# SLD Engineering V2 Topology Contract V1

## Scope

This contract defines the first non-rendering step for `engineering_v2`.

It adds a port/bay/terminal graph model but does not render SVG. The existing renderer modes remain unchanged:

```text
legacy_server
topology_v1
engineering_v2 reserved
```

No Layout, login, RBAC, or DC sizing mathematics are changed.

## Why V2 Needs A New Graph

`topology_v1` has useful high-level nodes:

```text
mv_ring_in
mv_switchgear
mv_transformer_feeder
mv_ring_out
transformer
lv_busbar
pcs
dc_interface
dc_block
```

But its edges are still node-to-node. A renderer then has to infer where lines should attach. That is why the current picture still suffers from ambiguous RMU bay geometry, floating labels, and weak connection semantics.

`engineering_v2` fixes the model first by requiring explicit ports.

## New Files

```text
calb_sizing_tool/schemas/sld_engineering_v2.py
calb_sizing_tool/services/sld_engineering_v2_builder.py
tests/unit/test_sld_engineering_v2_builder.py
```

## Node Model

Minimum V2 node types:

```text
mv_ring_in_terminal
mv_ring_out_terminal
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

The important change is that RMU is not a single ambiguous box. It is split into:

```text
rmu_switchgear
rmu_ring_in_bay
rmu_transformer_feeder_bay
rmu_ring_out_bay
```

## Port Model

Every drawable V2 node has ports:

```text
port_id
display_name
port_role
side
voltage_domain
feeder_index
dc_block_index
```

Required examples:

```text
rmu_ring_in_bay.line_port
rmu_ring_in_bay.bus_port
rmu_transformer_feeder_bay.bus_port
rmu_transformer_feeder_bay.load_port
rmu_ring_out_bay.bus_port
rmu_ring_out_bay.line_port
transformer.hv_port
transformer.lv_port
lv_busbar.transformer_port
lv_busbar.feeder_F01_port
lv_feeder.busbar_port
lv_feeder.pcs_port
pcs.ac_port
pcs.dc_port
dc_interface.pcs_port
dc_interface.block_port
dc_block.input_port
```

## Edge Model

Edges are now port-to-port:

```text
source_node_id
source_port_id
target_node_id
target_port_id
edge_type
feeder_index
dc_block_index
```

Minimum chain:

```text
Ring In terminal -> RMU Ring-In Bay
RMU Ring-In Bay -> RMU bus
RMU bus -> Transformer Feeder Bay
Transformer Feeder Bay -> Transformer HV
Transformer LV -> LV Busbar
LV Busbar -> LV Feeder F1/F2/F3/F4
LV Feeder -> PCS AC Port
PCS DC Port -> DC Interface
DC Interface -> DC Block
RMU bus -> RMU Ring-Out Bay -> Ring Out terminal
```

## Validation Rules

The V2 graph validates:

1. Node IDs are unique.
2. Port IDs are unique within each node.
3. Every edge references existing source and target nodes.
4. Every edge references existing source and target ports.
5. Edge endpoint voltage domains must match.
6. Required node types must exist.
7. Required ports must exist for each node type.
8. LV busbar must expose one feeder tap port per feeder.
9. PCS, LV feeder, DC interface, and DC block counts must match the authoritative topology summary.

## Builder Boundary

The new builder consumes existing authoritative topology:

```text
SldTopology -> SldEngineeringV2Graph
```

It does not:

```text
read Streamlit session
read AC/DC loose dicts
infer PCS count
infer DC block count
render SVG
change artifact persistence
```

## Current Status

Implemented:

```text
V2 schema
V2 builder from SldTopology
graph validation
unit tests for ports, counts, voltage domains, and invalid references
```

Not implemented yet:

```text
V2 layout engine
V2 SVG renderer
V2 visual regression
V2 UI activation
```

## Next Step

Build a V2 layout planner that consumes `SldEngineeringV2Graph` only.

The planner should place:

```text
MV terminals and RMU bays
transformer HV/LV terminals
LV busbar and feeder taps
PCS nodes
DC interfaces
DC blocks
```

The layout planner must use declared ports as line anchors. It must not route lines from node centers.
