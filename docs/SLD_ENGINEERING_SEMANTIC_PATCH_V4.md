# SLD Engineering Semantic Patch V4

Scope: SLD-only patch after the Phase 4 engineering-readable renderer work. This patch tightens the SLD topology semantics so the diagram is not only visually improved, but also backed by engineering-readable node and edge contracts.

This patch does not change Layout page logic, login, RBAC, or DC sizing mathematics.

## Problem Corrected

The Phase 4 drawing no longer showed floating DC+ / DC- busbars, but the internal topology still carried historical `dc_busbar` nodes and `pcs_to_dc_busbar` / `dc_busbar_to_dc_block` edges. That made the renderer translate a busbar abstraction into a DC interface symbol.

The MV side also still carried a generic `mv_bus` node and `mv_link` / `rmu_to_transformer` edges. That did not explicitly encode the ring-in, transformer-feeder, and ring-out relationship that a readable RMU / MV switchgear block SLD needs.

## New Topology Semantics

MV node types now express switchgear ports and feeder intent:

- `mv_ring_in`
- `mv_switchgear`
- `mv_transformer_feeder`
- `mv_ring_out`

MV edge types now express the one-line path:

- `ring_in_to_switchgear`
- `switchgear_to_transformer_feeder`
- `transformer_feeder_to_transformer`
- `switchgear_to_ring_out`

DC side now uses interface semantics directly:

- node type: `dc_interface`
- equipment type: `dc_interface`
- edge types:
  - `pcs_to_dc_interface`
  - `dc_interface_to_dc_block`

The current engineering-readable 1 PCS : 1 DC Block path is:

```text
LV Busbar -> PCS-n -> DC Isolator/Fuse -> DC Block-n
```

## Renderer Behavior

The MV switchgear symbol now draws a continuous main/ring path inside the RMU / MV Switchgear block, with separate cubicles for Ring In, Transformer Feeder, and Ring Out.

The DC interface symbol is now drawn inline on the single vertical feeder from PCS to DC Block. It is no longer a floating box below the PCS.

The renderer still does not decide PCS count, DC allocation, transformer rating, or equipment ratings. It consumes the already-built `SldTopology`.

## Strict Mode

Strict SLD mode rejects `dc_fuse.fuse_spec = TBD`.

Draft/session mode may still be used for incomplete engineering inputs, but official/strict SLD artifacts must not show a fake completed Equipment List with an unresolved DC interface.

## Regression Coverage

Tests now cover:

- topology no longer emits `mv_bus`
- topology no longer emits `dc_busbar`
- DC edges use `pcs_to_dc_interface` and `dc_interface_to_dc_block`
- strict mode rejects unresolved DC fuse/interface text
- render baseline includes `DC Isolator/Fuse`
- render baseline text no longer includes `TBD`
