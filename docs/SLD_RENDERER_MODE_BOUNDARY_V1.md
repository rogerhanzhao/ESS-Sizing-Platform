# SLD Renderer Mode Boundary V1

## Purpose

This patch isolates SLD rendering modes so the server-stable renderer and the refactored topology renderer can be compared without overwriting each other.

This is a boundary patch only. It does not change Layout, login, RBAC, or DC sizing mathematics.

## Modes

### `legacy_server`

Production comparison baseline.

Implementation:

```text
calb_diagrams/sld_server_baseline_renderer.py
```

This module is copied from commit `8568af4`, the version reported as stable on the server. It preserves the old monolithic drawing logic for controlled fallback and visual comparison.

This mode still carries the old drawing limitations, including the old local DC busbar/circuit style. It is not the target engineering-readable V2 renderer.

### `topology_v1`

Current refactored renderer.

Implementation:

```text
SldTopology -> build_sld_layout_plan(...) -> symbol_library -> render_sld_svg(...)
```

This remains the current repository refactor path. It is useful for regression comparison, but it must not silently replace the server baseline until the visual engineering review is passed.

### `engineering_v2`

Manual preview mode.

This mode uses the port/bay/terminal-based engineering V2 graph, layout planner, and SVG renderer. It is available for explicit comparison, but it is not production-approved and must not become the default until visual review is complete.

## Runtime Behavior

`SldRenderOptions` now carries:

```text
renderer_mode
```

Default API compatibility value:

```text
topology_v1
```

SLD page production comparison default:

```text
legacy_server
```

The plugin records the selected mode in artifact metadata:

```text
renderer_mode
renderer_lineage
server_baseline_commit
```

## Why This Boundary Exists

The project currently has two different concerns mixed together:

1. Data governance and authoritative runtime input.
2. Actual engineering drawing quality.

The previous refactor improved the first concern but changed the second concern too aggressively. This boundary lets the project keep authoritative SLD data work while preventing the unfinished topology renderer from replacing the stable server visual output by accident.

## Files Added / Modified

Added:

```text
calb_diagrams/sld_server_baseline_renderer.py
calb_sizing_tool/services/sld_renderer_mode_service.py
tests/unit/test_sld_renderer_mode_service.py
tests/integration/test_sld_renderer_mode_boundary.py
docs/SLD_RENDERER_MODE_BOUNDARY_V1.md
```

Modified:

```text
calb_sizing_tool/schemas/diagram_inputs.py
calb_sizing_tool/schemas/__init__.py
calb_sizing_tool/plugins/sld_engineering_plugin.py
calb_sizing_tool/ui/single_line_diagram_view.py
```

## Constraints Preserved

```text
Layout unchanged
Login/RBAC unchanged
DC sizing mathematics unchanged
SLD authoritative input path preserved
Current topology_v1 renderer preserved for comparison
```

## Next Step

Generate the same case through both `legacy_server` and `topology_v1`, save both SVGs, and use the differences to define the port/bay model for `engineering_v2`.
