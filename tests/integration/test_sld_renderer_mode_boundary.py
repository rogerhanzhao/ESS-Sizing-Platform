from pathlib import Path

from calb_sizing_tool.services.sld_pipeline_service import prepare_sld_pipeline_from_run_bundle, render_prepared_sld_pipeline
from tests.integration.sld_regression_support import build_case_inputs, load_case_definition


def _case_inputs():
    case_dir = Path(__file__).resolve().parents[1] / "fixtures" / "sld_cases" / "case01_container_only_group1"
    return build_case_inputs(load_case_definition(case_dir))


def _with_dc_blocks_per_feeder(ac_snapshot, allocation):
    output = dict(ac_snapshot.output)
    plan = list(output["dc_allocation_plan"])
    first_plan = dict(plan[0])
    first_plan["dc_blocks_total"] = sum(allocation)
    first_plan["feeder_allocations"] = list(allocation)
    plan[0] = first_plan
    output["dc_allocation_plan"] = plan
    return ac_snapshot.model_copy(update={"output": output})


def _with_professional_note_specs(project_settings):
    settings = dict(project_settings)
    equipment = dict(settings["equipment_ratings"])
    equipment["cables"] = {
        "mv_cable_spec": "MV-3x1C-240mm2",
        "lv_cable_spec": "LV-3P+PE-630mm2",
        "dc_cable_spec": "DC-1x240mm2",
    }
    equipment["battery_cell_spec"] = "LFP 3.2V/314Ah"
    settings["equipment_ratings"] = equipment
    return settings


def test_legacy_server_renderer_mode_uses_server_baseline_svg():
    run_bundle, ac_snapshot, options, project_settings = _case_inputs()
    options = options.model_copy(update={"renderer_mode": "legacy_server"})

    prepared = prepare_sld_pipeline_from_run_bundle(
        run_bundle,
        ac_snapshot=ac_snapshot,
        options=options,
        project_settings=project_settings,
    )
    output = render_prepared_sld_pipeline(prepared)

    svg_text = output["svg_bytes"].decode("utf-8")
    assert output["metadata"]["renderer_mode"] == "legacy_server"
    assert output["metadata"]["renderer_lineage"] == "legacy_compatibility_patched"
    assert output["metadata"]["server_baseline_commit"] == "8568af4"
    assert "BUSBAR A (Ckt A)" not in svg_text
    assert "BUSBAR B (Ckt B)" not in svg_text
    assert "2 circuits (A/B)" not in svg_text
    assert "DC interface" not in svg_text
    assert "DC Block #1" in svg_text
    assert "Ring Main Unit (SF6)" in svg_text


def test_topology_v1_renderer_mode_stays_current_refactored_path():
    run_bundle, ac_snapshot, options, project_settings = _case_inputs()
    options = options.model_copy(update={"renderer_mode": "topology_v1"})

    prepared = prepare_sld_pipeline_from_run_bundle(
        run_bundle,
        ac_snapshot=ac_snapshot,
        options=options,
        project_settings=project_settings,
    )
    output = render_prepared_sld_pipeline(prepared)

    svg_text = output["svg_bytes"].decode("utf-8")
    assert output["metadata"]["renderer_mode"] == "topology_v1"
    assert output["metadata"]["renderer_lineage"] == "refactored_topology_v1"
    assert output["metadata"]["server_baseline_commit"] is None
    assert "RMU / MV Switchgear" in svg_text


def test_engineering_v2_renderer_mode_uses_port_bay_preview_path():
    run_bundle, ac_snapshot, options, project_settings = _case_inputs()
    options = options.model_copy(update={"renderer_mode": "engineering_v2"})

    prepared = prepare_sld_pipeline_from_run_bundle(
        run_bundle,
        ac_snapshot=ac_snapshot,
        options=options,
        project_settings=project_settings,
    )
    output = render_prepared_sld_pipeline(prepared)

    svg_text = output["svg_bytes"].decode("utf-8")
    assert output["metadata"]["renderer_mode"] == "engineering_v2"
    assert output["metadata"]["renderer_lineage"] == "port_bay_engineering_v2_preview"
    assert output["metadata"]["server_baseline_commit"] is None
    assert output["metadata"]["engineering_v2_graph_hash"]
    assert output["metadata"]["engineering_v2_layout_hash"]
    assert output["metadata"]["engineering_v2_node_count"] == 24
    assert output["metadata"]["engineering_v2_connector_count"] == output["metadata"]["engineering_v2_edge_count"]
    assert output["metadata"]["engineering_v2_layout_issue_count"] == 0
    assert output["metadata"]["engineering_v2_layout_warning_count"] == 4
    assert output["metadata"]["engineering_v2_png_width"] == 1780
    assert output["metadata"]["engineering_v2_png_height"] == 900
    assert output["metadata"]["engineering_v2_template"] == "professional_electrical_reference_v1"
    assert [issue["issue_id"] for issue in output["engineering_v2_layout_issues"]] == [
        "missing_professional_input:MV Cable",
        "missing_professional_input:LV Cable",
        "missing_professional_input:DC Cable",
        "missing_professional_input:BESS Cell",
    ]
    assert "RMU / MV Switchgear" in svg_text
    assert "Transformer Feeder" in svg_text
    assert "DC Isolator/Fuse" in svg_text
    assert "DC BUSBAR" not in svg_text
    assert output["engineering_v2_graph"]["model_version"] == "engineering_v2_topology_v1"
    assert output["engineering_v2_layout"]["connectors"]


def test_engineering_v2_renderer_mode_handles_multi_dc_block_feeders():
    run_bundle, ac_snapshot, options, project_settings = _case_inputs()
    ac_snapshot = _with_dc_blocks_per_feeder(ac_snapshot, [2, 1, 2, 1])
    options = options.model_copy(update={"renderer_mode": "engineering_v2"})

    prepared = prepare_sld_pipeline_from_run_bundle(
        run_bundle,
        ac_snapshot=ac_snapshot,
        options=options,
        project_settings=project_settings,
    )
    output = render_prepared_sld_pipeline(prepared)

    svg_text = output["svg_bytes"].decode("utf-8")
    dc_block_boxes = [box for box in output["engineering_v2_layout"]["boxes"] if box["node_type"] == "dc_block"]

    assert output["metadata"]["renderer_mode"] == "engineering_v2"
    assert output["metadata"]["engineering_v2_layout_issue_count"] == 0
    assert output["metadata"]["engineering_v2_layout_warning_count"] == 4
    assert output["metadata"]["engineering_v2_node_count"] == 26
    assert output["metadata"]["engineering_v2_png_width"] == 1780
    assert output["metadata"]["engineering_v2_png_height"] == 900
    assert output["metadata"]["engineering_v2_template"] == "professional_electrical_reference_v1"
    assert len(dc_block_boxes) == 6
    assert "DC Block #6" in svg_text
    assert "DC BUSBAR" not in svg_text


def test_engineering_v2_professional_notes_use_authoritative_cable_and_cell_specs():
    run_bundle, ac_snapshot, options, project_settings = _case_inputs()
    options = options.model_copy(update={"renderer_mode": "engineering_v2"})
    project_settings = _with_professional_note_specs(project_settings)

    prepared = prepare_sld_pipeline_from_run_bundle(
        run_bundle,
        ac_snapshot=ac_snapshot,
        options=options,
        project_settings=project_settings,
    )
    output = render_prepared_sld_pipeline(prepared)

    svg_text = output["svg_bytes"].decode("utf-8")

    assert output["metadata"]["engineering_v2_layout_issue_count"] == 0
    assert output["metadata"]["engineering_v2_layout_warning_count"] == 0
    assert output["engineering_v2_layout_issues"] == []
    assert "MV-3x1C-240mm2" in svg_text
    assert "LV-3P+PE-630mm2" in svg_text
    assert "DC-1x240mm2" in svg_text
    assert "Cell: LFP 3.2V/314Ah" in svg_text
    assert "MISSING:" not in svg_text
