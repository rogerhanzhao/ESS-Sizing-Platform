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

import importlib.util
from typing import Dict


def _has_module(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def check_dependencies() -> Dict[str, bool]:
    return {
        "svgwrite": _has_module("svgwrite"),
        "cairosvg": _has_module("cairosvg"),
        # pypowsybl was probed for the IIDM SLD stack, retired 2026-08-06.
        # Reporting on a library nothing can use is noise, not diagnostics.
    }
