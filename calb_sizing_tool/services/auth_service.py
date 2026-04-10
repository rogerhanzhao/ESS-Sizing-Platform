from __future__ import annotations

import hashlib
import hmac
import os
from dataclasses import dataclass

from calb_sizing_tool.infra.db.base import utc_now
from calb_sizing_tool.infra.db.session import session_scope
from calb_sizing_tool.repositories.auth_repository import AuthRepository


_PBKDF2_ROUNDS = 120_000


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
