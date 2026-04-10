from __future__ import annotations

from sqlalchemy.orm import Session

from calb_sizing_tool.repositories.auth_repository import AuthRepository
from calb_sizing_tool.repositories.case_repository import CaseRepository
from calb_sizing_tool.repositories.run_repository import RunRepository
from calb_sizing_tool.schemas.run_bundle import DcRunBundle
from calb_sizing_tool.services.run_restore_service import load_dc_run_bundle
from calb_sizing_tool.services.auth_service import AuthUser


class AccessControlService:
    def __init__(self, session: Session, auth_user: AuthUser):
        self.session = session
        self.auth_user = auth_user
        self.auth_repo = AuthRepository(session)
        self.case_repo = CaseRepository(session)
        self.run_repo = RunRepository(session)
        try:
            self.db_url = str(session.get_bind().url)
        except Exception:
            self.db_url = None

    def is_admin(self) -> bool:
        return self.auth_user.is_admin

    def ensure_project_access(self, project_id: str) -> None:
        if self.is_admin():
            return
        if not self.auth_repo.is_project_member(project_id=project_id, user_id=self.auth_user.user_id):
            raise PermissionError("Project access denied.")

    def list_projects(self):
        if self.is_admin():
            return self.case_repo.list_projects()
        project_ids = self.auth_repo.list_project_ids_for_user(self.auth_user.user_id)
        return self.case_repo.list_projects_by_ids(project_ids)

    def list_cases_by_project(self, project_id: str):
        self.ensure_project_access(project_id)
        return self.case_repo.list_cases_by_project(project_id)

    def list_runs_by_case(self, sizing_case_id: str):
        sizing_case = self.case_repo.get_case_by_id(sizing_case_id)
        if sizing_case is None:
            return []
        self.ensure_project_access(sizing_case.project_id)
        return self.run_repo.list_runs_by_case(sizing_case_id)

    def load_dc_run_bundle(self, run_id: str) -> DcRunBundle | None:
        bundle = self.run_repo.get_run_bundle(run_id)
        if bundle is None:
            return None
        run = bundle.get("run")
        project_id = getattr(run, "project_id", None)
        if project_id:
            self.ensure_project_access(project_id)
        return load_dc_run_bundle(run_id, db_url=self.db_url)
