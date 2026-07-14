# AC Block Model Selection V1

Date: 2026-07-14

Scope: AC Sizing page behavior before governed AC Block product records are available.

## Boundary

`Product & Database -> AC Blocks` currently has no governed product records. AC Sizing therefore uses a simplified dropdown model derived from the existing PCS recommendation library. This is a runnable business workflow, not approved product master data.

Do not populate production AC Block templates from assumptions. Formal AC Block records still require confirmation of PCS configuration, LV feeder/winding basis, transformer MVA, voltage, impedance, manufacturer, and product revision.

## Logic

1. DC Sizing determines `dc_blocks_total` and total DC energy.
2. AC Sizing Step 1 selects the grouping ratio:
   - `1:1` means 1 AC Block per 1 DC Block.
   - `1:2` means 1 AC Block per 2 DC Blocks.
   - `1:4` means 1 AC Block per 4 DC Blocks.
3. The grouping ratio determines AC Block quantity.
4. AC Sizing Step 2 selects one simplified AC Block model.
5. The selected model defines:
   - `pcs_per_block`
   - `pcs_kw`
   - `block_size_mw = pcs_per_block * pcs_kw / 1000`
   - `ac_block_container_type`
6. Total AC power is calculated as:

```text
total_ac_mw = ac_block_count * block_size_mw
```

## Current Output Contract

The AC output keeps the existing downstream contract fields:

- `num_blocks`
- `pcs_per_block`
- `pcs_kw`
- `pcs_power_kw`
- `pcs_rating_kw_each`
- `block_size_mw`
- `total_ac_mw`
- `dc_allocation_plan`
- `transformer_mva`

It also adds simplified model trace fields:

- `ac_block_quantity_basis = dc_block_grouping_ratio`
- `ac_block_model_code`
- `ac_block_model_name`
- `ac_block_model_source`
- `ac_block_container_type`
- `ac_block_template_id`

## Example

For a restored 400 MW / 800 MWh run with 188 DC Blocks:

- Grouping `1:2` gives 94 AC Blocks.
- Model `ACBLK-2X2500KW-20FT` gives 2 PCS per AC Block at 2500 kW each.
- One AC Block is 5.00 MW.
- Total AC power is `94 * 5.00 = 470.00 MW`.

This relationship is the source of truth for SLD, layout, and report consumers until governed AC Block product records replace the simplified dropdown source.
