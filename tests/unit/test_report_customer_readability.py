from __future__ import annotations

import io
from docx import Document

from calb_sizing_tool.reporting.customer_presentation import customer_text, issue_date, quantity_label, spacing_basis_text
from calb_sizing_tool.reporting.report_context import build_report_context
from calb_sizing_tool.reporting.report_v2 import export_report_v2_1

UUID = "11111111-2222-4333-8444-555555555555"


def test_document_shows_alternative_without_internal_identifiers(tmp_path, monkeypatch):
    monkeypatch.setenv("CALB_OUTPUTS_DIR", str(tmp_path))
    ctx = build_report_context({}, {
        "stage13_output": dict(project_name="Readability", poi_power_req_mw=10.8,
            poi_energy_req_mwh=43.2, project_life_years=20, cycles_per_year=365, poi_guarantee_year=0),
        "stage2": {"container_count": 10},
        "ac_output": dict(num_blocks=3, pcs_per_block=4, pcs_kw=1250, block_size_mw=5,
                          dc_blocks_total=10, pcs_count_total=10),
    }, {})
    ctx.run_id = UUID
    ctx.ac_run_id = UUID
    ctx.ac_alternative_id = UUID
    ctx.ac_alternative_label = "B"
    ctx.report_generated_at = "2026-10-19 11:50 UTC+0"
    doc = Document(io.BytesIO(export_report_v2_1(ctx)))
    text = "\n".join(p.text for p in doc.paragraphs)
    text += "\n".join(c.text for t in doc.tables for r in t.rows for c in r.cells)
    assert "AC Alternative: B" in text
    assert "Document Information" in text and "19 Oct 2026" in text
    assert UUID not in text and "AC run" not in text
    assert "database" not in text.lower() and "Tool Version" not in text
    assert "contractually" not in text and "1 AC Blocks" not in text
    assert "Owner ruling" not in text
    assert ctx.ac_alternative_id == UUID and ctx.run_id == UUID


def test_customer_labels_keep_engineering_identifiers_and_remove_database_ids():
    assert customer_text(f"B (AC run {UUID})") == "B"
    assert customer_text(UUID) == "—"
    assert customer_text("AC-01 / CALB 5MWh 20ft Container") == "AC-01 / CALB 5MWh 20ft Container"
    assert customer_text("Field trial (run 2)") == "Field trial (run 2)"
    assert issue_date("2026-10-19 11:50 UTC+0") == "19 Oct 2026"
    assert quantity_label(1,"AC Block") == "1 AC Block"
    assert quantity_label(2,"AC Block") == "2 AC Blocks"
    assert spacing_basis_text("Owner ruling 2026-08-03 — same clearance") == "Concept design assumption — same clearance"
