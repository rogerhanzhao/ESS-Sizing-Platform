# Governed AC Block — ACBLK-10MW-8PCS-8DC-40FT-BILATERAL (Phase A)

Date: 2026-07-24
Branch: `claude/calb-10mw-8pcs-8dc-bilateral-yy64si`
Baseline: `ops/ubuntu-docker-coexist-20260311` @ `252bc75`
Governs: `docs/CLAUDE_HANDOFF_10MW_8PCS_8DC_2026-07-24.md`

This document records the Phase A implementation of the owner-confirmed
governed AC Block configuration. It is a fixed product/configuration identity,
**not** a generic unrestricted `1:8` ratio open to all PCS models.

## 1. What was implemented

A governed configuration contract binds the whole product/topology/layout
choice as one atomic identity and threads it through
AC Sizing -> SLD -> Layout -> Site Array -> Report by
`configuration_code` / `layout_variant` — never by an average
`dc_blocks_total / ac_blocks_total` ratio.

| Field | Value |
| --- | --- |
| `configuration_code` | `ACBLK-10MW-8PCS-8DC-40FT-BILATERAL` |
| `ac_power_mw` | `10.0` |
| `pcs_count` | `8` |
| `pcs_rating_kw` | `1250` |
| `dc_block_count` | `8` |
| `ac_container_type` | `40ft` |
| `layout_variant` | `central_40ft_bilateral_4plus4` |
| `dc_field_split` | `[4, 4]` |
| `dc_connection_policy` | `dedicated_dc_to_pcs` |
| `transformer_topology` | `three_winding` |
| `lv_winding_count` | `2` |
| `pcs_per_lv_winding` | `[4, 4]` |
| `status` | `concept_confirmed_partial` |

### New / changed code

- `calb_sizing_tool/schemas/governed_ac_block_config.py` (new) — the typed
  `GovernedACBlockConfiguration`, the Phase A instance, the Phase A gate, and
  `to_ac_sld_output()` which emits the authoritative AC->SLD payload for one
  governed unit (num_blocks=1, 8×1250 kW, 10 MW, three_winding / 2 LV, DC-i ->
  PCS-i).
- `calb_diagrams/ac_block_bilateral_layout.py` (new) — the
  `central_40ft_bilateral_4plus4` layout engine. Returns **per-equipment
  placements** (id, x/y, size, rotation, side, mirrored-pair, door/service
  orientation, feeder, aisle/envelope provenance, provisional flag) plus the
  equipment-only envelope and a concept SVG.
- `calb_diagrams/sld_engineering_v2_layout.py` /
  `calb_diagrams/sld_engineering_v2_renderer.py` (changed) — LV secondary
  busbar collision fix (see §4). SLD **render layer only**; no topology or
  sizing change.
- `calb_sizing_tool/reporting/report_context.py` (changed) — additive
  `configuration_code` / `layout_variant` carried directly from `ac_output`.

## 2. Confirmed physical layout

One central, vertically placed 40 ft AC Block / PCS-MV station; four DC Blocks
west, four east, left/right mirror images. Each side is a 2×2 `田` field of two
mirrored back-to-back DC pairs, the two pairs shoulder-to-shoulder. The removed
single-row eight-DC draft is **not** reintroduced.

Equipment-only envelope (rule-profile concept): **18.79 m × 13.02 m**, matching
handoff §2. The engine emits nine placements (DC-1..DC-8 + one vertical 40 ft
station), no DC overlaps, each DC block carrying its mirrored-pair id
(`W1/W2/E1/E2`), door orientation and provenance.

## 3. Electrical mapping

```
West DC-1..DC-4 -> PCS-1..PCS-4 -> LV-A
East DC-5..DC-8 -> PCS-5..PCS-8 -> LV-B
```

`dedicated_dc_to_pcs` is a **connection policy**: DC-i -> PCS-i over a single
physical output circuit. The DC Block **product** still exposes two protected
outputs (`dc_block_output_circuits = 2`); the product is not forced to
single-output. The two independent LV secondaries (4+4) come from
`transformer_topology = three_winding` / `lv_winding_count = 2`, which the
existing SLD topology builder already honours — no sizing formula change.

## 4. The "4 PCS / 2 DC -> [1,1,0,0]" defect — re-verified here

Re-checked in this repository (not carried over from any QR2CARD session). The
naive per-feeder split `evenly_distribute(2, 4)` still returns `[1, 1, 0, 0]`
(two dangling PCS). The physical connection model already repairs this: a DC
Block with fewer units than feeders spreads its output circuits across a
contiguous feeder span, so `build_dc_block_connection_plan(2, 4)` yields
DC1->F1-F2, DC2->F3-F4 and per-feeder `[1, 1, 1, 1]`. Locked by
`tests/unit/test_dangling_pcs_regression.py`.

While validating the 8-PCS/4+4 case a **new** render-layer collision surfaced:
the two independent LV secondary busbars overhang into each other when the
feeder count is wide (the fixed ±100 / ±90 pad exceeds the inter-feeder gap).
Fixed by clamping each secondary's inner edge to the boundary midpoint in both
the layout plan and the renderer. This is strictly SLD contract/topology/render
layer; no frozen sizing formula is touched. The 4-PCS shared-DC case is
unchanged.

## 5. Provisional / gated engineering values

None of these is inferred or hardcoded; each stays `None` until the owner
confirms it, and a caller must inject it through Engineering Settings
(`engineering_overrides`) for any drawing that needs it:

- transformer MVA nameplate (10 MW / 0.9 is **not** auto-promoted to 11.11 MVA),
  vector group, Uk%, LV voltage, cooling class;
- actual 40 ft station dimensions (nominal ISO `12.192 × 2.438 m` used, flagged);
- DC-field-to-station aisle (rule-profile 3.0 m, flagged);
- pair-to-pair gap (rule-profile 0.9 m, flagged).

The strict AC->SLD contract fails loudly when a required provisional value
(e.g. transformer MVA) is absent, rather than drawing an invented rating.

## 6. Scope boundary (Phase A only)

- Only homogeneous totals divisible by 8 are eligible
  (`dc_blocks_total % 8 == 0`). Mixed 8/4/2/1 tail configurations remain a
  deferred Phase B contract upgrade (SLD V1 requires uniform PCS count/rating);
  they are gated out, not partially enabled.
- Frozen sizing (DC Stage 1/2/3, guarantee loop, `K_MAX_FIXED`, SOH/RTE,
  scenario semantics, AC ratio set / PCS library / allocation thresholds) is
  unchanged. `git diff` over the frozen modules is empty.
- The verified L2 Site Array grouping / fire-road and report integration from
  `252bc75` are preserved (`calb_diagrams/site_array_concept.py` and
  `reporting/report_v2.py` behaviour untouched).

## 7. Open decisions for the owner (unchanged from handoff §10)

1. Confirm `DC-1 -> PCS-1` .. `DC-8 -> PCS-8` connection policy.
2. Confirm one three-winding transformer, two LV secondaries, 4 PCS each.
3. Confirm both DC-field-to-station aisles are 3.0 m.
4. Confirm first delivery supports only totals divisible by 8.
5. Confirm actual 40 ft station dimensions.
6. Confirm transformer nameplate, vector group, Uk%, LV voltage, cooling, and
   DC Block protected-output capability separately.

## 7a. Report-layer consistency fixes (Phase A finishing)

Three AC-sizing -> technical-report contradictions were found and fixed, all in
the reporting layer (no frozen sizing change):

1. **Silent transformer nameplate.** `report_context.py` used to derive
   `transformer_rating_kva = block_size_mw × 1000 / power_factor` when no MVA was
   present — i.e. it turned 10 MW / 0.9 into 11.11 MVA, which the strict SLD
   contract explicitly refuses. The fallback is now skipped for governed
   configurations (`governed_configuration = True`): an unconfirmed transformer
   MVA stays unresolved and the report shows TBD, matching the SLD.
2. **Arrangement figure (report §8).** It rendered the linear L1 engine from
   `round(dc_blocks_total / ac_blocks_total)`. For a governed unit it now routes
   by `layout_variant` to the bilateral 4+4 engine, so the figure matches the
   SLD topology and the confirmed physical layout, and prints the provisional
   spacing notes.
3. **Site figure (report §9).** The linear L2 site-array engine would draw
   single-row DC fields that contradict a governed bilateral unit and its SLD.
   It is now suppressed for the bilateral variant (whole-site composition of
   bilateral units is Master Layout / L3 scope). Ungoverned runs are unchanged.

Locked by `tests/unit/test_report_governed_consistency.py`.

## 7b. Engineering Settings integration (provisional values)

The one provisional value the settings form was missing — the transformer
nameplate MVA — is now an owner-confirmed field:

- `ui/sld_inputs.py`: added an optional "Transformer rating (MVA, owner-confirmed)"
  input (0 = unset). It is threaded into `SldInputOverride.transformer_rating_mva`.
- `services/sld_engineering_settings_service.py`: persists
  `transformer_rating_mva` at the top of `project_settings` **only when set**, so
  it is never inferred; the SLD builder already reads it from there.
- `services/governed_ac_block_service.py` (new): maps persisted engineering
  settings (`transformer_rating_mva`, vector group, Uk%, cooling) into the
  governed configuration's `engineering_overrides` and emits the authoritative
  AC->SLD output, reporting which provisional fields are still unresolved.
  Vector group / Uk% / cooling were already in the settings form; layout-only
  dims (40 ft size, aisle) remain unresolved until supplied.

Phase B (mixed 8/4/2/1 tails) remains deferred — design in
`docs/PHASE_B_MIXED_TAIL_DESIGN_2026-07-24.md`.

## 8. Tests

- `tests/unit/test_governed_ac_block_config.py` — identity, Phase A gate,
  dedicated mapping, provisional gating, AC->SLD payload.
- `tests/unit/test_ac_block_bilateral_layout.py` — envelope, 9 placements,
  bilateral split, mirrored pairs, vertical 40 ft station, no overlaps,
  provenance/provisional flags.
- `tests/unit/test_sld_bilateral_8pcs_8dc.py` — full SLD contract path: 1 block,
  8 PCS, 2 LV (4+4), 8 DC nodes 1:1, no dangling PCS, exact counts, layout +
  rendered-SVG collision validators.
- `tests/unit/test_dangling_pcs_regression.py` — the `[1,1,0,0]` defect and its
  contract-layer repair.
- `tests/unit/test_report_governed_consistency.py` — the three report-layer
  consistency fixes (§7a): no fabricated MVA, bilateral §8 routing, suppressed
  linear §9.
