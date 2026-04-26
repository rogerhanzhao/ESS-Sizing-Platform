# SLD Engineering V2 Renderer Contract V1

## Scope

This step adds the first SVG renderer for `engineering_v2`.

The renderer consumes only:

```text
SldV2LayoutPlan
```

It does not read:

```text
SldTopology
SldEngineeringV2Graph
AC output dictionaries
DC stage snapshots
Streamlit session state
```

This keeps rendering separate from sizing, authoritative data resolution, topology building, and layout planning.

## New Files

```text
calb_diagrams/sld_engineering_v2_renderer.py
scripts/generate_sld_engineering_v2_preview.py
tests/unit/test_sld_engineering_v2_renderer.py
tests/integration/test_sld_engineering_v2_preview_script.py
```

## Render Flow

Current V2 preview flow:

```text
SldTopology
-> SldEngineeringV2Graph
-> SldV2LayoutPlan
-> render_sld_engineering_v2_svg(...)
-> SVG / PNG preview
```

Only the last step is implemented in the renderer.

## Visual Rules Implemented

The renderer now draws the professional electrical template:

1. Equipment List section from resolved layout equipment rows.
2. RMU / MV Switchgear ring-in / transformer-feeder / ring-out expression.
3. Ring In / Ring Out terminal arrows.
4. Transformer feeder switching/protection symbols.
5. Delta/wye transformer symbol.
6. LV busbar and one vertical feeder per PCS.
7. PCS converter symbols.
8. DC Isolator/Fuse inline interface.
9. BESS/DC Block battery symbols.
10. Left-side engineering notes panel.

Port anchors are used for routing. They are hidden by default in the SVG output and can be enabled only for debugging with:

```text
show_port_anchors=True
```

The renderer does not draw:

```text
DC BUSBAR
BUSBAR A
BUSBAR B
Circuit A/B
```

## Preview Command

```text
python scripts/generate_sld_engineering_v2_preview.py
```

Default output:

```text
outputs/sld_engineering_v2_preview/case01_container_only_group1/sld_engineering_v2.svg
outputs/sld_engineering_v2_preview/case01_container_only_group1/sld_engineering_v2.png
outputs/sld_engineering_v2_preview/case01_container_only_group1/metadata.json
```

Stress-test preview for multiple DC blocks under selected feeders:

```text
python scripts/generate_sld_engineering_v2_preview.py --dc-blocks-per-feeder 2,1,2,1 --output-dir outputs/sld_engineering_v2_preview/multi_dc
```

## Current Status

Implemented:

```text
V2 port-level topology
V2 layout planner
V2 SVG/PNG preview renderer
renderer-only tests
preview generation script
```

Still not implemented:

```text
visual acceptance as production default
collision-aware text routing beyond the current acceptance gate
```

Implemented after the renderer step:

```text
manual plugin mode activation
artifact registry persistence through existing SLD plugin artifacts
UI manual selection through SLD Renderer Mode
layout acceptance gate
explicit multi-DC-block feeder placement for up to 4 DC blocks per feeder
preview metadata records PNG dimensions and layout issue count
plugin metadata records V2 PNG dimensions for cropped-render detection
professional electrical reference template
```

## Acceptance Boundary

`engineering_v2` must remain non-production until human visual review confirms:

1. RMU Ring In / Transformer Feeder / Ring Out are readable.
2. Transformer HV/LV relation is clear.
3. LV feeders F1/F2/F3/F4 are clear.
4. PCS count and ratings match authoritative input.
5. DC side is single-line `PCS -> DC Interface -> DC Block`.
6. No floating DC busbar lines are present.
7. No section-boundary crossings are present.
8. No severe text overlap is present.

Until then, `legacy_server` remains the production visual fallback and `topology_v1` remains the comparison renderer.
