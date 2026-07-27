# AC Sizing Specification V1

Date: 2026-07-25
Status: **Draft for owner confirmation.** This document normalizes AC Sizing so
that SLD, Typical AC Block Arrangement, whole-site Layout and the exported report
are all derived from one coherent contract. It only *describes* the frozen DC
sizing (`SIZING_LOGIC_CANON_V1`) and does not change it.

Baseline: `ops/ubuntu-docker-coexist-20260311`.

> **Owner override, 2026-07-27.** For current implementation and all future
> changes, read `AC_SIZING_UNIFIED_FLOW_V2_2026-07-27.md` first. The former
> governed-product preset and its fixed 8/4/2/1 tail decomposition are retained
> only as historical/persisted-run compatibility; they are not the new-run AC
> sizing path. The supported generic grouping set includes 1:8, and product
> matching is optional enrichment after grouping, PCS and topology selection.

---

## ⚠ CORRECTION (2026-07-25) — the "system duration family" concept is WITHDRAWN

Sections that treat **system duration (2/3/4/8 h)** as a stored parameter, a DC
Block nameplate-power-by-duration profile, a governed "family per duration", or a
duration gate (Rule S1, §1's duration table, §4's family matrix, the PCS-overload
"adjustment band" tied to a duration nameplate power) **do not reflect this
project's real logic and have been removed from the code.** They fabricated a
parameter that the live sizing does not use.

What is real (and unchanged): the DC-side rate parameter is **C-rate**
(`effective_c_rate`, `chosen_soh_c_rate`, `chosen_rte_c_rate`) — computed in the
frozen Stage 3 (it selects the SOH / RTE profiles) and already shown in the
report. AC Sizing continues the existing logic: auto-recommend AC:DC ratio + PCS,
then the existing power/energy validation (`evaluate_ac_sizing_feasibility`) →
pass/hold. The standard product AC Block is an optional preset, not gated by any
duration. Keep the still-valid parts below (POI plane / efficiency chain / POI is
the reference plane); ignore anything that introduces a duration family.

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

### 2.1 Where is the POI power requirement — MV or HV? (authoritative)

The POI power/energy requirement is stated **at the POI plane [6]**, and the POI
plane's voltage is set by the project:

- Default: `poi_nominal_voltage_kv = 33.0` (case.py) and `eff_hvt_others = 1.0`
  (stage1) → **POI is at the MV collection bus (33 kV)**. There is no site main
  step-up; the last modelled loss to POI is `eff_ac_cables_sw_rmu` (MV cables +
  switchgear + RMU). This is the current governed default.
- If the project connects at HV (e.g. a site main transformer 33 kV → 110/220 kV),
  set `eff_hvt_others < 1.0` and `poi_nominal_voltage_kv` to the HV value → **POI
  moves to the HV side** and the HV transformer loss is included.

So the POI plane is explicit and configurable; the two governed cases are
"POI = MV bus" (default) and "POI = HV side" (site main TR present). AC Sizing
must refer POI power to the AC-block MV terminal through only the losses that lie
between them:

```
eff(AC-block MV terminal → POI) = eff_ac_cables_sw_rmu · eff_hvt_others
```

**Segmented-percentage rule (owner-confirmed).** The efficiency chain is a set of
named **segment percentages**; a segment at **100 % means it is absent / lossless**.
The POI plane sits at the last segment carrying a loss:

- `eff_hvt_others = 100 %` → no HV step-up → **POI at MV (33 kV)**, the default.
- `eff_hvt_others < 100 %` → a site HV transformer/line is present → **POI at HV**.

Reserved segments (e.g. an extra MV switch / breaker stage, or a DC-side segment)
default to **100 % (lossless placeholder)** until a project supplies the real
percentage, so the chain stays explicit and auditable without inventing losses.

---

## 3. AC Sizing normalized contract

### 3.0 Two calculation lines that must reconcile

AC Sizing is driven by **two lines** that meet at the AC Block; a correct scheme
is where they agree within the adjustment band (§3.2).

**Line 1 — Power, top-down from POI (product-library driven).**
The contractual quantity is the **POI power** at the POI plane (§2.1). Refer it
back to the AC-block MV terminal, then divide by a real AC Block product's rated
power to get the block count — independent of the DC count:

```
ac_aggregate_mw   = poi_power_req_mw / (eff_ac_cables_sw_rmu · eff_hvt_others)
ac_block_count(P) = ceil_within_band( ac_aggregate_mw / AcBlockRatedPowerMw(product) )
```
`AcBlockRatedPowerMw` and `PcsUnitRatedPowerKw` come from the AC Block / PCS
catalogue (`AC_Block_Data_Dictionary`). The `ceil` is **soft** — see §3.2.

**Line 2 — DC-side power, bottom-up (energy/duration driven).**
DC sizing (frozen) grosses the POI requirement up through the whole chain
(including the AC Block's own PCS + MV transformer efficiency) and picks DC Blocks
by energy:

```
dc_power_required_mw = poi_power_req_mw / eff_chain      # deducts AC Block η too
dc_energy_required   → Stage 1/2  →  dc_blocks_total (of a template @ duration)
```

**Reconciliation (the crux).** Line 1 says how many AC Blocks the *power* needs
from the product library; Line 2 says how many DC Blocks the *energy* needs. The
AC Sizing job is to group `dc_blocks_total` under AC Blocks so that:
- the DC:AC grouping ratio is **reasonable** (`DcAcRatio`, §3.2), and
- the resulting AC aggregate power covers `poi_power_req_mw` within the band.
Single-config first (§3.3); mixed only when a single config cannot reconcile
cleanly.

### 3.1 AC Block definition (normalized)

An AC Block = a group of DC Blocks + PCS + one step-up transformer + one MV
connection (RMU), described by:
- `dc_per_block` (DC Blocks under this AC Block) — this IS the "ratio" axis:
  1:1 / 1:2 / 1:4 / **1:8** = 1 / 2 / 4 / 8 DC per block,
- `pcs_count`, `pcs_kw` (**continuous** rated power, `PcsUnitRatedPowerKw`),
- `transformer_mva` (ambient-dependent, see §3.2), `vector_group`, `lv_winding_count`,
- `layout_variant` (arrangement engine), `container_type`.

### 3.2 The adjustment band — power matching is NOT a rigid equality

Three real effects give the scheme its "adjustment room"; sizing must use bands,
not hard nameplate equalities:

1. **PCS overload.** `PcsUnitRatedPowerKw` is the **continuous** rating; a PCS has
   short-term overload capability, so the DC block power may momentarily exceed
   the PCS continuous nameplate. Model this with an explicit
   `pcs_overload_factor` (≥ 1.0, e.g. 1.1) rather than treating the nameplate as a
   hard ceiling.
2. **DC:AC power ratio / over-provisioning** (`DcAcRatio` in the AC Block dict —
   "DC 名义功率与 AC 额定功率的比例或能量超配系数"). The DC nominal power vs the AC
   rated power sits in a reasonable band (typ. ~1.0–1.5); it is a design choice,
   not a fixed 1:1.
3. **Ambient-derated transformer.** A product's transformer nameplate depends on
   ambient (e.g. Sineng EH-10000 `transformer_kva_by_ambient` = 11000 @30 °C /
   10000 @45 °C / 8750 @50 °C, per `RatedPowerComment`). The MVA used must state
   its ambient basis.

**Rule A1 (PCS power, revised).** Instead of a rigid nameplate floor, require
`dc_per_pcs · dc_block_nameplate_power_kw(duration) ≤ pcs_kw · pcs_overload_factor`.
For the dedicated 1 PCS ↔ 1 DC policy this is
`dc_block_nameplate_power_kw(duration) ≤ pcs_kw · pcs_overload_factor`.

**Rule A2 (transformer).** Governed AC Blocks carry a real product nameplate
(`transformer_mva` at a stated ambient basis) — never `AC-block-MW ÷ PF`. Only the
legacy abstract path may show the `MW ÷ PF` estimate, clearly labelled.

**Rule A3 (POI power closure, banded).** The chosen configuration must satisfy
`poi_power_req_mw ≤ Σ AC-block deliverable power at POI ≤ poi_power_req_mw · (1 + oversize_max)`,
where the AC-block deliverable at POI accounts for `eff(AC→POI)` and the allowed
PCS overload / oversize margin (`evaluate_ac_sizing_feasibility`). Landing on a
clean product configuration inside this band is the goal — not an exact equality.

### 3.3 Single-config first, mixed only when needed (owner-confirmed)

**Rule A4 (single-config priority).** Prefer a **single uniform AC Block
configuration** for the whole site (Phase A — every AC Block identical). Use the
**mixed** decomposition (Phase B — 8/4/2/1 governed families) only when a single
config cannot reconcile the DC count / POI power cleanly. Mixed gives large or
awkward projects more precision and flexibility, but it is the exception, not the
default: a site that divides cleanly must stay single-config.

### 3.4 Superseded two-method design (historical record only)

The former governed-product-primary design and its `{8,4,2,1}` tail
decomposition are superseded for new runs. There is one sizing trunk: select a
generic ratio from `{1:1,1:2,1:4,1:8}`, select PCS architecture and actual
transformer topology, validate, then optionally bind a matching product. See
`AC_SIZING_UNIFIED_FLOW_V2_2026-07-27.md`; do not implement this older section
as a second UI flow.

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
