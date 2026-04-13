# SLD AC Field Contract V1

## Contract Rule

SLD formal generation is allowed to read AC runtime data only through:

- `calb_sizing_tool/adapters/ac_to_sld_adapter.py::normalize_ac_output_for_sld`

This adapter is the only place where legacy aliases may be translated. Downstream builder, topology, spec, and renderer code must not reinterpret AC fields again.

## Authoritative AC Fields

| AC field | Meaning | SLD usage |
| --- | --- | --- |
| `num_blocks` | total AC blocks | `SldCanonicalInput.ac_blocks_total` |
| `pcs_per_block` | PCS count per AC block | required and uniform in current V1 |
| `pcs_kw` | PCS rated power per unit | used to build `pcs_rating_kw_list` |
| `block_size_mw` | MW per AC block | must match `pcs_per_block * pcs_kw / 1000` |
| `dc_allocation_plan` | authoritative DC allocation plan | authoritative source |
| `dc_blocks_total_by_block` | total DC blocks per AC block | mirror of allocation plan |
| `dc_blocks_per_feeder_by_block` | DC block distribution by feeder | mirror of allocation plan |
| `transformer_mva` | transformer MVA per AC block | `SldCanonicalInput.transformer_rating_mva` |
| `transformer_count` | transformer count | optional consistency mirror |
| `pcs_count_total` | site PCS total | optional consistency mirror |
| `dc_blocks_total` | site DC block total | optional consistency mirror |
| `dc_total_mwh` | site DC energy total | optional consistency mirror |
| `mv_voltage_kv` | site MV nominal voltage | optional mirror |
| `lv_voltage_v` | PCS LV voltage | optional mirror |

## Allowed Legacy Aliases

| Authoritative field | Allowed alias |
| --- | --- |
| `num_blocks` | `ac_blocks_total` |
| `pcs_per_block` | `pcs_count_per_ac_block` |
| `pcs_kw` | `pcs_power_kw`, `pcs_rating_kw_each` |
| `dc_allocation_plan` | `dc_block_allocation` |
| `transformer_mva` | `transformer_rating_mva`, `transformer_kva` |
| `pcs_count_total` | `total_pcs` |
| `mv_voltage_kv` | `mv_kv`, `grid_kv` |
| `lv_voltage_v` | `lv_v`, `inverter_lv_v` |

## Required Data For Formal SLD

Required AC-side fields:

- `num_blocks`
- `pcs_per_block`
- `pcs_kw`
- `block_size_mw`
- `dc_allocation_plan`
- `transformer_mva`

Required non-AC engineering fields:

- `labels`
- `equipment_ratings`
- `transformer.vector_group`
- `transformer.uk_percent`
- `dc_block_voltage_v`

These non-AC fields must come from persisted engineering settings or an explicit draft override. They must not be guessed in the formal path.

## Forbidden Fallbacks

The following are forbidden in the formal path:

- default `group_index = 1` as an engineering substitute
- default `pcs_count = 4`
- auto-even distribution of DC blocks across feeders
- `transformer_mva = block_size_mw / 0.9`
- default RMU / CT / cable / fuse engineering preset

## Strict vs Draft

In `validation_mode="strict"`:

- missing required inputs raise validation errors
- formal output is blocked

In `validation_mode="draft"`:

- explicit override is allowed
- result must be treated as draft only
- override does not redefine the formal contract
