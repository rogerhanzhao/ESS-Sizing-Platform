# Phase B — Mixed-Tail Governed Configurations (Design, deferred)

Date: 2026-07-24
Status: **design only — not implemented**. Requires explicit owner approval
before any code lands (per the handoff and SIZING_LOGIC_CANON_V1 governance).
Baseline: `ops/ubuntu-docker-coexist-20260311`.

## 1. Problem

Phase A ships the governed `ACBLK-10MW-8PCS-8DC-40FT-BILATERAL` under a strict
gate: it is only usable when `dc_blocks_total % 8 == 0` (every generated AC
Block has exactly eight DC Blocks). A real project can need a total that is not
divisible by eight, e.g. 188 DC Blocks:

```
23 × 8 DC  → 23 governed bilateral AC Blocks (184 DC)
remaining 4 DC → a smaller governed AC Block configuration (tail)
```

Phase B is the controlled way to place that non-8 remainder into one or more
*smaller governed* AC Block configurations — never by silently loosening the
Phase A gate or by falling back to the generic `ceil` + `evenly_distribute`
grouping (which would produce `[5, 4]`-type splits that represent no real
product).

## 2. Why it is not a small extension

The current SLD V1 authoritative schema (`schemas/sld_authoritative_input.py`)
requires **uniform** PCS count and rating across all AC Blocks:

- `pcs_count_by_block must be uniform and equal pcs_per_block in SLD V1`
- `pcs_rating_kw_list_by_block must match pcs_kw in SLD V1`
- `transformer_count must equal num_blocks in SLD V1`

A mixed 8 + 4 (or 8/4/2/1) site has AC Blocks with different PCS counts and
transformer ratings. That is a **heterogeneous `ACBlockInstance[]`** model, which
the V1 contract deliberately forbids. So Phase B is a contract upgrade, not a
parameter tweak.

## 3. Proposed model (for future approval)

### 3.1 A governed tail catalogue

Introduce sibling governed configurations for the allowed tails, each a fixed
product identity exactly like Phase A (no free ratios):

| configuration_code | dc_block_count | pcs_count | layout_variant |
| --- | --- | --- | --- |
| `ACBLK-10MW-8PCS-8DC-40FT-BILATERAL` | 8 | 8 | `central_40ft_bilateral_4plus4` |
| `ACBLK-…-4PCS-4DC-…` (tail) | 4 | 4 | existing 4-DC arrangement |
| `ACBLK-…-2PCS-2DC-…` (tail) | 2 | 2 | existing 2-DC arrangement |
| `ACBLK-…-1PCS-1DC-…` (tail) | 1 | 1 | single-DC arrangement |

Each tail keeps its own provisional/gated engineering values and its own
layout engine (routed by `layout_variant`), reusing the Phase A pattern in
`schemas/governed_ac_block_config.py`.

### 3.2 Deterministic decomposition

```
decompose(dc_blocks_total) -> list[GovernedACBlockConfiguration]
    while remaining >= 8:  emit 8-DC governed unit
    then greedily emit the largest approved tail (4, then 2, then 1)
```

This is explicit and auditable — one governed unit per emitted block, no
`ceil`/average grouping. `188 → 23×8 + 1×4`.

### 3.3 Heterogeneous SLD contract (`ACBlockInstance[]`)

A new `SldMultiBlockInput` (or a versioned `SldAuthoritativeAcOutput` v2) that
carries a **list of per-AC-Block descriptors**, each with its own
`pcs_count`, `pcs_kw`, `transformer_mva`, `lv_winding_count`, and
`dc_allocation_plan`. The uniformity validators move from "equal across the
site" to "internally consistent per block". The single-block builder
(`build_sld_topology`) already works per group; the change is at the
site-level aggregation and the authoritative-input schema, plus the report /
site-array aggregation which must sum heterogeneous blocks.

## 4. Frozen-boundary guarantees (unchanged in Phase B)

- DC Stage 1/2/3, guarantee loop, `K_MAX_FIXED`, SOH/RTE, scenario semantics —
  frozen.
- AC ratio set (`1:1`/`1:2`/`1:4`), PCS standard library, allocation thresholds
  — frozen. Governed configurations are a parallel, explicit product contract,
  not new AC ratios.
- The DC product's protected-output capability stays independent of the
  connection policy.

## 5. Delivery gate

Phase B lands only after:
1. owner confirms the exact tail product catalogue (which of 4/2/1 exist and
   their electrical data);
2. the heterogeneous `ACBlockInstance[]` schema is designed with its own
   regression tests;
3. the report / site-array aggregation is updated to consume heterogeneous
   blocks (no average reconstruction).

Until then the Phase A gate (`% 8 == 0`) stays in force and non-divisible totals
are rejected with a clear message rather than silently mixed.
