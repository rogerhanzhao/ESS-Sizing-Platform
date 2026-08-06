"""Step 2: drawings belong to the AC alternative that produced them.

Owner ruling B (2026-08-04): "同一个确定了的 DC 方案，AC 是可以稍微有多一个方案的
… SLD 以后的所有生成都可以变，最终报告可以重新生成一个版本".

The load-bearing piece is the ANCESTOR FALLBACK. Artifacts are read at the AC
alternative and the reader walks up parent_run_id, so:

- an alternative's own drawing always wins;
- an alternative that never produced a given figure still shows the DC run's;
- every database written before AC runs existed keeps working untouched, with no
  data migration.
"""
from __future__ import annotations

import pytest

from calb_sizing_tool.infra.db.base import Base
from calb_sizing_tool.infra.db.models.project import Project
from calb_sizing_tool.infra.db.models.sizing_run import SizingRun
from calb_sizing_tool.infra.db.session import session_scope
from calb_sizing_tool.plugins.base import ArtifactPayload
from calb_sizing_tool.services.artifact_service import (
    load_artifact_bytes_from_db,
    persist_artifacts,
)


@pytest.fixture()
def runs(tmp_path, monkeypatch):
    """A DC run with two AC alternatives hanging off it."""
    monkeypatch.setenv("CALB_OUTPUTS_DIR", str(tmp_path / "out"))
    url = f"sqlite:///{(tmp_path / 'scope.sqlite').as_posix()}"
    with session_scope(url) as session:
        Base.metadata.create_all(bind=session.get_bind())
    with session_scope(url) as session:
        session.add(Project(project_id="p1", project_code="P1", project_name="P1"))
        session.flush()
        session.add(SizingRun(
            sizing_run_id="dc-1", project_id="p1", sizing_case_id=None,
            run_type="dc_pipeline", status="succeeded",
            input_summary_json={}, output_summary_json={},
        ))
        session.flush()
        for child in ("ac-a", "ac-b"):
            session.add(SizingRun(
                sizing_run_id=child, project_id="p1", sizing_case_id=None,
                parent_run_id="dc-1", run_type="ac_sizing", status="succeeded",
                input_summary_json={}, output_summary_json={},
            ))
    return url


def _write(url, run_id, kind, body, *, plugin="p"):
    persist_artifacts(
        run_id=run_id,
        artifacts=[ArtifactPayload(
            artifact_kind=kind, file_name=f"{kind}.svg",
            media_type="image/svg+xml", content=body.encode(), metadata={},
        )],
        plugin_id=plugin, plugin_version="1", db_url=url,
    )


def test_an_alternatives_own_drawing_wins_over_the_dc_runs(runs):
    _write(runs, "dc-1", "sld_svg", "<svg>dc</svg>")
    _write(runs, "ac-a", "sld_svg", "<svg>ac-a</svg>")
    _write(runs, "ac-b", "sld_svg", "<svg>ac-b</svg>")

    assert load_artifact_bytes_from_db("ac-a", ["sld_svg"], db_url=runs)["sld_svg"] == b"<svg>ac-a</svg>"
    assert load_artifact_bytes_from_db("ac-b", ["sld_svg"], db_url=runs)["sld_svg"] == b"<svg>ac-b</svg>"
    # The DC run itself never sees its children's drawings — the walk is upward.
    assert load_artifact_bytes_from_db("dc-1", ["sld_svg"], db_url=runs)["sld_svg"] == b"<svg>dc</svg>"


def test_an_alternative_falls_back_to_the_dc_run_for_what_it_never_produced(runs):
    """Generate an SLD under an alternative but not an arrangement."""
    _write(runs, "dc-1", "sld_svg", "<svg>dc-sld</svg>")
    _write(runs, "dc-1", "layout_svg", "<svg>dc-layout</svg>")
    _write(runs, "ac-a", "sld_svg", "<svg>ac-sld</svg>")

    found = load_artifact_bytes_from_db("ac-a", ["sld_svg", "layout_svg"], db_url=runs)
    assert found["sld_svg"] == b"<svg>ac-sld</svg>"
    assert found["layout_svg"] == b"<svg>dc-layout</svg>"


def test_a_pre_existing_database_is_unaffected(runs):
    """Everything on the DC run, nothing on the branches — the old shape."""
    _write(runs, "dc-1", "sld_svg", "<svg>legacy</svg>")
    assert load_artifact_bytes_from_db("dc-1", ["sld_svg"], db_url=runs)["sld_svg"] == b"<svg>legacy</svg>"
    # And an alternative created later still finds it.
    assert load_artifact_bytes_from_db("ac-a", ["sld_svg"], db_url=runs)["sld_svg"] == b"<svg>legacy</svg>"


def test_the_fallback_can_be_switched_off(runs):
    _write(runs, "dc-1", "sld_svg", "<svg>dc</svg>")
    strict = load_artifact_bytes_from_db(
        "ac-a", ["sld_svg"], db_url=runs, include_ancestors=False)
    assert strict == {}


def test_alternatives_do_not_see_each_others_drawings(runs):
    _write(runs, "ac-a", "sld_svg", "<svg>ac-a</svg>")
    assert load_artifact_bytes_from_db("ac-b", ["sld_svg"], db_url=runs) == {}


def test_the_writers_can_target_an_alternative():
    """Every downstream service accepts the run its output belongs to."""
    import inspect

    from calb_sizing_tool.services.diagram_service import render_sld_from_run_bundle
    from calb_sizing_tool.services.layout_service import render_layout_from_run_bundle
    from calb_sizing_tool.services.sld_pipeline_service import run_sld_pipeline_from_run_bundle

    for func in (render_sld_from_run_bundle, render_layout_from_run_bundle,
                 run_sld_pipeline_from_run_bundle):
        params = inspect.signature(func).parameters
        assert "artifact_run_id" in params, func.__name__
        # Defaulting to None keeps every existing caller on the DC run.
        assert params["artifact_run_id"].default is None, func.__name__


def test_the_pages_ask_one_helper_which_run_to_use():
    """Deciding this per page is how the arrangement grew two implementations."""
    import inspect

    from calb_sizing_tool.ui import (
        report_export_view,
        single_line_diagram_view,
        site_layout_view,
    )

    for module in (single_line_diagram_view, site_layout_view, report_export_view):
        assert "artifact_run_id" in inspect.getsource(module), module.__name__


def test_switching_the_dc_run_drops_the_alternative_selection():
    """An AC alternative belongs to ONE DC run; carrying it over would mis-point."""
    import inspect

    from calb_sizing_tool.state import workspace_state

    src = inspect.getsource(workspace_state.set_active_run)
    assert "active_ac_run_id" in src, (
        "set_active_run must clear the alternative, or the downstream pages would "
        "read another run's branch"
    )
