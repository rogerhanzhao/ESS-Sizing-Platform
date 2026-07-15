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

from calb_diagrams.layout_block_renderer import render_layout_block_svg
from calb_diagrams.specs import build_layout_block_spec


def test_layout_block_smoke(tmp_path: Path):
    labels = {
        "block_title": "Block {index}",
        "bess_range_text": "BESS {start}~{end}",
        "skid_text": "PCS&MVT SKID",
        "skid_subtext": "33.0 kV / 690 V, 5.0 MVA",
    }
    spec = build_layout_block_spec(
        ac_output={},
        block_indices_to_render=[1, 2],
        labels=labels,
        arrangement="2x2",
        show_skid=True,
    )
    svg_path = tmp_path / "layout_block.svg"
    result_path, warning = render_layout_block_svg(spec, svg_path)
    assert result_path is not None
    assert warning is None or isinstance(warning, str)

    svg_text = svg_path.read_text(encoding="utf-8")
    assert svg_text.strip()
    assert "Block 1" in svg_text
    assert "PCS&amp;MVT SKID" in svg_text
    assert "Transformer" in svg_text
    # Every container carries its own tag inside its outline (no floating
    # "DC Block" labels that collided with row gaps / dimension lines).
    assert "BESS-01" in svg_text
    assert "BESS-04" in svg_text
    assert ">DC Block<" not in svg_text
    # Overall footprint dimensions and the container-size note are present.
    assert "DC container 6.058 m x 2.438 m" in svg_text
