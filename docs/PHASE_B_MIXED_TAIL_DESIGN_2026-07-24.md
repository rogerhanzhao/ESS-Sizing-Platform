# Phase B — Mixed-Tail Governed Configurations

Date: 2026-07-24
Status: **Phase B v1 implemented** (owner-approved). The DC-block-level
decomposition and the governed tail catalogue are live; the single-drawing
heterogeneous SLD (one drawing covering unlike blocks) remains future work —
each governed group is rendered on its own, which the SLD V1 contract already
supports.
Baseline: `ops/ubuntu-docker-coexist-20260311`.

## Implemented (v1)

- Governed tail catalogue (`schemas/governed_ac_block_config.py`), all reusing
  the 1250 kW PCS unit and the dedicated DC-to-PCS policy:
  - `ACBLK-10MW-8PCS-8DC-40FT-BILATERAL` (three-winding, 2 LV, bilateral)
  - `ACBLK-5MW-4PCS-4DC-40FT-LINEAR` (two-winding, 1 LV)
  - `ACBLK-2P5MW-2PCS-2DC-20FT-LINEAR` (two-winding, 1 LV)
  - `ACBLK-1P25MW-1PCS-1DC-20FT-LINEAR` (two-winding, 1 LV)
- `decompose_governed_site(dc_blocks_total)` — greedy 8/4/2/1, exact (a 1-DC unit
  exists so any positive total is composable), never a ceil/average split.
- `services.governed_ac_block_service.build_governed_site_plan()` — returns the
  heterogeneous site as a list of homogeneous `GovernedSiteGroup`s. Each group's
  AC output is a valid, uniform `SldAuthoritativeAcOutput`, so it is individually
  SLD-renderable without changing the SLD V1 uniform-block contract.
- Tail groups bind to real catalogue products (`eligible_products_for` no longer
  excludes a product that does not declare its topology): the 5 MW group ->
  NR PCS-9567MV-5000 + Kehua BCS5000K; the 2.5 MW group -> Kehua BCS2500K; the
  1.25 MW group has no catalogue product. `build_governed_site_plan(with_products)`
  annotates each group with its eligible products.
- `calb_diagrams/governed_site_composition.py` renders a concept composition
  diagram (one band per governed group, counts, metrics, eligible products).
- Wired into the app: the AC Sizing governed panel shows a "Site composition
  (Phase B decomposition)" table, and report §9 renders the governed composition
  figure + group table for a governed run (replacing the linear L2 site array).
- Multi-group run orchestration
  (`services.governed_ac_block_service.build_governed_site_run()`): turns the
  decomposition into a runnable multi-block site — one valid, individually
  SLD-renderable `SldAuthoritativeAcOutput` per governed group (a group of N
  identical blocks is one uniform output; N distinct governed configurations ->
  N distinct SLDs). With `bind_products=True` each group auto-binds the first
  eligible catalogue product (datasheet MVA / vector group / cooling); otherwise
  it builds from Engineering Settings. A provisional value is never fabricated —
  each group reports its unresolved fields and the run unions them, so a group
  without a product or owner MVA stays gated (not silently rendered). The AC
  Sizing composition table now shows each group's bound product and transformer
  MVA readiness from this run.
- **UI reachability + report closure (fixes the "92 DC exported generic" gap).**
  The AC Sizing governed panel previously only offered itself when
  `dc_blocks_total % 8 == 0`, so a real non-multiple-of-8 project (e.g. 92 DC)
  could never reach the governed path and silently fell back to the generic
  average-ratio grouping (23 × 4-PCS blocks + a fabricated `5.0 MW / 0.9 = 5.56`
  MVA nameplate). Now:
  - `services.governed_ac_block_service.build_governed_primary_ac_output()` is the
    single governed entry for ANY DC total. A multiple of 8 yields one uniform
    bilateral output (Phase A, unchanged); any remainder is decomposed (Phase B)
    and the **uniform head group** is returned as the SLD-renderable block while
    the **true site rollup** (`governed_is_mixed`, `governed_site_ac_blocks_total`
    / `_pcs_total` / `_total_ac_mw`, and the per-group `governed_groups`) rides on
    the output. The head honours the owner's product choice; tails auto-bind.
  - `ui/ac_view.py` offers the governed panel for any total and runs through this
    entry.
  - `reporting/report_context.py` reads the site rollup so the report states the
    true governed site (12 AC Blocks / 115 MW / 92 PCS for 92 DC), not the head.
  - `reporting/report_v2.py` §1/§6 are governed-aware: the executive-summary
    configuration line states the governed decomposition, the generic average
    DC-to-AC split line is suppressed, and the §6 "Transformer Sizing Basis" no
    longer prints `MW ÷ PF` for a governed run (it shows the owner-confirmed
    product nameplate or an explicit TBD) — removing the last place a governed
    report could show a fabricated `10 MW / 0.9` figure.
  - The DRAFT/OVERRIDE watermark + `Dyn11` + `Uk 7.0%` on an exported SLD come
    from the SLD page's Override toggle (legacy preset); the strict governed path
    (Override off) draws `Dy11y11` / standard-by-class Uk / dual LV bus, no
    watermark.
- Tests: `tests/unit/test_governed_phase_b_decomposition.py`,
  `test_governed_ac_block_product_binding.py`, `test_governed_site_composition.py`,
  `test_governed_site_run_orchestration.py`, `test_governed_primary_ac_output.py`,
  `test_report_governed_mixed_consistency.py`.

Example: `188 -> 23 x ACBLK-10MW (bilateral) + 1 x ACBLK-5MW (linear tail)`.

The remainder of this document is the original design rationale.

---

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
