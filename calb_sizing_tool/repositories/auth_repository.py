from __future__ import annotations

from sqlalchemy.orm import Session

from calb_sizing_tool.infra.db.models import ProjectMember, RoleDefinition, UserAccount, UserRoleBinding


class AuthRepository:
    def __init__(self, session: Session):
        self.session = session

    def ensure_role(
        self,
        *,
        role_code: str,
        display_name: str,
        description: str | None = None,
        is_system: bool = True,
        version_tag: str | None = None,
        source_ref: str | None = None,
    ) -> RoleDefinition:
        row = self.session.query(RoleDefinition).filter_by(role_code=role_code).one_or_none()
        if row is None:
            row = RoleDefinition(
                role_code=role_code,
                display_name=display_name,
                description=description,
                is_system=is_system,
                version_tag=version_tag,
                source_ref=source_ref,
            )
            self.session.add(row)
        return row

    def ensure_system_roles(self) -> dict[str, RoleDefinition]:
        admin = self.ensure_role(
            role_code="admin",
            display_name="Administrator",
            description="System administrator",
            is_system=True,
            source_ref="bootstrap",
        )
        normal = self.ensure_role(
            role_code="normal_user",
            display_name="Normal User",
            description="Standard project user",
            is_system=True,
            source_ref="bootstrap",
        )
        return {"admin": admin, "normal_user": normal}

    def has_any_user(self) -> bool:
        return self.session.query(UserAccount).first() is not None

    def list_users(self) -> list[UserAccount]:
        return (
            self.session.query(UserAccount)
            .order_by(UserAccount.created_at.desc(), UserAccount.username.asc())
            .all()
        )

    def list_roles(self) -> list[RoleDefinition]:
        return self.session.query(RoleDefinition).order_by(RoleDefinition.role_code.asc()).all()

    def create_user(
        self,
        *,
        username: str,
        password_hash: str,
        password_salt: str,
        display_name: str | None = None,
        email: str | None = None,
        status: str = "active",
        role_codes: list[str] | None = None,
        version_tag: str | None = None,
        source_ref: str | None = None,
    ) -> UserAccount:
        user = UserAccount(
            username=username,
            email=email,
            display_name=display_name,
            password_hash=password_hash,
            password_salt=password_salt,
            status=status,
            version_tag=version_tag,
            source_ref=source_ref,
        )
        self.session.add(user)
        self.session.flush()

        if role_codes:
            for code in role_codes:
                role = self.session.query(RoleDefinition).filter_by(role_code=code).one_or_none()
                if role is None:
                    continue
                binding = UserRoleBinding(user_id=user.user_id, role_id=role.role_id)
                self.session.add(binding)
        self.session.flush()
        return user

    def get_user_by_username(self, username: str) -> UserAccount | None:
        return self.session.query(UserAccount).filter_by(username=username).one_or_none()

    def get_user_by_email(self, email: str) -> UserAccount | None:
        return self.session.query(UserAccount).filter_by(email=email).one_or_none()

    def get_user_by_id(self, user_id: str) -> UserAccount | None:
        return self.session.query(UserAccount).filter_by(user_id=user_id).one_or_none()

    def list_user_roles(self, user_id: str) -> list[RoleDefinition]:
        return (
            self.session.query(RoleDefinition)
            .join(UserRoleBinding, RoleDefinition.role_id == UserRoleBinding.role_id)
            .filter(UserRoleBinding.user_id == user_id)
            .all()
        )

    def is_admin(self, user_id: str) -> bool:
        return any(role.role_code == "admin" for role in self.list_user_roles(user_id))

    def count_active_admins(self) -> int:
        return (
            self.session.query(UserAccount.user_id)
            .join(UserRoleBinding, UserAccount.user_id == UserRoleBinding.user_id)
            .join(RoleDefinition, UserRoleBinding.role_id == RoleDefinition.role_id)
            .filter(UserAccount.status == "active", RoleDefinition.role_code == "admin")
            .distinct()
            .count()
        )

    def add_user_role(self, user_id: str, role_code: str) -> UserRoleBinding | None:
        role = self.session.query(RoleDefinition).filter_by(role_code=role_code).one_or_none()
        if role is None:
            return None
        binding = (
            self.session.query(UserRoleBinding)
            .filter_by(user_id=user_id, role_id=role.role_id)
            .one_or_none()
        )
        if binding is None:
            binding = UserRoleBinding(user_id=user_id, role_id=role.role_id)
            self.session.add(binding)
        return binding

    def set_user_roles(self, user_id: str, role_codes: list[str]) -> None:
        role_rows = (
            self.session.query(RoleDefinition)
            .filter(RoleDefinition.role_code.in_(role_codes))
            .all()
        )
        self.session.query(UserRoleBinding).filter_by(user_id=user_id).delete(synchronize_session=False)
        for role in role_rows:
            self.session.add(UserRoleBinding(user_id=user_id, role_id=role.role_id))

    def update_user_account(
        self,
        *,
        user_id: str,
        display_name: str | None = None,
        email: str | None = None,
        status: str = "active",
        password_hash: str | None = None,
        password_salt: str | None = None,
    ) -> UserAccount | None:
        user = self.get_user_by_id(user_id)
        if user is None:
            return None
        user.display_name = display_name
        user.email = email
        user.status = status
        if password_hash is not None and password_salt is not None:
            user.password_hash = password_hash
            user.password_salt = password_salt
        self.session.add(user)
        return user

    def add_project_member(
        self,
        *,
        project_id: str,
        user_id: str,
        role_code: str = "normal_user",
        status: str = "active",
    ) -> ProjectMember | None:
        role = self.session.query(RoleDefinition).filter_by(role_code=role_code).one_or_none()
        role_id = role.role_id if role else None
        member = (
            self.session.query(ProjectMember)
            .filter_by(project_id=project_id, user_id=user_id)
            .one_or_none()
        )
        if member is None:
            member = ProjectMember(
                project_id=project_id,
                user_id=user_id,
                role_id=role_id,
                status=status,
            )
            self.session.add(member)
        return member

    def list_project_memberships(self, user_id: str, *, active_only: bool = False) -> list[ProjectMember]:
        query = self.session.query(ProjectMember).filter_by(user_id=user_id)
        if active_only:
            query = query.filter_by(status="active")
        return query.order_by(ProjectMember.created_at.desc()).all()

    def set_project_memberships(
        self,
        *,
        user_id: str,
        project_ids: list[str],
        role_code: str = "normal_user",
    ) -> None:
        self.session.query(ProjectMember).filter_by(user_id=user_id).delete(synchronize_session=False)
        for project_id in dict.fromkeys(project_ids):
            self.add_project_member(project_id=project_id, user_id=user_id, role_code=role_code, status="active")

    def is_project_member(self, *, project_id: str, user_id: str) -> bool:
        return (
            self.session.query(ProjectMember)
            .filter_by(project_id=project_id, user_id=user_id)
            .one_or_none()
            is not None
        )

    def list_project_ids_for_user(self, user_id: str) -> list[str]:
        rows = (
            self.session.query(ProjectMember.project_id)
            .filter_by(user_id=user_id, status="active")
            .all()
        )
        return [row[0] for row in rows]
