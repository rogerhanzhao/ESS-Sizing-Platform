# SLD Engineering Readable Template V1

Scope: Phase 4 SLD renderer/template fix. This document describes the engineering-readable block SLD template now used by the deterministic renderer. It does not change AC sizing, DC sizing, Layout page logic, login, or RBAC.

## Template Intent

The SLD is a one-line engineering block diagram, not a visual poster. The diagram must show electrical topology first:

```text
Ring In -> RMU / MV Switchgear -> Transformer Feeder -> Transformer -> LV Busbar -> PCS feeders -> DC Interface -> DC Block
          \---------------------------------------------- Ring Out
```

The renderer consumes `SldTopology`; it does not decide PCS count, transformer rating, or DC allocation.

## MV Area

The top MV area is no longer drawn as:

```text
top MV busbar
  |
 hanging RMU box
```

It is now rendered as an RMU / MV switchgear block with three explicit cubicles:

- Ring In
- Transformer Feeder
- Ring Out

External labels remain attached to the ring positions:

- `to_switchgear`
- `to_other_rmu`

The transformer feeder drops directly from the center cubicle to the transformer.

## Transformer Area

The transformer is shown as a separate symbol below the MV switchgear feeder.

The displayed transformer label includes:

- HV/LV voltage
- MVA rating
- vector group
- Uk%
- cooling, when present in authoritative equipment ratings

## LV Area

The LV busbar is shown below the transformer and is labeled with LV voltage.

Each PCS feeder is drawn as a separate vertical feeder from the LV busbar and is labeled:

- F1
- F2
- F3
- F4
- or the actual feeder index from the authoritative topology

PCS count and PCS rating are taken from the authoritative topology produced by the SLD builder.

## DC Area

The engineering-readable template does not draw floating local DC+ / DC- busbars.

For the current 1 PCS : 1 DC Block case, the diagram renders:

```text
PCS-n -> DC Interface F-n -> DC Block-n
```

For feeders with more than one DC Block, the same DC interface feeds the blocks assigned by the authoritative allocation. The renderer does not redistribute blocks.

V4 cleanup note: the internal topology no longer uses the historical `dc_busbar` node or edge names for this engineering-readable SLD path. DC-side topology now uses `dc_interface`, `pcs_to_dc_interface`, and `dc_interface_to_dc_block`.

## Equipment List

The equipment list is generated from the same topology and equipment ratings used by the drawing. It now includes:

- MV System voltage
- MV Switchgear / RMU ratings
- Transformer HV/LV voltage, MVA, vector group, Uk%, cooling
- LV Busbar voltage/current/short-circuit rating
- PCS count/rating/LV voltage
- DC Interface fuse/interface note
- Battery Storage Bank block count and energy
- DC Block Allocation by feeder

The renderer does not map MV voltage into a different RMU equipment-class voltage.

## Out Of Scope

This phase does not:

- change AC sizing math
- change DC sizing math
- change Layout page behavior
- change login or RBAC
- introduce a separate dual DC channel data model

If future authoritative input distinguishes DC Channel A / Channel B, the renderer should add explicit channel symbols. It must not reintroduce floating DC+ / DC- busbar lines as a substitute.
