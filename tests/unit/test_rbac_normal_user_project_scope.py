from __future__ import annotations

import pytest

from calb_sizing_tool.infra.db.base import Base
from calb_sizing_tool.infra.db.session import create_engine_for_url, session_scope
from calb_sizing_tool.repositories.auth_repository import AuthRepository
from calb_sizing_tool.repositories.case_repository import CaseRepository
from calb_sizing_tool.services.access_control_service import AccessControlService
from calb_sizing_tool.services.auth_service import AuthService


def test_rbac_normal_user_project_scope(tmp_path):
    db_url = f"sqlite:///{(tmp_path / 'rbac_user.sqlite').as_posix()}"
    engine = create_engine_for_url(db_url)
    Base.metadata.create_all(bind=engine)

    auth_service = AuthService(db_url)
    auth_service.ensure_system_roles()
    user = auth_service.create_user(username="user1", password="secret", role_codes=["normal_user"])

    with session_scope(db_url) as session:
        case_repo = CaseRepository(session)
        project_a = case_repo.get_or_create_project(project_code="alpha", project_name="Alpha")
        project_b = case_repo.get_or_create_project(project_code="beta", project_name="Beta")
        session.flush()
        auth_repo = AuthRepository(session)
        auth_repo.ensure_system_roles()
        auth_repo.add_project_member(project_id=project_a.project_id, user_id=user.user_id)
        inactive_project = case_repo.get_or_create_project(project_code="inactive", project_name="Inactive")
        session.flush()
        auth_repo.add_project_member(
            project_id=inactive_project.project_id,
            user_id=user.user_id,
            status="inactive",
        )
        project_b_id = project_b.project_id
        inactive_project_id = inactive_project.project_id

    with session_scope(db_url) as session:
        access = AccessControlService(session, user)
        projects = access.list_projects()
        assert [project.project_code for project in projects] == ["alpha"]
        with pytest.raises(PermissionError):
            access.ensure_project_access(project_b_id)
        with pytest.raises(PermissionError):
            access.ensure_project_access(inactive_project_id)
