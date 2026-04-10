from __future__ import annotations

from calb_sizing_tool.infra.db.base import Base
from calb_sizing_tool.infra.db.session import create_engine_for_url, session_scope
from calb_sizing_tool.repositories.case_repository import CaseRepository
from calb_sizing_tool.services.access_control_service import AccessControlService
from calb_sizing_tool.services.auth_service import AuthService


def test_rbac_admin_access(tmp_path):
    db_url = f"sqlite:///{(tmp_path / 'rbac_admin.sqlite').as_posix()}"
    engine = create_engine_for_url(db_url)
    Base.metadata.create_all(bind=engine)

    auth_service = AuthService(db_url)
    auth_service.ensure_system_roles()
    admin_user = auth_service.create_user(username="admin1", password="secret", role_codes=["admin"])

    with session_scope(db_url) as session:
        repo = CaseRepository(session)
        repo.get_or_create_project(project_code="alpha", project_name="Alpha")
        repo.get_or_create_project(project_code="beta", project_name="Beta")
        session.flush()

    with session_scope(db_url) as session:
        access = AccessControlService(session, admin_user)
        projects = access.list_projects()
        assert len(projects) == 2
