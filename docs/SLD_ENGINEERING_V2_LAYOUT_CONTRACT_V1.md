# SLD Engineering V2 Layout Contract V1

## Scope

This step adds a layout planner for `engineering_v2`.

It consumes only:

```text
SldEngineeringV2Graph
```

It outputs a pure layout plan:

```text
sections
node boxes
port anchors
connectors
```

It does not render SVG, does not connect to UI, and does not replace `legacy_server` or `topology_v1`.

## New File

```text
calb_diagrams/sld_engineering_v2_layout.py
```

## Layout Objects

### Sections

```text
equipment_list
ac_block
battery_bank
```

Sections are fixed layout regions for the future renderer. Node boxes must stay inside their assigned section.

### Node Boxes

Each V2 graph node receives a layout box:

```text
node_id
node_type
section_id
x
y
width
height
text_lines
feeder_index
dc_block_index
```

Important placement rules:

1. RMU bays are separate boxes inside the AC section.
2. Transformer is aligned below the transformer feeder bay.
3. LV busbar sits below transformer LV terminal.
4. LV feeders, PCS, DC interface, and DC blocks align by feeder column.
5. DC interface and DC blocks stay inside the battery section.

### Port Anchors

Each declared graph port receives one coordinate:

```text
node_id
port_id
x
y
side
voltage_domain
```

This is the critical difference from `topology_v1`: line routing now starts and ends at declared ports.

### Connectors

Each V2 graph edge becomes one connector:

```text
edge_id
edge_type
source_node_id
source_port_id
target_node_id
target_port_id
points
voltage_domain
```

The first connector point must equal the source port anchor. The last connector point must equal the target port anchor.

## Current Routing Rules

The first planner uses deterministic orthogonal routing:

1. Same X or same Y: direct line.
2. Different X and Y: vertical-horizontal-vertical route through a midpoint.

This is still not the final visual renderer. It is enough to prevent node-center drawing and make all future SVG lines port-owned.

## Validation Covered By Tests

Tests verify:

1. Layout plan is deterministic.
2. All node boxes stay inside their section.
3. Every connector starts and ends on declared port anchors.
4. RMU bay order is Ring In -> Transformer Feeder -> Ring Out.
5. Transformer HV port aligns with transformer feeder bay load port.
6. Each feeder column is vertically aligned:

```text
LV feeder -> PCS -> DC interface -> DC block
```

7. Connectors carry explicit source and target port IDs.

## Still Not Implemented

```text
SVG renderer
collision-aware text placement
visual regression for V2 SVG
UI activation
artifact persistence for V2 output
```

## Next Step

Add a V2 SVG renderer that draws only from `SldV2LayoutPlan`.

The renderer must not:

```text
read SldTopology directly
infer port positions
infer feeder allocation
change equipment ratings
change DC sizing results
```

The renderer's only job is visual output from the already-resolved layout plan.
