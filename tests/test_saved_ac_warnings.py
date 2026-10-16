from streamlit.testing.v1 import AppTest


def test_saved_ac_displays_existing_overhead_warning_without_changing_record():
    saved = dict(num_blocks=20, pcs_per_block=2, pcs_kw=2000, total_ac_mw=80,
                 dc_total_mwh=16.72, poi_energy_mwh=14.3, poi_power_mw=8)
    app = AppTest.from_string(
        "from calb_sizing_tool.ui.ac_view import _render_saved_ac_snapshot\n"
        "from calb_sizing_tool.ui._ui import section_header\n"
        f"saved = {saved!r}\n_render_saved_ac_snapshot(saved, section_header=section_header)\nassert saved == {saved!r}"
    ).run(timeout=30)
    assert not app.exception
    assert any("72.0 MW (900%" in str(item.value) for item in app.warning)
    assert next(metric.value for metric in app.metric if metric.label == "Total AC Power") == "80.00 MW"


def test_older_saved_record_remains_viewable_without_comparison_fields():
    app = AppTest.from_string(
        "from calb_sizing_tool.ui.ac_view import _render_saved_ac_snapshot\n"
        "from calb_sizing_tool.ui._ui import section_header\n"
        "_render_saved_ac_snapshot({'num_blocks': 1, 'total_ac_mw': 8}, section_header=section_header)"
    ).run(timeout=30)
    assert not app.exception
    assert not app.warning
    assert not app.error
    assert next(metric.value for metric in app.metric if metric.label == "Total AC Power") == "8.00 MW"
