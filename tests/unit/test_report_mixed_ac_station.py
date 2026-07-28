"""End-to-end: a mixed AC Block station reaches the report as a head/tail schedule.

Uniform stations must NOT show the mixed schedule (one code path, but the extra
table appears only when it adds information).
"""
from __future__ import annotations

import io

from docx import Document

from calb_sizing_tool.reporting.report_context import build_report_context
from calb_sizing_tool.reporting.report_v2 import export_report_v2_1
from calb_sizing_tool.services.ac_mixed_station import summarize_ac_block_rows


def _report_text(ac_output: dict) -> str:
    ctx = build_report_context(
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
    # The tail is tied back to the DC container + cabinet tail for coherence.
    assert "counterpart of the DC container + cabinet tail" in text


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
