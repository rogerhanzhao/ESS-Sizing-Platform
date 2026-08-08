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

import io

from docx import Document

from calb_sizing_tool.config import DC_DATA_PATH
from calb_sizing_tool.reporting import export_docx
from calb_sizing_tool.ui import dc_view


def _doc_from_bytes(data):
    if hasattr(data, "getvalue"):
        data = data.getvalue()
    return Document(io.BytesIO(data))


def _paragraph_texts(doc: Document):
    return [p.text for p in doc.paragraphs]


def _strip_timestamp_lines(texts):
    cleaned = []
    for text in texts:
        lines = [line for line in text.splitlines() if not line.startswith("Date:")]
        cleaned.append("\n".join(lines))
    return cleaned


def _build_stage1():
    defaults, df_blocks, df_soh_profile, df_soh_curve, df_rte_profile, df_rte_curve = dc_view.load_data(DC_DATA_PATH)
    inputs = {
        "project_name": "Unit Test Project",
        "poi_power_req_mw": 100.0,
        "poi_energy_req_mwh": 400.0,
        "eff_dc_cables": 99.5,
        "eff_pcs": 98.5,
        "eff_mvt": 99.5,
        "eff_ac_cables_sw_rmu": 99.2,
        "eff_hvt_others": 100.0,
        "sc_time_months": 3,
        "dod_pct": 97.0,
        "dc_round_trip_efficiency_pct": 94.0,
        "project_life_years": 20,
        "cycles_per_year": 365,
        "poi_guarantee_year": 0,
    }
    stage1 = dc_view.run_stage1(inputs, defaults)
    return stage1, df_blocks, df_soh_profile, df_soh_curve, df_rte_profile, df_rte_curve


def test_setup_header_callable():
    assert callable(export_docx._setup_header)


def test_dc_report_unchanged_paragraphs():
    stage1, df_blocks, df_soh_profile, df_soh_curve, df_rte_profile, df_rte_curve = _build_stage1()
    selected = "container_only"

    s2, s3_df, s3_meta, iter_count, poi_g, converged = dc_view.size_with_guarantee(
        stage1,
        selected,
        df_blocks,
        df_soh_profile,
        df_soh_curve,
        df_rte_profile,
        df_rte_curve,
        k_max=dc_view.K_MAX_FIXED,
    )
    results = {selected: (s2, s3_df, s3_meta, iter_count, poi_g, converged)}
    report_order = [(selected, selected.replace("_", " ").title())]

    baseline = dc_view.build_report_bytes(stage1, results, report_order)
    baseline_doc = _doc_from_bytes(baseline)

    dc_output = {"stage1": stage1, "selected_scenario": selected}
    updated = export_docx.create_dc_report(dc_output, {})
    updated_doc = _doc_from_bytes(updated)

    baseline_texts = _strip_timestamp_lines(_paragraph_texts(baseline_doc))
    updated_texts = _strip_timestamp_lines(_paragraph_texts(updated_doc))
    assert baseline_texts == updated_texts


if __name__ == "__main__":
    import pytest

    pytest.main([__file__])
