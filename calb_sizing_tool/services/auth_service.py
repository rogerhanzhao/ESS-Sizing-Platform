from __future__ import annotations

import hashlib
import hmac
import os
from dataclasses import dataclass
from typing import Any

from calb_sizing_tool.infra.db.base import utc_now
from calb_sizing_tool.infra.db.session import session_scope
from calb_sizing_tool.repositories.auth_repository import AuthRepository
from calb_sizing_tool.repositories.case_repository import CaseRepository


_PBKDF2_ROUNDS = 120_000
_USER_STATUSES = {"active", "inactive"}


@dataclass
class AuthUser:
    user_id: str
    username: str
    display_name: str | None
    roles: list[str]

    @property
    def is_admin(self) -> bool:
        return "admin" in self.roles


def _hash_password(password: str, *, salt: bytes | None = None) -> tuple[str, str]:
    salt = salt or os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ROUNDS)
    return digest.hex(), salt.hex()


def _verify_password(password: str, password_hash: str, password_salt: str) -> bool:
    try:
        salt = bytes.fromhex(password_salt)
    except ValueError:
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ROUNDS).hex()
    return hmac.compare_digest(digest, password_hash)


class AuthService:
    def __init__(self, db_url: str | None = None):
        self.db_url = db_url

    def ensure_system_roles(self) -> None:
        with session_scope(self.db_url) as session:
            repo = AuthRepository(session)
            repo.ensure_system_roles()

    def has_users(self) -> bool:
        with session_scope(self.db_url) as session:
            repo = AuthRepository(session)
            return repo.has_any_user()

    def create_user(
        self,
        *,
        username: str,
        password: str,
        display_name: str | None = None,
        email: str | None = None,
        role_codes: list[str] | None = None,
    ) -> AuthUser:
        password_hash, password_salt = _hash_password(password)
        with session_scope(self.db_url) as session:
            repo = AuthRepository(session)
            repo.ensure_system_roles()
            user = repo.create_user(
                username=username,
                password_hash=password_hash,
                password_salt=password_salt,
                display_name=display_name,
                email=email,
                role_codes=role_codes,
                source_ref="auth_service",
            )
            roles = repo.list_user_roles(user.user_id)
            return AuthUser(
                user_id=user.user_id,
                username=user.username,
                display_name=user.display_name,
                roles=[role.role_code for role in roles],
            )

    def list_role_codes(self) -> list[str]:
        with session_scope(self.db_url) as session:
            repo = AuthRepository(session)
            repo.ensure_system_roles()
            return [role.role_code for role in repo.list_roles()]

    def list_project_options(self) -> list[dict[str, str]]:
        with session_scope(self.db_url) as session:
            projects = CaseRepository(session).list_projects()
            return [
                {
                    "project_id": project.project_id,
                    "project_code": project.project_code,
                    "project_name": project.project_name,
                    "label": _project_label(project.project_code, project.project_name),
                }
                for project in projects
            ]

    def list_user_admin_rows(self) -> list[dict[str, Any]]:
        with session_scope(self.db_url) as session:
            repo = AuthRepository(session)
            repo.ensure_system_roles()
            projects = CaseRepository(session).list_projects()
            project_labels = {
                project.project_id: _project_label(project.project_code, project.project_name)
                for project in projects
            }

            rows: list[dict[str, Any]] = []
            for user in repo.list_users():
                roles = [role.role_code for role in repo.list_user_roles(user.user_id)]
                memberships = repo.list_project_memberships(user.user_id, active_only=True)
                project_ids = [member.project_id for member in memberships]
                rows.append(
                    {
                        "user_id": user.user_id,
                        "username": user.username,
                        "display_name": user.display_name,
                        "email": user.email,
                        "status": user.status,
                        "roles": roles,
                        "is_admin": "admin" in roles,
                        "project_ids": project_ids,
                        "project_labels": [
                            project_labels.get(project_id, project_id)
                            for project_id in project_ids
                        ],
                        "created_at": user.created_at,
                        "last_login_at": user.last_login_at,
                    }
                )
            return rows

    def admin_create_user(
        self,
        *,
        actor_user_id: str,
        username: str,
        password: str,
        display_name: str | None = None,
        email: str | None = None,
        role_codes: list[str] | None = None,
        project_ids: list[str] | None = None,
    ) -> AuthUser:
        username = username.strip()
        email = _clean_optional(email)
        display_name = _clean_optional(display_name)
        if not username:
            raise ValueError("Username is required.")
        if not password:
            raise ValueError("Initial password is required.")

        password_hash, password_salt = _hash_password(password)
        with session_scope(self.db_url) as session:
            repo = AuthRepository(session)
            case_repo = CaseRepository(session)
            repo.ensure_system_roles()
            _ensure_actor_admin(repo, actor_user_id)
            cleaned_roles = _clean_role_codes(repo, role_codes or ["normal_user"])
            cleaned_project_ids = _clean_project_ids(case_repo, project_ids or [])
            if repo.get_user_by_username(username) is not None:
                raise ValueError("Username already exists.")
            if email and repo.get_user_by_email(email) is not None:
                raise ValueError("Email already exists.")

            user = repo.create_user(
                username=username,
                password_hash=password_hash,
                password_salt=password_salt,
                display_name=display_name,
                email=email,
                role_codes=cleaned_roles,
                source_ref="admin_portal",
            )
            repo.set_project_memberships(user_id=user.user_id, project_ids=cleaned_project_ids)
            return AuthUser(
                user_id=user.user_id,
                username=user.username,
                display_name=user.display_name,
                roles=cleaned_roles,
            )

    def admin_update_user(
        self,
        *,
        user_id: str,
        actor_user_id: str,
        display_name: str | None = None,
        email: str | None = None,
        status: str = "active",
        role_codes: list[str] | None = None,
        project_ids: list[str] | None = None,
        new_password: str | None = None,
    ) -> AuthUser:
        status = status.strip().lower()
        if status not in _USER_STATUSES:
            raise ValueError("Unsupported user status.")

        with session_scope(self.db_url) as session:
            repo = AuthRepository(session)
            case_repo = CaseRepository(session)
            repo.ensure_system_roles()
            _ensure_actor_admin(repo, actor_user_id)

            user = repo.get_user_by_id(user_id)
            if user is None:
                raise ValueError("User not found.")

            cleaned_roles = _clean_role_codes(repo, role_codes or [])
            cleaned_project_ids = _clean_project_ids(case_repo, project_ids or [])
            target_is_admin = "admin" in cleaned_roles
            target_is_active = status == "active"
            currently_admin = repo.is_admin(user_id)
            cleaned_email = _clean_optional(email)
            cleaned_display_name = _clean_optional(display_name)

            if actor_user_id == user_id and not target_is_active:
                raise ValueError("You cannot deactivate your own account.")
            if actor_user_id == user_id and not target_is_admin:
                raise ValueError("You cannot remove your own admin role.")
            if currently_admin and (not target_is_admin or not target_is_active) and repo.count_active_admins() <= 1:
                raise ValueError("At least one active administrator must remain.")

            password_hash = password_salt = None
            if new_password:
                password_hash, password_salt = _hash_password(new_password)

            if cleaned_email:
                existing_email = repo.get_user_by_email(cleaned_email)
                if existing_email is not None and existing_email.user_id != user_id:
                    raise ValueError("Email already exists.")

            updated = repo.update_user_account(
                user_id=user_id,
                display_name=cleaned_display_name,
                email=cleaned_email,
                status=status,
                password_hash=password_hash,
                password_salt=password_salt,
            )
            if updated is None:
                raise ValueError("User update failed.")
            repo.set_user_roles(user_id, cleaned_roles)
            repo.set_project_memberships(user_id=user_id, project_ids=cleaned_project_ids)
            return AuthUser(
                user_id=updated.user_id,
                username=updated.username,
                display_name=updated.display_name,
                roles=cleaned_roles,
            )

    def authenticate(self, *, username: str, password: str) -> AuthUser | None:
        with session_scope(self.db_url) as session:
            repo = AuthRepository(session)
            user = repo.get_user_by_username(username)
            if user is None or user.status != "active":
                return None
            if not _verify_password(password, user.password_hash, user.password_salt):
                return None
            user.last_login_at = utc_now()
            roles = repo.list_user_roles(user.user_id)
            return AuthUser(
                user_id=user.user_id,
                username=user.username,
                display_name=user.display_name,
                roles=[role.role_code for role in roles],
            )


def _clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _clean_role_codes(repo: AuthRepository, role_codes: list[str]) -> list[str]:
    available = {role.role_code for role in repo.list_roles()}
    cleaned = [code.strip() for code in role_codes if code and code.strip()]
    cleaned = list(dict.fromkeys(cleaned))
    if not cleaned:
        raise ValueError("At least one role is required.")
    invalid = [code for code in cleaned if code not in available]
    if invalid:
        raise ValueError(f"Unsupported role(s): {', '.join(invalid)}")
    return cleaned


def _clean_project_ids(case_repo: CaseRepository, project_ids: list[str]) -> list[str]:
    cleaned = [project_id.strip() for project_id in project_ids if project_id and project_id.strip()]
    cleaned = list(dict.fromkeys(cleaned))
    for project_id in cleaned:
        if case_repo.get_project_by_id(project_id) is None:
            raise ValueError(f"Unknown project id: {project_id}")
    return cleaned


def _ensure_actor_admin(repo: AuthRepository, actor_user_id: str) -> None:
    if not actor_user_id or not repo.is_admin(actor_user_id):
        raise ValueError("Admin access required.")


def _project_label(project_code: str, project_name: str) -> str:
    if project_code == project_name:
        return project_name
    return f"{project_code} - {project_name}"
