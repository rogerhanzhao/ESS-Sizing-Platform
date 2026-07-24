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

"""Standard typical transformer impedance (Uk%) by voltage class.

Why this exists
---------------
Transformer impedance (Uk% / percent impedance) is NOT a sizing parameter — the
energy/power sizing chain never uses it. It only appears on the SLD transformer
schedule and in fault-current work. In practice the project-specific declared
impedance is a grid-interconnection filing value the owner usually does not have
at concept stage, so requiring it would block the SLD for no sizing benefit.

Instead, when no project-declared value exists, the SLD uses a STANDARD TYPICAL
impedance selected by high-voltage class. The values below follow the IEEE
liquid-immersed power-transformer standards basis (IEEE Std C57.12.00 §5.8,
which refers impedance to the product standards; IEEE Std C57.12.10 standard
impedance values for two-winding power transformers). They are typical class
values, NOT a manufacturer-guaranteed or project-declared figure, and every use
must be labelled as such so a typical is never mistaken for a filed value.
"""

from __future__ import annotations

STANDARD_IMPEDANCE_BASIS = "typical per IEEE C57.12.00/C57.12.10 (by HV class), not project-declared"

# (upper_hv_kv_inclusive, percent_impedance). Ordered ascending by HV class.
# Two-winding liquid-immersed power transformer standard/typical impedance.
_IMPEDANCE_BY_HV_CLASS: tuple[tuple[float, float], ...] = (
    (15.0, 5.75),
    (25.0, 5.75),
    (34.5, 6.0),
    (46.0, 6.5),
    (69.0, 7.0),
)
_DEFAULT_IMPEDANCE_PERCENT = 7.0


def standard_impedance_percent(mv_voltage_kv: float | None) -> float:
    """Return the standard typical Uk% for the given MV (high-voltage) class.

    Falls back to the highest defined class value when the voltage is unknown or
    above the tabulated range.
    """
    try:
        hv = float(mv_voltage_kv) if mv_voltage_kv is not None else None
    except (TypeError, ValueError):
        hv = None
    if hv is None or hv <= 0:
        return _DEFAULT_IMPEDANCE_PERCENT
    for upper_kv, percent in _IMPEDANCE_BY_HV_CLASS:
        if hv <= upper_kv + 1e-9:
            return percent
    return _DEFAULT_IMPEDANCE_PERCENT


__all__ = ["STANDARD_IMPEDANCE_BASIS", "standard_impedance_percent"]
