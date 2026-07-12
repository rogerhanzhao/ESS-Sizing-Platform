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
from pathlib import Path

from docx import Document

from calb_sizing_tool.reporting.report_context import build_report_context
from calb_sizing_tool.reporting.report_v2 import export_report_v2_1
from tools.regress_export import run_ac_sizing, run_dc_sizing


def test_report_v2_smoke():
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

    report_bytes = export_report_v2_1(ctx)
    doc = Document(io.BytesIO(report_bytes))
    texts = [p.text for p in doc.paragraphs]
    joined = "\n".join(texts)

    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}

    def _has_header_drawing(section) -> bool:
        try:
            return bool(section.header._element.xpath(".//w:drawing", namespaces=ns))
        except TypeError:
            return bool(section.header._element.xpath(".//w:drawing"))

    has_logo = any(_has_header_drawing(section) for section in doc.sections)

    assert sum("Executive Summary" in text for text in texts) == 1
    assert sum("Inputs & Assumptions" in text for text in texts) == 1
    assert any("DC Energy Sizing" in text for text in texts)
    assert any("Single Line Diagram" in text for text in texts)
    assert any("Typical AC Block Arrangement" in text for text in texts)
    assert "Appendix" not in joined
    assert ".xlsx" not in joined
    assert "314 Ah cell database" not in joined
    assert has_logo
    assert len(doc.inline_shapes) >= 2
