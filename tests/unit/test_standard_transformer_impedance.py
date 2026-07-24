"""Standard typical transformer impedance (Uk%) by HV class.

Uk% is not a sizing parameter and is usually an unfiled grid-interconnection
value at concept stage, so the SLD uses a standard typical by voltage class
(IEEE C57.12.00/C57.12.10 basis) rather than blocking on a declared value.
"""
from __future__ import annotations

import pytest

from calb_sizing_tool.sld.standard_transformer_impedance import (
    STANDARD_IMPEDANCE_BASIS,
    standard_impedance_percent,
)


@pytest.mark.parametrize(
    "hv_kv, expected",
    [
        (11.0, 5.75),
        (15.0, 5.75),
        (25.0, 5.75),
        (34.5, 6.0),
        (33.0, 6.0),
        (46.0, 6.5),
        (69.0, 7.0),
    ],
)
def test_standard_impedance_by_class(hv_kv, expected):
    assert standard_impedance_percent(hv_kv) == expected


def test_unknown_or_zero_voltage_falls_back():
    assert standard_impedance_percent(None) == 7.0
    assert standard_impedance_percent(0) == 7.0
    assert standard_impedance_percent(500.0) == 7.0  # above tabulated range


def test_basis_label_marks_it_typical():
    assert "typical" in STANDARD_IMPEDANCE_BASIS.lower()
    assert "not project-declared" in STANDARD_IMPEDANCE_BASIS.lower()
