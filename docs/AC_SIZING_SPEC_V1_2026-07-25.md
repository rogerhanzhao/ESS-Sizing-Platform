# AC Sizing Specification V1

Date: 2026-07-25
Status: **Draft for owner confirmation.** This document normalizes AC Sizing so
that SLD, Typical AC Block Arrangement, whole-site Layout and the exported report
are all derived from one coherent contract. It only *describes* the frozen DC
sizing (`SIZING_LOGIC_CANON_V1`) and does not change it.

Baseline: `ops/ubuntu-docker-coexist-20260311`.

---

## 0. Why this spec

Real projects are **duration systems** — 2 h / 3 h / 4 h, and a likely future
8 h. The DC Block library already encodes this (below). AC Sizing must be pinned
to the DC nameplate **power** at the chosen duration, otherwise the PCS,
transformer, SLD, arrangement and site layout drift apart and the report shows
inconsistent numbers. This spec fixes the single chain of definitions.

---

## 1. System duration is a DC-side nameplate fact (authoritative source)

Source of truth: `data/…_v13_*.xlsx` sheet **`dc_block_nameplate_profile_data`**,
keyed by `system_duration_h`. A DC Block's nameplate **power** is a function of
its duration profile — the energy is roughly fixed, the power scales inversely
with duration:

| profile | duration | nameplate energy | **nameplate power** | usable DoD |
| --- | --- | --- | --- | --- |
| `5MWh_4H_STD` | 4 h | 5000 kWh | **1250 kW** | 0.90 |
| `6p26MWh_2H_588` | 2 h | 6000 kWh | **3000 kW** | 0.85 |
| `6p26MWh_4H_588` | 4 h | 6262 kWh | **1500 kW** | 0.90 |
| `7MWh_2H_661_CONCEPT` | 2 h | 6899 kWh | **3449 kW** | 0.85 |
| `7MWh_4H_661_CONCEPT` | 4 h | 7039 kWh | **1760 kW** | 0.90 |

Two independent duration signals must agree:

- **DC-side**: the selected DC Block template + its `system_duration_h` profile
  fix the block's `nameplate_power_kw`.
- **Project-side**: `discharge_duration_h = poi_energy_req_mwh / poi_power_req_mw`
  (e.g. 400 MWh / 100 MW = 4 h). Already used in
  `ac_sizing_service.generate_ac_sizing_options` /
  `calculate_optimal_pcs_rating`.

**Rule S1 (duration coherence).** AC Sizing must size the PCS to the DC Block
nameplate power at the project duration, not to a hardcoded 4 h assumption. A
2 h system built from a 5 MWh/4 h block (1250 kW) is invalid — a 2 h system needs
the 2 h profile (≈3000 kW) or the block count/PCS rating changes accordingly.

---

## 2. Power calculation points and their relation to POI (the efficiency chain)

Authoritative source: `stage1_service.run_stage1`. One-way DC→POI efficiency:

```
eff_chain = eff_dc_cables · eff_pcs · eff_mvt · eff_ac_cables_sw_rmu · eff_hvt_others
          = 0.995 · 0.985 · 0.995 · 0.992 · 1.000   (defaults)  ≈ 0.967
```

Each factor is a **calculation point** between the DC Block and the grid:

```
[1] DC Block terminal        P_dc_block (nameplate power @ duration)
      │  × eff_dc_cables (DC cabling)
[2] PCS DC input
      │  × eff_pcs (DC→AC conversion)
[3] PCS AC LV output  ──────  AC Block LV busbar (690 V)
      │  × eff_mvt (AC Block step-up transformer, MV)
[4] AC Block MV terminal ───  33 kV
      │  × eff_ac_cables_sw_rmu (MV cables + switchgear + RMU)
[5] MV collection bus / RMU ring
      │  × eff_hvt_others (site HV transformer + others)
[6] POI  ← point of interconnection (contractual power/energy meter)
```

**Power relationship (authoritative):**

```
dc_power_required_mw = poi_power_req_mw / eff_chain
```
i.e. POI power is the *deliverable*; the DC side must be larger by 1/eff_chain.

**Energy relationship (authoritative):**

```
dc_energy_capacity_required_mwh
    = poi_energy_req_mwh / [ (1 − sc_loss_frac) · DoD · √(DC_RTE) · eff_chain ]
```
where `√(DC_RTE)` is the one-way DC efficiency and `sc_loss` is the
storage-&-conveyance (calendar) loss. **POI is always the reference plane**;
every AC-side quantity is referred back to POI through `eff_chain`.

---

## 3. AC Sizing normalized contract

**Inputs (from DC sizing, read-only):**
- `dc_blocks_total`, DC Block template (`Dc_Block_Code`, energy, form, container),
- DC Block `nameplate_power_kw` @ project `system_duration_h`,
- `poi_power_req_mw`, `poi_energy_req_mwh`, `eff_chain` (Stage 1).

**AC Block definition (normalized):** an AC Block = a group of DC Blocks + PCS +
one step-up transformer + one MV connection (RMU). It is described by:
- `dc_per_block` (DC Blocks under this AC Block) — this IS the "ratio" axis:
  1:1 / 1:2 / 1:4 / **1:8** = 1 / 2 / 4 / 8 DC per block,
- `pcs_count`, `pcs_kw`,
- `transformer_mva`, `vector_group`, `lv_winding_count`,
- `layout_variant` (arrangement engine), `container_type`.

**Rule A1 (PCS power).** `pcs_count · pcs_kw ≥ dc_per_block · dc_block_nameplate_power_kw(duration)`.
For the dedicated DC→PCS policy (1 PCS per DC), `pcs_kw ≥ dc_block_nameplate_power_kw(duration)`.

**Rule A2 (transformer).** Governed AC Blocks carry a real product nameplate
(`transformer_mva` from the catalogue) — never `AC-block-MW ÷ PF`. Only the
legacy abstract path may show the `MW ÷ PF` estimate, clearly labelled.

**Rule A3 (POI power closure).** `Σ AC-block MW · eff(AC→POI) ≈ poi_power_req_mw`
within the allowed oversize margin (`evaluate_ac_sizing_feasibility`).

### 3.1 Two AC Sizing methods (already implemented, one primary)

- **Governed product (primary).** The site is composed of real productized AC
  Block families (below). `dc_per_block ∈ {8,4,2,1}` = 1:8/1:4/1:2/1:1. Real
  transformer, real layout, real BOM. Non-multiple decompositions use Phase B.
- **Legacy abstract (secondary, folded).** The frozen
  `ac_sizing_service` ratio set `{1:1,1:2,1:4}` + `MW ÷ PF` transformer, no
  product. Kept for a no-product quick estimate; never the report's basis.

---

## 4. Governed AC Block families vs duration (THE open decision)

Today's governed families are implicitly **4 h** (1250 kW PCS, 5 MWh/4 h block):

| family | dc_per_block | ratio | pcs | pcs_kw | AC MW | duration |
| --- | --- | --- | --- | --- | --- | --- |
| `ACBLK-10MW-8PCS-8DC-40FT-BILATERAL` | 8 | 1:8 | 8 | 1250 | 10.0 | **4 h** |
| `ACBLK-5MW-4PCS-4DC-40FT-LINEAR` | 4 | 1:4 | 4 | 1250 | 5.0 | 4 h |
| `ACBLK-2P5MW-2PCS-2DC-20FT-LINEAR` | 2 | 1:2 | 2 | 1250 | 2.5 | 4 h |
| `ACBLK-1P25MW-1PCS-1DC-20FT-LINEAR` | 1 | 1:1 | 1 | 1250 | 1.25 | 4 h |

For 2 h / 3 h / 8 h the DC nameplate power changes, so the PCS rating (and thus
AC-block MW and transformer) must change. Options (see the question I will ask):

- **(A) Duration-aware family matrix** — declare a `system_duration_h` +
  `dc_block_nameplate_power_kw` on each governed family, and add 2 h/3 h/8 h
  siblings (PCS rating derived from the DC nameplate power). Cleanest, fully
  productized.
- **(B) Duration parameter on one family** — keep `dc_per_block` fixed, set
  `pcs_kw = dc_block_nameplate_power_kw(duration)` at run time. Flexible, less
  catalogue-exact.
- **(C) Keep 4 h only now** — pin the current families as 4 h, gate other
  durations with a clear "family not yet defined" message; define the matrix
  later with real products.

Whichever is chosen, **Rule S1 / A1 must hold** so PCS, transformer, SLD, layout
and report stay coherent.

---

## 5. Downstream coherence (one identity, four consumers)

Everything routes by the governed AC Block identity + duration:

- **SLD (one main drawing).** The governed head block: Δ primary, LV winding(s)
  per `lv_winding_count`, PCS = `pcs_count × pcs_kw`, DC = `dc_per_block`,
  transformer = real MVA/vector. Strict path (no Override) = no watermark.
- **Typical AC Block Arrangement.** Routed by `layout_variant` (bilateral head /
  linear tails) at the real container footprint.
- **Whole-site Layout (concept).** Every governed block placed at its real
  product footprint, grouped by family, with a site-envelope estimate.
- **Report.** Numbers come only from the governed run — never re-derived.

---

## 6. Report chapter structure (normalized)

```
Cover · provenance (project / case / run id / dictionary versions)
1. Executive Summary        POI P/E, guarantee, governed configuration line
2. Project Inputs & Assumptions   duration, DoD, efficiencies, PF
3. Stage 1 – DC Energy Sizing     efficiency chain (§2), dc_energy/power required
   3.1 Efficiency Chain (DC→POI)  the calculation-point table
4. Stage 2 – DC Block Configuration   DC Block template, count, nameplate @BOL
5. Stage 3 – Lifetime Degradation & POI Deliverable  SOH/RTE, guarantee year
6. Stage 4 – AC Block Sizing       method, dc_per_block, PCS, transformer basis
7. Single Line Diagram             one governed head SLD
8. Typical AC Block Arrangement    per layout_variant, real footprint
9. Concept Site Layout & Equipment Schedule (Provisional)
      whole-site layout + per-group BOM (PCS/DC/transformer real or TBD/product)
Appendix. QC checks · provisional/TBD register · standards basis
```

**Rule R1.** Every provisional value is shown as an explicit `TBD` with its
owner-confirmation source, never silently filled. **Rule R2.** No fabricated
`MW ÷ PF` nameplate on a governed report.

---

## 7. Frozen-boundary guarantees

- Stage 1/2/3, guarantee loop, `K_MAX_FIXED`, SOH/RTE, `SUPPORTED_AC_DC_RATIOS`,
  PCS standard library and allocation — **frozen**. This spec adds the duration
  coherence rules and the governed-family contract as a parallel, explicit layer;
  it does not edit the frozen modules.
