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

from calb_diagrams.specs import LayoutBlockSpec, SldGroupSpec, build_layout_block_spec, build_sld_group_spec

try:  # pragma: no cover - optional dependency
    from calb_diagrams.layout_block_renderer import render_layout_block_svg
except Exception:  # pragma: no cover
    render_layout_block_svg = None

try:  # pragma: no cover - optional dependency
    from calb_diagrams.sld_pro_renderer import render_sld_pro_svg, render_sld_svg
except Exception:  # pragma: no cover
    render_sld_pro_svg = None
    render_sld_svg = None

__all__ = [
    "LayoutBlockSpec",
    "SldGroupSpec",
    "build_layout_block_spec",
    "build_sld_group_spec",
    "render_layout_block_svg",
    "render_sld_pro_svg",
    "render_sld_svg",
]
