# SLD Input Contract V1

This document defines the single canonical SLD input contract introduced in Phase 1.

## Canonical Object

Primary schema:

- `calb_sizing_tool/schemas/sld_render_input.py`
- `SldCanonicalInput`

Builder:

- `calb_sizing_tool/services/sld_input_builder.py`
- `build_sld_canonical_input()`

## Canonical Fields

Required core fields:

- `run_id`
- `project_name`
- `scenario_id`
- `group_index`
- `ac_blocks_total`
- `mv_voltage_kv`
- `lv_voltage_v_ll`
- `transformer_rating_mva`
- `transformer_vector_group`
- `transformer_uk_percent`
- `pcs_count`
- `pcs_rating_kw_list`
- `dc_block_energy_mwh`
- `dc_blocks_total_in_group`
- `dc_blocks_per_feeder`
- `dc_block_voltage_v`
- `equipment_ratings`
- `labels`
- `diagram_mode`
- `theme`
- `compact_mode`
- `draw_summary`

Supporting fields:

- `project_frequency_hz`
- `validation_mode`
- `override_mode`
- `source_trace`
- `draft_warnings`

## Source Priority

Priority is fixed and enforced:

1. `A`: explicit snapshot / canonical run data
2. `B`: `ac_output` authoritative allocation
3. `C`: project-level persisted settings
4. `D`: UI override only when `override_mode=True`
5. `E`: all other sources forbidden

Important rule:

- UI override does not replace authoritative A/B/C values.
- UI override only fills gaps that remain unresolved after A/B/C.

## Field Sources

| Field group | Primary source |
| --- | --- |
| `project_name`, `scenario_id`, `mv_voltage_kv` | DC run snapshot / case input |
| `group_index` | explicit UI selection |
| `ac_blocks_total`, `pcs_count`, `pcs_rating_kw_list`, `dc_blocks_per_feeder`, `lv_voltage_v_ll`, `transformer_rating_mva` | authoritative AC output |
| `dc_block_energy_mwh` | canonical DC run snapshot |
| `transformer_vector_group`, `transformer_uk_percent`, `labels`, `equipment_ratings`, `dc_block_voltage_v` | project settings first, then explicit UI override |
| `theme`, `compact_mode`, `draw_summary` | render options |

## Strict Mode

Formal rendering must use `validation_mode="strict"`.

Strict mode rules:

- missing critical fields raise `SldInputValidationError`
- no implicit `group_index=1`
- no implicit `pcs_count=4`
- no implicit even distribution of `dc_blocks_per_feeder`
- no implicit transformer sizing fallback inside the builder
- no implicit RMU / CT / cable / fuse defaults inside the builder

## Draft Mode

`validation_mode="draft"` is allowed only for internal preview.

Draft mode rules:

- still rejects missing authoritative engineering fields
- may fill legacy electrical labels/equipment fields from the centralized legacy draft preset
- records `draft_warnings`

Draft mode is not the formal render path.

## Fields That Must Not Fallback In Strict Mode

- `group_index`
- `ac_blocks_total`
- `pcs_count`
- `pcs_rating_kw_list`
- `dc_blocks_per_feeder`
- `transformer_rating_mva`
- `dc_block_energy_mwh`
- `dc_block_voltage_v`
- `transformer_vector_group`
- `transformer_uk_percent`
- `labels`
- `equipment_ratings`

## Allowed Override Scope

Allowed only when `override_mode=True`:

- `transformer_vector_group`
- `transformer_uk_percent`
- `dc_block_voltage_v`
- `dc_blocks_per_feeder` when authoritative AC allocation is absent
- `labels`
- `equipment_ratings`

Blocked in strict mode when authoritative value already exists:

- authoritative `transformer_rating_mva`
- authoritative `dc_blocks_per_feeder`
- any other A/B/C-resolved field with conflicting override

## Error Strategy

The builder collects all detected input issues and raises one `SldInputValidationError`.

Typical strict-mode errors:

- missing authoritative AC allocation
- missing project/persisted transformer metadata
- missing controlled DC block voltage source
- override payload provided while `override_mode=False`
