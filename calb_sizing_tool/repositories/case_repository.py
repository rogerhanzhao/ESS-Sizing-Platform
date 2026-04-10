from __future__ import annotations

from sqlalchemy.orm import Session

from calb_sizing_tool.infra.db.models import Project, SizingCase


class CaseRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_or_create_project(
        self,
        *,
        project_code: str,
        project_name: str,
        description: str | None = None,
        version_tag: str | None = None,
        source_ref: str | None = None,
    ) -> Project:
        row = self.session.query(Project).filter_by(project_code=project_code).one_or_none()
        if row is None:
            row = Project(
                project_code=project_code,
                project_name=project_name,
                description=description,
                version_tag=version_tag,
                source_ref=source_ref,
            )
            self.session.add(row)
        return row

    def get_project_by_id(self, project_id: str) -> Project | None:
        return self.session.query(Project).filter_by(project_id=project_id).one_or_none()

    def list_projects(self) -> list[Project]:
        return (
            self.session.query(Project)
            .order_by(Project.created_at.desc())
            .all()
        )

    def list_projects_by_ids(self, project_ids: list[str]) -> list[Project]:
        if not project_ids:
            return []
        return (
            self.session.query(Project)
            .filter(Project.project_id.in_(project_ids))
            .order_by(Project.created_at.desc())
            .all()
        )

    def create_case(
        self,
        *,
        project_id: str,
        case_code: str,
        case_name: str,
        stage_scope: str,
        scenario_mode: str,
        input_json: dict,
        notes: str | None = None,
        version_tag: str | None = None,
        source_ref: str | None = None,
    ) -> SizingCase:
        row = SizingCase(
            project_id=project_id,
            case_code=case_code,
            case_name=case_name,
            stage_scope=stage_scope,
            scenario_mode=scenario_mode,
            input_json=input_json,
            notes=notes,
            version_tag=version_tag,
            source_ref=source_ref,
        )
        self.session.add(row)
        return row

    def get_case_by_id(self, sizing_case_id: str) -> SizingCase | None:
        return self.session.query(SizingCase).filter_by(sizing_case_id=sizing_case_id).one_or_none()

    def list_cases_by_project(self, project_id: str) -> list[SizingCase]:
        return (
            self.session.query(SizingCase)
            .filter_by(project_id=project_id)
            .order_by(SizingCase.created_at.desc())
            .all()
        )

    def create_case_if_needed(
        self,
        *,
        project_id: str,
        case_code: str,
        case_name: str,
        stage_scope: str,
        scenario_mode: str,
        input_json: dict,
        notes: str | None = None,
        version_tag: str | None = None,
        source_ref: str | None = None,
    ) -> SizingCase:
        row = (
            self.session.query(SizingCase)
            .filter_by(project_id=project_id, case_code=case_code, scenario_mode=scenario_mode)
            .order_by(SizingCase.created_at.desc())
            .first()
        )
        if row is not None:
            return row
        return self.create_case(
            project_id=project_id,
            case_code=case_code,
            case_name=case_name,
            stage_scope=stage_scope,
            scenario_mode=scenario_mode,
            input_json=input_json,
            notes=notes,
            version_tag=version_tag,
            source_ref=source_ref,
        )
