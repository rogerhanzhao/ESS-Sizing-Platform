# SLD Builder Unification V1

## Authoritative Builder Chain

Phase 2 selects **Scheme A** as the only authoritative chain:

`run / snapshot -> SldCanonicalInput -> SldTopology -> compatibility spec adapter -> renderer`

Reason:

- `SldCanonicalInput` is already the frozen contract from Phase 1.
- `SldTopology` is the correct place to hold engineering relationships such as MV/RMU/transformer/LV/PCS/DC branches.
- The current renderer still consumes `SldGroupSpec`, so a temporary compatibility adapter is the safest way to preserve output while removing duplicate builder logic.

## Final Authority Boundaries

- Authoritative input contract: `calb_sizing_tool/schemas/sld_render_input.py::SldCanonicalInput`
- Authoritative relationship builder: `calb_sizing_tool/services/sld_topology_builder.py::build_sld_topology`
- Temporary compatibility adapter for renderer: `calb_diagrams/specs.py::build_sld_group_spec_from_topology`

Renderer is **not** authoritative for topology anymore.

## Legacy Builder Handling

The following functions are downgraded to compatibility wrappers only:

- `calb_diagrams/specs.py::build_sld_group_spec`
  - Old dict-based entry retained for smoke tests and older call sites.
  - Now routes through `build_legacy_sld_topology(...)` and then `build_sld_group_spec_from_topology(...)`.

- `calb_sizing_tool/sld/ac_block_group.py::build_ac_block_group_spec`
  - No longer performs independent feeder / PCS / DC block inference.
  - Now reads values from `SldTopology.summary`.

- `calb_sizing_tool/sld/snapshot_single_unit.py::build_single_unit_snapshot`
  - Still outputs the legacy raw snapshot shape.
  - Now depends on the downgraded compatibility wrapper instead of acting as an independent builder chain.

## Topology Model

`calb_sizing_tool/schemas/sld_topology.py` defines:

- `SldTopology`
- `SldTopologySummary`
- `SldNode`
- `SldEdge`
- `SldEquipment`
- `SldLabel`

Current node types:

- `mv_bus`
- `rmu`
- `transformer`
- `lv_busbar`
- `pcs`
- `dc_busbar`
- `dc_block`

Current edge types:

- `mv_link`
- `rmu_to_transformer`
- `transformer_to_lv_busbar`
- `lv_busbar_to_pcs`
- `pcs_to_dc_busbar`
- `dc_busbar_to_dc_block`

## What Moved Out of Renderer

The following engineering relationships are now built before rendering:

- feeder count
- PCS count
- PCS per feeder relationship
- DC blocks per feeder allocation
- MV -> RMU -> transformer -> LV busbar chain
- LV busbar -> PCS -> DC busbar -> DC block chain
- semantic labels for switchgear / RMU / PCS / DC block quantities

## What Renderer Should Consume Next

Short term:

- renderer still consumes `SldGroupSpec`
- `SldGroupSpec` must be produced only from `SldTopology`

Next phase target:

- renderer should consume topology-derived render data only
- no engineering inference should remain in renderer

## Validation / Verification

Phase 2 verification includes:

- `tests/unit/test_sld_topology_builder.py`
- `tests/unit/test_sld_builder_unification.py`
- existing SLD smoke tests
- existing SLD plugin integration tests
