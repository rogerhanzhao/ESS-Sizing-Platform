from __future__ import annotations

from calb_sizing_tool.infra.db.base import Base
from calb_sizing_tool.infra.db.session import create_engine_for_url
from calb_sizing_tool.services.auth_service import AuthService


def test_auth_login_flow(tmp_path):
    db_url = f"sqlite:///{(tmp_path / 'auth_login.sqlite').as_posix()}"
    engine = create_engine_for_url(db_url)
    Base.metadata.create_all(bind=engine)

    service = AuthService(db_url)
    service.ensure_system_roles()
    user = service.create_user(username="admin", password="secret", role_codes=["admin"])
    assert user.is_admin

    auth_user = service.authenticate(username="admin", password="secret")
    assert auth_user is not None
    assert auth_user.user_id == user.user_id
    assert auth_user.is_admin
