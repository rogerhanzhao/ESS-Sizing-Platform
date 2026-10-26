"""Compact customer labels retain every actual mixed-AC group assignment."""
from copy import deepcopy
import io
import re

from docx import Document
import pytest

from calb_sizing_tool.reporting.report_context import build_report_context
from calb_sizing_tool.reporting.report_v2 import _compact_ac_block_labels, export_report_v2_1


def _expanded_labels(text):
    indices = []
    for start, end in re.findall(r"AC-(\d+)(?:–AC-(\d+))?", text):
        indices.extend(range(int(start), int(end) + 1) if end else [int(start)])
    return indices


@pytest.mark.parametrize("indices,expected", [
    ([], ""),
    ([45], "AC-45"),
    ([1, 2], "AC-01, AC-02"),
    (list(range(1, 45)), "AC-01–AC-44"),
    ([1, 2, 3, 5, 7, 8, 9, 11, 12], "AC-01–AC-03, AC-05, AC-07–AC-09, AC-11, AC-12"),
    ([4, 5, 6, 1, 2, 8], "AC-04–AC-06, AC-01, AC-02, AC-08"),
    ([98, 99, 100, 102], "AC-98–AC-100, AC-102"),
])
def test_compact_labels_preserve_exact_recorded_groups_and_order(indices, expected):
    original = list(indices)
    label = _compact_ac_block_labels(indices)
    assert label == expected
    assert _expanded_labels(label) == indices
    assert indices == original


@pytest.mark.parametrize("larger_groups", [(45,), (6, 45), (6, 14, 45)])
def test_both_report_schedules_keep_actual_45_group_model_membership(
        tmp_path, monkeypatch, larger_groups):
    monkeypatch.setenv("CALB_OUTPUTS_DIR", str(tmp_path))
    rows = [dict(pcs_count=2, pcs_kw=1500 if index in larger_groups else 1250, dc_blocks=2)
            for index in range(1, 46)]
    total_mw = sum(row["pcs_count"] * row["pcs_kw"] / 1000 for row in rows)
    ac = dict(num_blocks=45, pcs_per_block=2, pcs_kw=1250, block_size_mw=2.5,
              pcs_count_total=90, pcs_count_by_block=[2] * 45,
              dc_blocks_per_ac=[2] * 45, dc_blocks_total=90,
              total_ac_mw=total_mw, grid_power_factor=.9,
              transformer_mva=2.5 / .9, ac_block_mixed=True, ac_block_rows=rows)
    ctx = build_report_context({}, {
        "stage13_output": dict(project_name="Saved mixed allocation QA", poi_power_req_mw=100,
            poi_energy_req_mwh=400, project_life_years=20, cycles_per_year=365, poi_guarantee_year=0),
        "stage2": dict(container_count=90, dc_nameplate_bol_mwh=451.440),
        "ac_output": ac,
    }, {"grid_power_factor": .9})
    before = deepcopy(ac)
    doc = Document(io.BytesIO(export_report_v2_1(ctx)))
    tables = {tuple(cell.text for cell in table.rows[0].cells): table for table in doc.tables}
    station = tables[("Model / Blocks", "Qty", "PCS per Block", "MW Each / Total",
                      "DC Blocks", "PCS Total", "TX Each (est.)")]
    site = tables[("AC Blocks", "Model", "Qty", "PCS Nameplate Each", "DC Blocks Total")]
    expected = {
        "Tail": [index for index in range(1, 46) if index not in larger_groups],
        "Head": list(larger_groups),
    }

    # Decode both customer schedules and reconcile them to the original saved rows.
    for row in station.rows[1:-1]:
        cells = [cell.text for cell in row.cells]
        role = cells[0].split(" · ", 1)[0]
        actual = _expanded_labels(cells[0])
        assert actual == expected[role]
        assert int(cells[1]) == len(actual)
        rating = 1500 if role == "Head" else 1250
        assert cells[2] == f"2 × {rating} kW"
        assert cells[3] == f"{2 * rating / 1000:.2f} / {len(actual) * 2 * rating / 1000:.2f}"
        assert cells[4] == f"2 per block; {2 * len(actual)} total"
    for row in site.rows[1:]:
        cells = [cell.text for cell in row.cells]
        assert _expanded_labels(cells[0]) == expected[cells[1]]
        assert int(cells[2]) == len(expected[cells[1]])
        assert int(cells[4]) == 2 * len(expected[cells[1]])
    totals = [cell.text for cell in station.rows[-1].cells]
    assert totals[1] == "45" and totals[3] == f"— / {total_mw:.2f}"
    assert totals[4] == "90 total" and totals[5] == "90"
    assert ctx.ac_output == before and ac == before
