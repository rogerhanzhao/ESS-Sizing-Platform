from __future__ import annotations

import pytest

pytest.importorskip("svgwrite")
import svgwrite

from calb_diagrams.symbol_library import draw_symbol, resolve_palette, symbol_registry
from calb_diagrams.sld_layout_engine import SldLayoutSymbol


def test_symbol_library_registry_contains_expected_symbols():
    registry = symbol_registry()
    assert "rmu" in registry
    assert "transformer" in registry
    assert "pcs" in registry
    assert "dc_busbar_pair" in registry
    assert "dc_block" in registry


def test_symbol_library_renders_without_engineering_decisions():
    palette = resolve_palette("dark")
    dwg = svgwrite.Drawing(size=("400px", "240px"), viewBox="0 0 400 240")

    symbols = [
        SldLayoutSymbol(symbol_id="frame", symbol_type="section_frame", x=10, y=10, width=180, height=80, text_lines=("Section",), meta={"frame_style": "dash"}),
        SldLayoutSymbol(symbol_id="rmu", symbol_type="rmu", x=80, y=40, width=92, height=58, text_lines=("RMU", "24 kV")),
        SldLayoutSymbol(symbol_id="tx", symbol_type="transformer", x=220, y=30, width=120, height=70, text_lines=("Transformer", "5.0 MVA")),
        SldLayoutSymbol(symbol_id="pcs", symbol_type="pcs", x=40, y=130, width=110, height=70, text_lines=("PCS-1", "1250 kW")),
        SldLayoutSymbol(symbol_id="dcpair", symbol_type="dc_busbar_pair", x=180, y=150, width=120, height=22, text_lines=("DC BUSBAR A", "DC BUSBAR B")),
        SldLayoutSymbol(symbol_id="block", symbol_type="dc_block", x=310, y=120, width=70, height=80, text_lines=("DC Block #1", "5.106 MWh")),
    ]

    for symbol in symbols:
        draw_symbol(dwg, symbol, palette)

    svg_text = dwg.tostring()
    assert "Section" in svg_text
    assert "RMU" in svg_text
    assert "Transformer" in svg_text
    assert "PCS-1" in svg_text
    assert "DC BUSBAR A" in svg_text
    assert "DC Block #1" in svg_text
