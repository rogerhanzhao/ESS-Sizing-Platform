# SLD AC Field Contract V2

Scope: Phase 3 AC -> SLD field contract. This document governs the current SLD runtime chain only. It does not change AC sizing math or DC sizing math.

## Single Adapter Boundary

Formal SLD generation may normalize AC runtime data only through:

```python
calb_sizing_tool.adapters.ac_to_sld_adapter.normalize_ac_output_for_sld()
```

This adapter is the only allowed legacy-alias boundary. Builders, topology builders, specs, and renderers must consume the normalized object and must not reinterpret AC dict fields again.

## Authoritative Fields

| Authoritative field | Requirement | Meaning |
| --- | --- | --- |
| `num_blocks` | required | total AC block count |
| `pcs_per_block` | required | PCS count per AC block; uniform in current SLD V1 |
| `pcs_kw` | required | PCS rated power per PCS, kW |
| `block_size_mw` | required | AC block MW; must equal `pcs_per_block * pcs_kw / 1000` |
| `dc_allocation_plan` | required | authoritative DC block allocation plan |
| `transformer_mva` | required | transformer MVA per AC block |
| `dc_blocks_total_by_block` | derived mirror | totals derived from `dc_allocation_plan` |
| `dc_blocks_per_feeder_by_block` | derived mirror | feeder allocation matrix derived from `dc_allocation_plan` |
| `transformer_count` | optional mirror | must equal `num_blocks` if present |
| `pcs_count_total` | optional mirror | must equal sum of PCS count by block if present |
| `dc_blocks_total` | optional mirror | must equal sum of DC block totals if present |
| `dc_total_mwh` | optional mirror | site-level DC energy |
| `mv_voltage_kv` | optional mirror | AC-side MV voltage mirror |
| `lv_voltage_v` | optional mirror | PCS LV voltage mirror |

The adapter does not silently derive `block_size_mw`. It must be present and consistent.

## Allowed Legacy Aliases

Only the adapter may translate these legacy aliases:

| Authoritative field | Allowed legacy alias |
| --- | --- |
| `num_blocks` | `ac_blocks_total` |
| `pcs_per_block` | `pcs_count_per_ac_block` |
| `pcs_kw` | `pcs_power_kw`, `pcs_rating_kw_each` |
| `dc_allocation_plan` | `dc_block_allocation` |
| `transformer_mva` | `transformer_rating_mva`, `transformer_kva` |
| `pcs_count_total` | `total_pcs` |
| `mv_voltage_kv` | `mv_kv`, `grid_kv` |
| `lv_voltage_v` | `lv_v`, `inverter_lv_v` |

`dc_blocks_total_by_block` and `dc_blocks_per_feeder_by_block` are not primary allocation inputs. They are mirrors and cannot replace `dc_allocation_plan`.

## Strict Errors

The adapter raises `AcToSldAdapterError` when required AC fields are missing or inconsistent.

Examples that must fail:

- missing `block_size_mw`
- missing `dc_allocation_plan`
- only providing `dc_blocks_total_by_block`
- only providing `dc_blocks_per_feeder_by_block`
- mirror fields conflicting with `dc_allocation_plan`
- `dc_allocation_plan.dc_blocks_total` not matching sum of `feeder_allocations`

## Builder Contract

`calb_sizing_tool/services/sld_input_builder.py` must read AC topology through the normalized `SldAuthoritativeAcOutput` only.

The builder may select group-specific values from the normalized object, for example:

- `authoritative_ac.pcs_count_by_block[group_index - 1]`
- `authoritative_ac.pcs_rating_kw_list_by_block[group_index - 1]`
- `authoritative_ac.dc_blocks_per_feeder_by_block[group_index - 1]`
- `authoritative_ac.transformer_mva`

It must not independently try `pcs_count_total / total_pcs`, `pcs_kw / pcs_power_kw`, or `dc_allocation_plan / dc_block_allocation` again.

## Legacy Compatibility Paths

Legacy paths still exist:

- `calb_sizing_tool/sld/snapshot_single_unit.py`
- `calb_sizing_tool/sld/ac_block_group.py`
- `calb_diagrams/specs.py`

These paths must route through the same adapter/topology chain. They may remain compatibility wrappers, but they must not invent PCS count, transformer size, or DC feeder allocation.

## Phase 3 Acceptance

- AC -> SLD field map is explicit.
- Legacy aliases are handled only in `ac_to_sld_adapter.py`.
- `dc_allocation_plan` is the only primary DC allocation input.
- Mirror fields are consistency checks, not fallback topology sources.
- Strict mode fails on missing required fields.
