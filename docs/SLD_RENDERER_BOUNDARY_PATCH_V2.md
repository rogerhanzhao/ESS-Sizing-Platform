# SLD Renderer Boundary Patch V2

Scope: Phase 4 renderer boundary and template patch.

## Boundary Rule

The deterministic SLD renderer entrypoint remains:

```python
render_sld_svg(topology, layout_profile, theme, out_svg, out_png=None)
```

It consumes:

- authoritative `SldTopology`
- layout profile
- theme

It does not consume:

- Streamlit session
- raw AC output dict
- raw DC summary dict
- Stage 13 dict
- UI override dict

## What Changed

Phase 4 changed the layout symbols produced by `calb_diagrams/sld_layout_engine.py` and rendered by `calb_diagrams/symbol_library.py`.

New visible symbols:

- `mv_switchgear`
- `dc_interface`

Removed from the engineering-readable visible template:

- top-level `mv-busbar` symbol
- `DC BUSBAR` rendered below PCS
- `dc_busbar_pair` / floating DC+ and DC- rails

Existing compatibility symbols remain in the library so older or compact callers do not fail unexpectedly, but the engineering-readable template no longer uses them for the current SLD.

## What Did Not Change

The renderer still does not compute:

- PCS count
- PCS rating
- transformer rating
- DC block allocation
- DC blocks per feeder

Those values arrive through the authoritative builder and topology.

## Tests

Phase 4 regression coverage includes:

- `tests/unit/test_sld_layout_engine.py`
- `tests/unit/test_symbol_library.py`
- `tests/unit/test_sld_renderer_pure_render_only.py`
- `tests/integration/test_sld_render_regression.py`
- `tests/integration/test_sld_topology_regression.py`

The tests verify:

- the engineering-readable plan contains `mv_switchgear`
- Ring In / Transformer Feeder / Ring Out are visible
- there is no top `mv-busbar` symbol in the engineering-readable plan
- DC side uses `dc_interface`
- rendered SVG has `DC Interface`
- rendered SVG does not show `DC BUSBAR` or `MV BUS`
- topology and render baselines remain deterministic

## V4 Follow-Up Status

The V4 semantic patch removes the historical `dc_busbar` node and edge names from the current engineering-readable SLD topology path.

The current topology now uses:

- `dc_interface`
- `pcs_to_dc_interface`
- `dc_interface_to_dc_block`

Compatibility drawing symbols for old busbar-style renderers may remain in the symbol library, but the current engineering-readable plan does not use them.
