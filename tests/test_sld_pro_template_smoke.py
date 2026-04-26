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

from pathlib import Path

import pytest

pytest.importorskip("svgwrite")

from calb_diagrams.specs import build_sld_group_spec
from calb_diagrams.sld_pro_renderer import render_sld_pro_svg


def test_sld_pro_template_smoke(tmp_path: Path):
    stage13_output = {
        "project_name": "Template Test",
        "poi_nominal_voltage_kv": 33.0,
        "dc_block_total_qty": 6,
    }
    ac_output = {
        "num_blocks": 2,
        "pcs_per_block": 2,
        "mv_voltage_kv": 33.0,
        "lv_voltage_v": 690.0,
        "block_size_mw": 5.0,
        "pcs_kw": 2500.0,
        "transformer_mva": 5.0,
        "pcs_count_by_block": [2, 2],
        "dc_blocks_total_by_block": [3, 3],
        "dc_blocks_per_feeder_by_block": [[2, 1], [1, 2]],
        "dc_allocation_plan": [
            {"ac_block_index": 1, "dc_blocks_total": 3, "feeder_allocations": [2, 1]},
            {"ac_block_index": 2, "dc_blocks_total": 3, "feeder_allocations": [1, 2]},
        ],
    }
    sld_inputs = {
        "mv_nominal_kv_ac": 33.0,
        "pcs_lv_voltage_v_ll": 690.0,
        "transformer_rating_mva": 5.0,
        "pcs_rating_each_kw": 2500.0,
        "dc_block_energy_mwh": 5.106,
        "dc_blocks_per_feeder": [2, 1],
        "dc_block_voltage_v": 1500.0,
        "mv_labels": {"to_switchgear": "To Switchgear", "to_other_rmu": "To Other RMU"},
        "rmu": {
            "rated_kv": 33.0,
            "rated_a": 630,
            "short_circuit_ka_3s": 25.0,
            "ct_ratio": "200/1",
            "ct_class": "5P20",
            "ct_va": 10.0,
        },
        "transformer": {"vector_group": "Dyn11", "uk_percent": 7.0, "cooling": "ONAN"},
        "lv_busbar": {"rated_a": 6300.0, "short_circuit_ka": 25.0},
        "cables": {"mv_cable_spec": "TBD", "lv_cable_spec": "TBD", "dc_cable_spec": "TBD"},
        "dc_fuse": {"fuse_spec": "DC isolator/fuse"},
    }

    spec = build_sld_group_spec(stage13_output, ac_output, {}, sld_inputs, group_index=1)
    svg_path = tmp_path / "sld_pro.svg"
    result_path, warning = render_sld_pro_svg(spec, svg_path)
    assert result_path is not None
    assert warning is None or isinstance(warning, str)

    svg_text = svg_path.read_text(encoding="utf-8")
    assert svg_text.strip()
    assert "PCS&amp;MVT SKID (AC Block)" in svg_text
    assert "Battery Storage Bank" in svg_text
    assert "RMU / MV Switchgear" in svg_text
    assert "Ring In" in svg_text
    assert "Transformer Feeder" in svg_text
    assert "Ring Out" in svg_text
    assert "DC Interface" in svg_text
    assert "DC Isolator/Fuse" in svg_text
    assert "DC Block Allocation" in svg_text
    assert "DC BUSBAR" not in svg_text
    assert "DC Combiner" not in svg_text
