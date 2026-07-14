from __future__ import annotations

from calb_sizing_tool.infra.db.base import Base
from calb_sizing_tool.infra.db.session import create_engine_for_url, session_scope
from calb_sizing_tool.repositories.case_repository import CaseRepository


def test_create_project_does_not_reuse_existing_project_code(tmp_path):
    db_url = f"sqlite:///{(tmp_path / 'project_creation.sqlite').as_posix()}"
    engine = create_engine_for_url(db_url)
    Base.metadata.create_all(bind=engine)

    with session_scope(db_url) as session:
        repo = CaseRepository(session)
        first = repo.create_project(project_code="same-name", project_name="Same Name")
        second = repo.create_project(project_code="same-name-2", project_name="Same Name")
        session.flush()

        assert first.project_id != second.project_id
        assert repo.get_project_by_code("same-name").project_id == first.project_id
        assert repo.get_project_by_code("same-name-2").project_id == second.project_id
