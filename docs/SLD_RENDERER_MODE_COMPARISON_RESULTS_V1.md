# SLD Renderer Mode Comparison Results V1

## Generated Evidence

Comparison script:

```text
python scripts/generate_sld_renderer_mode_comparison.py
```

Generated artifacts:

```text
outputs/sld_renderer_mode_comparison/case01_container_only_group1/legacy_server/sld.svg
outputs/sld_renderer_mode_comparison/case01_container_only_group1/legacy_server/sld.png
outputs/sld_renderer_mode_comparison/case01_container_only_group1/topology_v1/sld.svg
outputs/sld_renderer_mode_comparison/case01_container_only_group1/topology_v1/sld.png
outputs/sld_renderer_mode_comparison/case01_container_only_group1/comparison_summary.json
outputs/sld_renderer_mode_comparison/case01_container_only_group1/comparison_summary.md
```

Both rendered modes used the same input and topology:

```text
input_hash:    6226d637c2ec06128c9f9cafcf25228fe0db7e75ed7b3751c4a9d7454c24e125
topology_hash: 8f05d27e12d8593baeeac149cb31c2cc97e8bf17eb589f436b269f825099d28f
```

Therefore the visual difference is caused by renderer behavior, not by different sizing data.

## Renderer Comparison

| Mode | Role | Evidence |
|---|---|---|
| `legacy_server` | Server stable visual baseline from `8568af4` | Stable old template, 302 SVG elements, 61 text nodes |
| `topology_v1` | Current refactored topology renderer | New split layout/symbol renderer, 177 SVG elements, 66 text nodes |

## Legacy Server Baseline Findings

`legacy_server` is valuable because it preserves the drawing that is already stable on the running server.

It is not the final engineering-readable SLD.

Main problems:

1. RMU/MV switchgear is still an old symbolic construction around a top horizontal line.
2. DC side still uses `BUSBAR A (Ckt A)` / `BUSBAR B (Ckt B)`.
3. The DC block section visually connects through long shared-looking horizontal routing.
4. Equipment list is renderer-owned and contains legacy text such as `TBD`.
5. It is visually stable but not a clean single-line block SLD.

Keep this mode only as production fallback and visual regression reference.

## Topology V1 Findings

`topology_v1` improves several data and display issues:

1. Equipment list uses authoritative values more consistently.
2. It removes the legacy `BUSBAR A/B` DC concept.
3. It expresses `PCS -> DC Isolator/Fuse -> DC Block` more directly.
4. It can show feeder identities `F1/F2/F3/F4`.

But it is still not good enough as the final engineering SLD.

Main remaining problems:

1. RMU / MV switchgear is drawn as a large box with internal labels, but the underlying model still does not expose formal bay ports.
2. Ring In and Ring Out arrows visually enter the RMU box in a way that can overlap internal bay symbols and labels.
3. Transformer feeder is a drawn line, not a port-to-port connection from a real feeder bay to transformer HV terminal.
4. Transformer symbol does not have explicit HV and LV terminal anchors.
5. LV feeders are vertical lines with labels, but there is no explicit LV feeder equipment or breaker/isolator boundary.
6. DC interface is represented as a small inline mark plus text, but it is not yet a formal device symbol with defined input/output ports.
7. Battery section containment is weak: DC block boxes can visually sit too close to or cross the dashed section boundary.
8. Text placement is still coordinate-driven, not collision-aware.

Conclusion: `topology_v1` is a useful intermediate renderer, but it is still a fixed-slot diagram. It should not be promoted as the final engineering-readable SLD.

## Engineering V2 Requirements

`engineering_v2` must not be a patch on the current fixed-slot layout.

It needs a real engineering SLD graph:

### Node Types

Minimum required nodes:

```text
mv_ring_in_terminal
rmu_switchgear
rmu_ring_in_bay
rmu_transformer_feeder_bay
rmu_ring_out_bay
transformer
lv_busbar
lv_feeder
pcs
dc_interface
dc_block
```

### Ports

Every drawable node must declare ports:

```text
node_id
port_id
port_role
side
voltage_domain
```

Examples:

```text
rmu_ring_in_bay.line_port
rmu_ring_in_bay.bus_port
rmu_transformer_feeder_bay.bus_port
rmu_transformer_feeder_bay.load_port
transformer.hv_port
transformer.lv_port
lv_busbar.tap_F1
pcs_F1.ac_port
pcs_F1.dc_port
dc_interface_F1.pcs_port
dc_interface_F1.block_port
dc_block_F1.input_port
```

### Edges

Edges must be port-to-port, not node-center-to-node-center:

```text
source_node_id
source_port_id
target_node_id
target_port_id
edge_type
feeder_id
```

Minimum edge chain:

```text
Ring In terminal -> RMU Ring-In Bay
RMU Ring-In Bay -> RMU bus
RMU bus -> Transformer Feeder Bay
Transformer Feeder Bay -> Transformer HV
Transformer LV -> LV Busbar
LV Busbar tap F1 -> LV Feeder F1 -> PCS F1 AC port
PCS F1 DC port -> DC Interface F1 -> DC Block F1
RMU bus -> RMU Ring-Out Bay -> Ring Out terminal
```

### Layout Rules

The V2 layout engine must enforce:

1. No equipment box crosses a section boundary.
2. No text overlaps equipment or other text.
3. Lines attach only to declared ports.
4. RMU bay labels sit inside their bay and do not collide with external arrows.
5. Transformer HV/LV relationship is visually vertical and unambiguous.
6. LV feeders are evenly spaced and labelled at the feeder, not floating near the PCS.
7. DC side is one-line only for 1 PCS : 1 DC Block.
8. Dual DC channel mode, if ever enabled, must be explicit as `DC Ch-A` / `DC Ch-B`, not a floating busbar.

## Implementation Boundary For Next Step

Next implementation should add V2 structures without deleting current modes:

```text
legacy_server   remains production visual fallback
topology_v1     remains comparison renderer
engineering_v2  new port/bay/terminal renderer under feature selection
```

Suggested files:

```text
calb_sizing_tool/schemas/sld_engineering_v2.py
calb_sizing_tool/services/sld_engineering_v2_builder.py
calb_diagrams/sld_engineering_v2_layout.py
calb_diagrams/sld_engineering_v2_renderer.py
tests/unit/test_sld_engineering_v2_topology.py
tests/integration/test_sld_engineering_v2_render.py
```

Do not modify DC sizing logic. The V2 engine consumes existing authoritative SLD data and changes only the drawing model.

## Acceptance Gate

Before making `engineering_v2` the default, it must pass:

1. Same input hash as `topology_v1` for the same case.
2. Same PCS/DC allocation as authoritative topology.
3. Visual review confirms:
   - Ring In / Transformer Feeder / Ring Out are readable.
   - Transformer HV/LV relationship is clear.
   - LV feeders F1/F2/F3/F4 are clear.
   - PCS count and rating come from authoritative input.
   - DC side is `PCS -> DC interface -> DC Block`.
   - No floating DC busbar lines.
   - No section-boundary crossing.
   - No text overlap.
