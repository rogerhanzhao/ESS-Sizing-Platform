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


def test_saved_mixed_snapshot_shows_actual_42_pcs_schedule_without_uniform_head_claim():
    from calb_sizing_tool.services.ac_run_service import ac_configuration_hash
    rows = ([dict(pcs_count=4, pcs_kw=2500, dc_blocks=4) for _ in range(9)]
            + [dict(pcs_count=2, pcs_kw=2500, dc_blocks=4) for _ in range(2)]
            + [dict(pcs_count=2, pcs_kw=2500, dc_blocks=2)])
    saved = dict(num_blocks=12, pcs_per_block=4, pcs_kw=2500, total_ac_mw=105,
                 ac_block_mixed=True, ac_block_rows=rows,
                 ac_block_model_name="Uniform head label must not describe the station")
    before_hash = ac_configuration_hash(saved)
    app = AppTest.from_string(
        "from calb_sizing_tool.ui.ac_view import _render_saved_ac_snapshot\n"
        "from calb_sizing_tool.ui._ui import section_header\n"
        f"saved = {saved!r}\n_render_saved_ac_snapshot(saved, section_header=section_header)\n"
        f"assert saved == {saved!r}"
    ).run(timeout=30)
    assert not app.exception
    assert next(metric.value for metric in app.metric if metric.label == "Total PCS") == "42"
    assert next(metric.value for metric in app.metric if metric.label == "Total AC Power") == "105.00 MW"
    assert not any(metric.label == "PCS per Block" for metric in app.metric)
    table = " ".join(str(item.value) for item in app.markdown)
    assert "4 x 2,500 kW" in table and "2 x 2,500 kW" in table
    assert "90.00" in table and "15.00" in table
    assert not any("Uniform head label" in str(item.value) for item in app.caption)
    assert ac_configuration_hash(saved) == before_hash
