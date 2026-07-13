"""load_dc_run_bundle must fail closed when a run cannot be attributed to a
project: a non-admin must not read it on the strength of a missing project_id.
"""
import pytest

from calb_sizing_tool.infra.db.base import Base
from calb_sizing_tool.infra.db.session import create_engine_for_url, create_session_factory
from calb_sizing_tool.services import access_control_service as acs_mod
from calb_sizing_tool.services.access_control_service import AccessControlService
from calb_sizing_tool.services.auth_service import AuthUser


class _NullProjectRun:
    project_id = None


class _StubRunRepo:
    def get_run_bundle(self, run_id):
        return {"run": _NullProjectRun()}


def _service(tmp_path, roles):
    db_url = f"sqlite:///{(tmp_path / 'acl.sqlite').as_posix()}"
    Base.metadata.create_all(bind=create_engine_for_url(db_url))
    session = create_session_factory(db_url)()
    user = AuthUser(user_id="u1", username="u1", display_name=None, roles=roles)
    service = AccessControlService(session, user)
    service.run_repo = _StubRunRepo()
    return service


def test_non_admin_denied_when_run_has_no_project(tmp_path):
    service = _service(tmp_path, roles=[])
    with pytest.raises(PermissionError):
        service.load_dc_run_bundle("run-x")


def test_admin_allowed_when_run_has_no_project(tmp_path, monkeypatch):
    monkeypatch.setattr(acs_mod, "load_dc_run_bundle", lambda run_id, db_url=None: {"ok": True})
    service = _service(tmp_path, roles=["admin"])
    assert service.load_dc_run_bundle("run-x") == {"ok": True}
