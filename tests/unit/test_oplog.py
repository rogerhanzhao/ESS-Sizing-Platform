from __future__ import annotations

import json

from calb_sizing_tool.infra import oplog


def _read_lines(directory):
    files = list(directory.glob("oplog-*.jsonl"))
    assert len(files) == 1
    return [json.loads(line) for line in files[0].read_text(encoding="utf-8").splitlines()]


def test_page_view_and_error_are_appended_as_jsonl(tmp_path, monkeypatch):
    monkeypatch.setenv("CALB_OPLOG_DIR", str(tmp_path))
    monkeypatch.setenv("CALB_OPLOG_ENABLED", "true")

    oplog.log_page_view(actor="alice", page="DC Sizing", is_guest=False)
    try:
        raise ValueError("boom")
    except ValueError as exc:
        oplog.log_error(actor="alice", page="DC Sizing", error=exc)

    records = _read_lines(tmp_path)
    assert [r["kind"] for r in records] == ["page_view", "error"]
    assert records[0]["actor"] == "alice"
    assert records[0]["page"] == "DC Sizing"
    assert records[1]["error_type"] == "ValueError"
    assert "boom" in records[1]["error"]
    assert "ValueError" in records[1]["traceback"]
    assert all("ts" in r for r in records)


def test_disabled_switch_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.setenv("CALB_OPLOG_DIR", str(tmp_path))
    monkeypatch.setenv("CALB_OPLOG_ENABLED", "false")

    oplog.log_page_view(actor="alice", page="DC Sizing")

    assert list(tmp_path.glob("*.jsonl")) == []


def test_oplog_never_raises_on_unwritable_destination(monkeypatch):
    # A file path used as a directory makes mkdir/open fail on every platform.
    monkeypatch.setenv("CALB_OPLOG_ENABLED", "true")
    monkeypatch.setenv("CALB_OPLOG_DIR", str(__file__))

    oplog.log_page_view(actor="alice", page="DC Sizing")  # must not raise
    try:
        raise RuntimeError("x")
    except RuntimeError as exc:
        oplog.log_error(actor=None, page="p", error=exc)  # must not raise
