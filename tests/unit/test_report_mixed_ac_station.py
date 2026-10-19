"""End-to-end: a mixed AC Block station reaches the report as a head/tail schedule.

Uniform stations must NOT show the mixed schedule (one code path, but the extra
table appears only when it adds information).
"""
from __future__ import annotations

import io

from docx import Document

from calb_sizing_tool.reporting.report_context import build_report_context
from calb_sizing_tool.reporting.report_v2 import (
    _mixed_head_entry,
    _arrangement_shape,
    _representative_dc_per_ac,
    export_report_v2_1,
)
from calb_sizing_tool.services.ac_mixed_station import summarize_ac_block_rows


def _build_ctx(ac_output: dict):
    return build_report_context(
        session_state={},
        stage_outputs={
            "stage13_output": {
                "project_name": "Mixed Station",
                "poi_power_req_mw": 45.0,
                "poi_energy_req_mwh": 180.0,
                "project_life_years": 20,
                "poi_guarantee_year": 0,
                "cycles_per_year": 365,
            },
            "ac_output": ac_output,
            "stage2": {"container_count": 36},
        },
        project_inputs={"grid_power_factor": 0.9},
    )


def _report_text(ac_output: dict) -> str:
    ctx = _build_ctx(ac_output)
    doc = Document(io.BytesIO(export_report_v2_1(ctx)))
    parts = [p.text for p in doc.paragraphs]
    for table in doc.tables:
        for row in table.rows:
            parts.extend(cell.text for cell in row.cells)
    return "\n".join(parts)


def _mixed_ac_output() -> dict:
    # 4 head blocks (10 MW, 8x1250, 8 DC) + 1 tail (5 MW, 4x1250, 4 DC) = 36 DC.
    rows = [{"pcs_count": 8, "pcs_kw": 1250, "dc_blocks": 8} for _ in range(4)]
    rows.append({"pcs_count": 4, "pcs_kw": 1250, "dc_blocks": 4})
    breakdown = summarize_ac_block_rows(rows)
    return {
        "selected_ratio": "1:8",
        "num_blocks": len(rows),
        "pcs_per_block": 8,
        "pcs_count_by_block": [r["pcs_count"] for r in rows],
        "pcs_kw": 1250,
        "block_size_mw": 10.0,
        "total_ac_mw": 45.0,
        "dc_blocks_per_ac": [r["dc_blocks"] for r in rows],
        "dc_blocks_total": 36,
        "grid_power_factor": 0.9,
        "transformer_mva": 10.0 / 0.9,
        "ac_block_mixed": True,
        "ac_block_rows": rows,
        "ac_block_breakdown": breakdown,
    }


def test_mixed_station_renders_head_and_tail_schedule():
    text = _report_text(_mixed_ac_output())
    assert "Mixed AC Block Station Schedule" in text
    assert "Head" in text and "Tail" in text
    # Tail model (5 MW, 4 x 1250) and head model (10 MW, 8 x 1250) both present.
    assert "10.00 MW" in text
    assert "5.00 MW" in text
    # AC model mixing does not imply a cabinet is present on the DC side.
    assert "irrespective of the DC equipment form" in text
    assert "counterpart of the DC container + cabinet tail" not in text


def test_uniform_station_has_no_mixed_schedule():
    rows = [{"pcs_count": 8, "pcs_kw": 1250, "dc_blocks": 8} for _ in range(5)]
    breakdown = summarize_ac_block_rows(rows)
    ac_output = {
        "selected_ratio": "1:8",
        "num_blocks": 5,
        "pcs_per_block": 8,
        "pcs_count_by_block": [8] * 5,
        "pcs_kw": 1250,
        "block_size_mw": 10.0,
        "total_ac_mw": 50.0,
        "dc_blocks_per_ac": [8] * 5,
        "dc_blocks_total": 40,
        "grid_power_factor": 0.9,
        "transformer_mva": 10.0 / 0.9,
        "ac_block_mixed": False,
        "ac_block_rows": rows,
        "ac_block_breakdown": breakdown,
    }
    text = _report_text(ac_output)
    assert "Mixed AC Block Station Schedule" not in text


def test_representative_dc_per_ac_uses_head_not_average_for_mixed():
    # 4 × 8-DC head + 1 × 4-DC tail = 36 DC over 5 blocks. The average rounds to
    # 7 (a block that exists nowhere); the representative must be the head's 8.
    ctx = _build_ctx(_mixed_ac_output())
    head = _mixed_head_entry(ctx)
    assert head is not None and head["role"] == "Head"
    assert _representative_dc_per_ac(ctx) == 8


def test_representative_dc_per_ac_is_average_for_uniform():
    rows = [{"pcs_count": 8, "pcs_kw": 1250, "dc_blocks": 8} for _ in range(4)]
    rows.append({"pcs_count": 8, "pcs_kw": 1250, "dc_blocks": 4})  # uneven DC, one model
    ac_output = {
        "selected_ratio": "1:8",
        "num_blocks": 5,
        "pcs_per_block": 8,
        "pcs_count_by_block": [8] * 5,
        "pcs_kw": 1250,
        "block_size_mw": 10.0,
        "total_ac_mw": 50.0,
        "dc_blocks_per_ac": [8, 8, 8, 8, 4],
        "dc_blocks_total": 36,
        "grid_power_factor": 0.9,
        "transformer_mva": 10.0 / 0.9,
        "ac_block_mixed": False,
        "ac_block_rows": rows,
        "ac_block_breakdown": summarize_ac_block_rows(rows),
    }
    ctx = _build_ctx(ac_output)
    assert _mixed_head_entry(ctx) is None
    assert _representative_dc_per_ac(ctx) == round(36 / 5)  # 7 (average), single model


def test_mixed_report_draws_head_block_and_states_real_whole_site_power():
    text = _report_text(_mixed_ac_output())
    # §8/§9 disclose the representative head block for a mixed station.
    assert "representative Head AC Block" in text
    # Whole-site power is the real 45 MW head + tail total, not the uniform
    # over-count of 5 blocks × 10 MW head = 50 MW.
    assert "50 MW / " not in text


def test_mixed_report_is_concept_draft_and_not_product_backed():
    text = _report_text(_mixed_ac_output())
    # Issue 3: the mixed schedule is explicitly marked concept/draft.
    assert "Concept / draft" in text
    # Issue 1: with no bound product nameplate the transformer basis is an
    # estimate, never a "product datasheet" nameplate falsely attributed per block.
    assert "product datasheet" not in text


def _belize_ac_output():
    rows = [
        {"pcs_count": 4, "pcs_kw": 1250, "dc_blocks": 4},
        {"pcs_count": 4, "pcs_kw": 1250, "dc_blocks": 4},
        {"pcs_count": 2, "pcs_kw": 1250, "dc_blocks": 2},
    ]
    return {
        "selected_ratio": "1:4", "num_blocks": 3, "pcs_per_block": 4,
        "pcs_count_by_block": [4, 4, 2], "pcs_count_total": 10,
        "pcs_kw": 1250, "block_size_mw": 5.0, "total_ac_mw": 12.5,
        "dc_blocks_per_ac": [4, 4, 2], "dc_blocks_total": 10,
        "grid_power_factor": .9, "transformer_mva": 5 / .9,
        "ac_block_mixed": True, "ac_block_rows": rows,
        "ac_block_breakdown": summarize_ac_block_rows(rows),
    }


def _belize_ctx(ac_output=None):
    ctx = build_report_context(
        session_state={},
        stage_outputs={
            "stage13_output": {
                "project_name": "Belize mixed", "poi_power_req_mw": 10.8,
                "poi_energy_req_mwh": 43.2, "project_life_years": 20,
                "poi_guarantee_year": 0, "cycles_per_year": 365,
                "dc_total_energy_mwh": 50.16,
            },
            "ac_output": ac_output or _belize_ac_output(),
            "stage2": {"container_count": 10, "total_energy_mwh": 50.16},
        }, project_inputs={"grid_power_factor": .9},
    )
    ctx.poi_usable_energy_mwh_at_guarantee_year = 44.72
    ctx.dc_total_energy_mwh = 50.16
    return ctx


def _doc_text(ctx):
    doc = Document(io.BytesIO(export_report_v2_1(ctx)))
    return "\n".join(
        [p.text for p in doc.paragraphs]
        + [cell.text for table in doc.tables for row in table.rows for cell in row.cells]
    )


def test_belize_mixed_allocation_consumes_saved_4_4_2_not_balanced_4_3_3():
    ctx = _belize_ctx()
    assert ctx.dc_blocks_allocation == [
        {"dc_blocks_per_ac_block": 4, "ac_blocks_count": 2},
        {"dc_blocks_per_ac_block": 2, "ac_blocks_count": 1},
    ]
    text = _doc_text(ctx)
    assert "4 DC Blocks per AC Block × 2 AC Blocks" in text
    assert "2 DC Blocks per AC Block × 1 AC Blocks" in text
    assert "3 DC Blocks per AC Block" not in text


def test_belize_mixed_report_states_models_totals_and_figure_scope():
    text = _doc_text(_belize_ctx())
    assert "2 × 5.00 MW (4 × 1250 kW PCS per block) + 1 × 2.50 MW" in text
    assert "= 12.50 MW installed PCS nameplate" in text
    assert "AC-01, AC-02" in text and "AC-03" in text
    assert "4 per block; 8 total" in text and "2 per block; 2 total" in text
    assert "5.00 / 10.00" in text and "2.50 / 2.50" in text
    assert "Transformer Rating (representative Head model)" in text
    assert "Representative Head Size (MW)" in text
    assert "Tail AC Blocks are not included in this drawing" in text
    assert "Tail AC Blocks are not shown" in text
    assert "not the complete station SLD" in text
    assert "PCS nameplate is the installed converter rating" in text
    assert "POI requirement is 10.80 MW" in text


def test_mixed_report_exposes_unconfirmed_frequency_without_changing_saved_input():
    ctx = _belize_ctx()
    ctx.project_inputs.update(poi_frequency_hz=None, saved_ac_frequency_hz=50.0)
    text = _doc_text(ctx)
    assert "POI frequency remains TBD" in text
    assert "selected AC input uses 50 Hz" in text
    assert ctx.project_inputs["poi_frequency_hz"] is None


def test_belize_mixed_site_overview_does_not_repeat_false_head_footprints():
    text = _doc_text(_belize_ctx())
    assert "equipment composition overview, not a physical site layout" in text
    assert "site envelope and land area are not established" in text
    assert "single representative project group of 3" not in text
    assert "Site land area (equipment + access only)" not in text
    assert "12 MW /" not in text and "15 MW /" not in text
    assert "Site Envelope (concept)" not in text


def test_mixed_rows_without_marker_or_breakdown_still_report_actual_allocation():
    ac = _belize_ac_output()
    ac.pop("ac_block_mixed")
    ac.pop("ac_block_breakdown")
    ctx = _belize_ctx(ac)
    assert _mixed_head_entry(ctx)["pcs_count"] == 4
    assert ctx.dc_blocks_allocation[0]["ac_blocks_count"] == 2
    assert "Mixed AC Block Station Schedule" in _doc_text(ctx)


def test_uniform_uneven_fill_keeps_existing_report_path():
    ac = _belize_ac_output()
    ac["ac_block_rows"] = [dict(r, pcs_count=4) for r in ac["ac_block_rows"]]
    ac["pcs_count_by_block"] = [4, 4, 4]
    ac["ac_block_mixed"] = False
    ac["ac_block_breakdown"] = summarize_ac_block_rows(ac["ac_block_rows"])
    ctx = _belize_ctx(ac)
    assert _mixed_head_entry(ctx) is None
    assert ctx.dc_blocks_allocation == [
        {"dc_blocks_per_ac_block": 4, "ac_blocks_count": 1},
        {"dc_blocks_per_ac_block": 3, "ac_blocks_count": 2},
    ]
    text = _doc_text(ctx)
    assert "Mixed AC Block Station Schedule" not in text
    assert "equipment composition overview" not in text


def test_mixed_arrangement_uses_saved_head_rows_not_stale_model_or_first_tail():
    ac = _belize_ac_output()
    ac["ac_block_model_name"] = "4.00 MW AC Block - 2 x 2000 kW PCS"
    ac["ac_block_rows"] = [ac["ac_block_rows"][2], *ac["ac_block_rows"][:2]]
    ac["pcs_count_by_block"] = [2, 4, 4]
    ac["dc_blocks_per_ac"] = [2, 4, 4]
    shape = _arrangement_shape(_belize_ctx(ac))
    assert shape.block_index == 2
    assert shape.pcs_count == 4 and shape.dc_blocks == 4
    assert shape.block_power_mw == 5.0
    assert "5.00 MW" in shape.model_name
    assert "4 × 1250 kW PCS" in shape.model_name
    assert "2000" not in shape.model_name


def test_legacy_mixed_mirrors_use_per_block_dc_array_when_ratio_is_scalar():
    ac = _belize_ac_output()
    ac.pop("ac_block_rows")
    ac.pop("ac_block_mixed")
    ac.pop("ac_block_breakdown")
    ac["dc_blocks_per_ac"] = 4
    ac["dc_blocks_total_by_block"] = [4, 4, 2]
    ctx = _belize_ctx(ac)
    assert ctx.dc_blocks_allocation[0] == {
        "dc_blocks_per_ac_block": 4, "ac_blocks_count": 2,
    }
    assert "= 12.50 MW installed PCS nameplate" in _doc_text(ctx)
