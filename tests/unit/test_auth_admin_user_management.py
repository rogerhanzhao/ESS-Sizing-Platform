from __future__ import annotations

import pytest

from calb_sizing_tool.infra.db.base import Base
from calb_sizing_tool.infra.db.session import create_engine_for_url, session_scope
from calb_sizing_tool.repositories.case_repository import CaseRepository
from calb_sizing_tool.services.access_control_service import AccessControlService
from calb_sizing_tool.services.auth_service import AuthService


def _make_db(tmp_path, name: str) -> str:
    db_url = f"sqlite:///{(tmp_path / name).as_posix()}"
    engine = create_engine_for_url(db_url)
    Base.metadata.create_all(bind=engine)
    return db_url


def test_admin_can_create_normal_user_with_project_scope(tmp_path):
    db_url = _make_db(tmp_path, "auth_admin_create.sqlite")
    auth_service = AuthService(db_url)
    auth_service.ensure_system_roles()
    admin = auth_service.create_user(username="admin", password="secret", role_codes=["admin"])

    with session_scope(db_url) as session:
        case_repo = CaseRepository(session)
        project = case_repo.get_or_create_project(project_code="alpha", project_name="Alpha")
        session.flush()
        project_id = project.project_id

    user = auth_service.admin_create_user(
        actor_user_id=admin.user_id,
        username="user1",
        password="secret",
        display_name="User One",
        role_codes=["normal_user"],
        project_ids=[project_id],
    )

    assert not user.is_admin
    assert auth_service.authenticate(username="user1", password="secret") is not None

    rows = auth_service.list_user_admin_rows()
    row = next(item for item in rows if item["username"] == "user1")
    assert row["roles"] == ["normal_user"]
    assert row["project_ids"] == [project_id]

    with session_scope(db_url) as session:
        access = AccessControlService(session, user)
        assert [project.project_code for project in access.list_projects()] == ["alpha"]


def test_admin_user_management_guardrails_prevent_self_lockout(tmp_path):
    db_url = _make_db(tmp_path, "auth_admin_guardrails.sqlite")
    auth_service = AuthService(db_url)
    auth_service.ensure_system_roles()
    admin = auth_service.create_user(username="admin", password="secret", role_codes=["admin"])

    with pytest.raises(ValueError, match="deactivate your own account"):
        auth_service.admin_update_user(
            user_id=admin.user_id,
            actor_user_id=admin.user_id,
            status="inactive",
            role_codes=["admin"],
        )

    with pytest.raises(ValueError, match="remove your own admin role"):
        auth_service.admin_update_user(
            user_id=admin.user_id,
            actor_user_id=admin.user_id,
            status="active",
            role_codes=["normal_user"],
        )


def test_admin_user_management_requires_admin_actor(tmp_path):
    db_url = _make_db(tmp_path, "auth_admin_actor.sqlite")
    auth_service = AuthService(db_url)
    auth_service.ensure_system_roles()
    admin = auth_service.create_user(username="admin", password="secret", role_codes=["admin"])
    user = auth_service.create_user(username="user1", password="secret", role_codes=["normal_user"])

    with pytest.raises(ValueError, match="Admin access required"):
        auth_service.admin_update_user(
            user_id=admin.user_id,
            actor_user_id=user.user_id,
            status="active",
            role_codes=["admin"],
        )
