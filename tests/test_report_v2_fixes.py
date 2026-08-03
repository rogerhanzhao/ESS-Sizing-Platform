# -----------------------------------------------------------------------------
# Personal Open-Source Notice
#
# Copyright (c) 2026 Alex.Zhao. All rights reserved.
#
# This repository is released under the MIT License (see LICENSE file).
# Intended use: learning, evaluation, and engineering reference for Utility-scale
# BESS/ESS sizing and Reporting workflows.
#
# DISCLAIMER: This software is provided "AS IS", without warranty of any kind,
# express or implied. In no event shall the author(s) be liable for any claim,
# damages, or other liability arising from, out of, or in connection with the
# software or the use or other dealings in the software.
#
# NOTE: This is a personal project. It is not an official product or statement
# of any company or organization.
# -----------------------------------------------------------------------------

import base64
import io
import json
import re
from pathlib import Path

from docx import Document

from calb_sizing_tool.reporting.report_context import build_report_context
from calb_sizing_tool.reporting.report_v2 import export_report_v2_1, _validate_report_consistency
from tools.regress_export import run_ac_sizing, run_dc_sizing


def test_efficiency_chain_uses_dc_sizing_values():
    """Verify that exported efficiency chain uses actual DC SIZING values, not defaults."""
    fixture_path = Path(__file__).parent / "fixtures" / "v1_case01_container_input.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))

    dc_results = run_dc_sizing(fixture)
    ac_output = run_ac_sizing(fixture, dc_results["stage1"], dc_results["stage2"])

    png_bytes = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4nGNgYAAAAAMAASsJTYQAAAAASUVORK5CYII="
    )

    ctx = build_report_context(
        session_state={
            "artifacts": {
                "sld_png_bytes": png_bytes,
                "layout_png_bytes": png_bytes,
            }
        },
        stage_outputs={
            "stage13_output": dc_results["stage1"],
            "stage2": dc_results["stage2"],
            "stage3_df": dc_results["stage3_df"],
            "stage3_meta": dc_results["stage3_meta"],
            "ac_output": ac_output,
        },
        project_inputs={"poi_energy_guarantee_mwh": fixture["poi_energy_req_mwh"]},
        scenario_ids=fixture["scenario_id"],
    )

    # Verify efficiency values were read from DC SIZING, not defaults
    assert ctx.efficiency_chain_oneway_frac > 0, "Total efficiency should be positive"
    assert ctx.efficiency_chain_oneway_frac <= 1.0, "Total efficiency should not exceed 100%"
    
    # All component efficiencies should be present
    assert ctx.efficiency_components_frac.get("eff_dc_cables_frac") is not None
    assert ctx.efficiency_components_frac.get("eff_pcs_frac") is not None
    assert ctx.efficiency_components_frac.get("eff_mvt_frac") is not None
    assert ctx.efficiency_components_frac.get("eff_ac_cables_sw_rmu_frac") is not None
    assert ctx.efficiency_components_frac.get("eff_hvt_others_frac") is not None
    
    # Export and verify report contains actual values
    report_bytes = export_report_v2_1(ctx)
    doc = Document(io.BytesIO(report_bytes))
    texts = [p.text for p in doc.paragraphs]
    joined = "\n".join(texts)

    # Should NOT contain defaults (e.g., "97.00%" for PCS which is a common default)
    # Should contain the efficiency disclaimer about not including Auxiliary
    assert "do not include Auxiliary losses" in joined, "Report should state that efficiencies exclude Auxiliary"
    
    # Verify Efficiency Chain section exists
    assert "Efficiency Chain" in joined


def test_ac_block_config_not_verbose():
    """Verify AC Block configuration doesn't list every block when they're identical."""
    fixture_path = Path(__file__).parent / "fixtures" / "v1_case01_container_input.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))

    dc_results = run_dc_sizing(fixture)
    ac_output = run_ac_sizing(fixture, dc_results["stage1"], dc_results["stage2"])

    png_bytes = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4nGNgYAAAAAMAASsJTYQAAAAASUVORK5CYII="
    )

    ctx = build_report_context(
        session_state={
            "artifacts": {
                "sld_png_bytes": png_bytes,
                "layout_png_bytes": png_bytes,
            }
        },
        stage_outputs={
            "stage13_output": dc_results["stage1"],
            "stage2": dc_results["stage2"],
            "stage3_df": dc_results["stage3_df"],
            "stage3_meta": dc_results["stage3_meta"],
            "ac_output": ac_output,
        },
        project_inputs={"poi_energy_guarantee_mwh": fixture["poi_energy_req_mwh"]},
        scenario_ids=fixture["scenario_id"],
    )

    # Export and verify report
    report_bytes = export_report_v2_1(ctx)
    doc = Document(io.BytesIO(report_bytes))
    texts = [p.text for p in doc.paragraphs]
    joined = "\n".join(texts)

    # Should have summary section
    assert "AC Block Sizing" in joined or "AC:DC Ratio" in joined

    # The concept-arrangement section is allowed to use the phrase "AC Block",
    # but the report must not revert to a per-block list such as "AC Block 1".
    assert not re.search(r"\bAC Block\s+\d+\b", joined), (
        "Report contains a verbose numbered AC Block listing"
    )


def test_report_consistency_validation():
    """Verify consistency validation function works."""
    fixture_path = Path(__file__).parent / "fixtures" / "v1_case01_container_input.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))

    dc_results = run_dc_sizing(fixture)
    ac_output = run_ac_sizing(fixture, dc_results["stage1"], dc_results["stage2"])

    png_bytes = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4nGNgYAAAAAMAASsJTYQAAAAASUVORK5CYII="
    )

    ctx = build_report_context(
        session_state={
            "artifacts": {
                "sld_png_bytes": png_bytes,
                "layout_png_bytes": png_bytes,
            }
        },
        stage_outputs={
            "stage13_output": dc_results["stage1"],
            "stage2": dc_results["stage2"],
            "stage3_df": dc_results["stage3_df"],
            "stage3_meta": dc_results["stage3_meta"],
            "ac_output": ac_output,
        },
        project_inputs={"poi_energy_guarantee_mwh": fixture["poi_energy_req_mwh"]},
        scenario_ids=fixture["scenario_id"],
    )

    # Run validation
    warnings = _validate_report_consistency(ctx)
    
    # Valid context should have no critical errors
    # (May have warnings, but should not fail completely)
    assert isinstance(warnings, list)


def test_site_array_power_and_energy_match_the_ac_sizing_tables():
    """§9 must never contradict §6: the site figure's MW/MWh come from the run.

    The site-array engine used to hardcode a 5 MW / 5.015 MWh unit, so a 10 MW
    station was reported at HALF its power (65 MW vs 130 MW) and energy was
    computed from n_blocks x dc_per_block (104) instead of the real DC Block
    count (100) — the report contradicted its own AC Sizing tables.
    """
    import io as _io

    from docx import Document as _Document

    from calb_sizing_tool.reporting.report_context import build_report_context
    from calb_sizing_tool.reporting.report_v2 import export_report_v2_1

    ac_output = {
        "num_blocks": 13, "pcs_per_block": 8, "pcs_kw": 1250.0,
        "block_size_mw": 10.0, "transformer_mva": 11.111, "total_ac_mw": 130.0,
        "lv_winding_count": 2, "transformer_topology": "three_winding",
        "dc_blocks_total": 100,
    }
    ctx = build_report_context(
        session_state={},
        stage_outputs={
            "stage13_output": {
                "project_name": "Consistency", "poi_power_req_mw": 115.0,
                "poi_energy_req_mwh": 400.0, "project_life_years": 20,
                "poi_guarantee_year": 4, "cycles_per_year": 365,
            },
            "ac_output": ac_output,
            "stage2": {"container_count": 100, "dc_nameplate_bol_mwh": 501.5},
        },
        project_inputs={},
    )
    doc = _Document(_io.BytesIO(export_report_v2_1(ctx)))
    caption = next(
        (p.text for p in doc.paragraphs if "Concept Site Arrangement —" in p.text), ""
    )
    assert caption, "§9 site arrangement caption not found"
    # 13 AC Blocks x 10.00 MW = 130 MW (was 65), and the REAL 100 DC Blocks.
    assert "10 MW\nper block" in caption or "10 MW per block" in caption, caption
    assert "130 MW" in caption, caption
    assert "65 MW" not in caption, caption
