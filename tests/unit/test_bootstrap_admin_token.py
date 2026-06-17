from __future__ import annotations

from calb_sizing_tool.ui.login_view import (
    _bootstrap_admin_token,
    _bootstrap_token_matches,
    _bootstrap_token_required,
)


def test_bootstrap_token_is_optional_by_default(monkeypatch):
    monkeypatch.delenv("CALB_REQUIRE_BOOTSTRAP_TOKEN", raising=False)
    monkeypatch.delenv("CALB_BOOTSTRAP_ADMIN_TOKEN", raising=False)
    assert not _bootstrap_token_required()
    assert _bootstrap_admin_token() == ""
    assert not _bootstrap_token_matches("anything")


def test_bootstrap_token_required_flag_and_match(monkeypatch):
    monkeypatch.setenv("CALB_REQUIRE_BOOTSTRAP_TOKEN", "true")
    monkeypatch.setenv("CALB_BOOTSTRAP_ADMIN_TOKEN", "server-secret")
    assert _bootstrap_token_required()
    assert _bootstrap_token_matches("server-secret")
    assert not _bootstrap_token_matches("wrong")
