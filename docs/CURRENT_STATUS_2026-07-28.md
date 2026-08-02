# Current Status — 2026-07-28 (stage record)

Milestone tip: `20676fe` on `ops/ubuntu-docker-coexist-20260311`
(HEAD == origin; working tree clean).

This document is a **stage record** for the AC-Sizing → Report → SLD work that
landed on 2026-07-28. It supplements — does not replace — the standing detail
doc `docs/CURRENT_STATUS_2026-07-12.md`, whose §2.7–§2.12 hold the per-change
rationale and the module map. Read that doc's module map before scanning code.

---

## 1. Where the project is

- **Branch / sync:** all 2026-07-28 work is on `ops/ubuntu-docker-coexist-20260311`,
  committed directly (no feature branch), pushed to origin, HEAD == origin.
- **Tests:** **517 passed, 2 skipped** (full suite, ~63 s). Guards green: frozen
  canon SHA-256, report brand/leak, concept-SVG sanitization, UI PyArrow
  serialization. Baseline `case01` regenerated (geometry unchanged; only the two
  new watermark CSS classes + DC-block size differ).
- **Frozen boundary intact:** no file in `SIZING_LOGIC_CANON_V1` was modified;
  all new logic lives in non-frozen services / UI / reporting / diagrams.

## 2. What shipped

### 2a. Merged earlier this session via PR #38 (`2262a25`)
- **Mixed AC Block station** — opt-in per-AC-Block manual adjustment on the
  uniform AC-sizing trunk (head + tail models); one code path, report §6.1
  head/tail schedule. `services/ac_mixed_station.py`.
- **Report §9 legible site layout** — one representative project group at page
  scale + whole-site composition in the caption/table.
- **Report §8/§9 mixed-aware** — draw the Head AC Block (not the fractional
  average) for a mixed station; §9 whole-site power/energy from real totals.
- **Mixed → SLD head-fleet projection** — a mixed station renders its Head
  AC-Block fleet (uniform sub-station) instead of crashing the uniform-only
  SLD adapter.
- **Codex round 1 formality** — mixed disables single-product binding;
  representative SLD is non-official (CONCEPT watermark); mixed marked
  concept/draft in UI + report §6.1.

### 2b. Landed directly on ops (2026-07-28) — four commits
- `1ff771e` — **Legacy renderer** removed from the public SLD dropdown
  (`PUBLIC_SLD_RENDERER_MODES`; legacy reachable only via `?sld_dev=1`);
  **vector-group formality gate** (unconfirmed/mismatched → non-formal).
- `1f840f4` — **Unconfirmed-vector-group placeholder** in the engineering_v2
  renderer (explicit "NOT A DRAWING" block instead of TBD winding circles);
  **product-data standard defaults** (`ac_block_transformer_defaults`, derive
  from datasheet vector group, else conservative single-LV default, all
  `*_basis`-tagged); **two-/three-winding PNG export acceptance** tests.
- `796036f` — **SLD sheet redesign** (electrical logic unchanged): AC Block
  boundary box (RMU+TX+PCS); single-PCS LV winding draws no redundant busbar;
  DC Block enlarged to container scale (116×84) and balanced against the
  boundary. **Assumed-default vector-group readiness gate** (Codex round 2):
  `standard_default_pending_confirmation` can never back a formal SLD.
- `20676fe` — **Report rule:** every concept figure (SLD §7 / arrangement §8 /
  site §9) is stamped `DRAFT / OVERRIDE - NOT FOR CONSTRUCTION` unconditionally,
  in the existing watermark style. Plus a Workspace-Setup button-wrap fix.

### 2d. Multi-DC per PCS + watermark hardening (2026-08-02)

**Firm rule (owner decision):** when several dedicated DC Blocks sit under ONE
PCS, the split belongs to the **PCS's own internal DC busbar**. Each DC Block is
fed by its **own protected vertical branch** (its own isolator/fuse `F-nnA` /
`F-nnB`) straight down into its own container. There is **no external combiner /
"DC branch box" enclosure** and **no V-shaped (diagonal) conductor**. The earlier
external `DC BRANCH BOX` rendering was an unapproved intermediate attempt and has
been removed (`_pcs_internal_dc_bus` replaces `_dc_branch_box`).

- Multi-DC feeders get a wider feeder pitch and renderer-safe container spacing
  (`_local_dc_block_counts` / `_local_dc_half_span`), so the containers never
  overlap; the compact single-DC field (incl. the approved 8-PCS sheet) is
  unchanged.
- The PCS-internal busbar is drawn INSIDE the PCS outline, so the split is never
  mistaken for external switchgear.
### 2f. Configuration-matrix sweep of the SLD chain (2026-08-02)

Swept `(DC Blocks x PCS per block x LV windings)` end-to-end (canonical input ->
topology -> graph -> layout -> rendered SVG) and validated every result.

- **PCS symbols could overlap (fixed).** The PCS *layout box* is 120 px wide, but
  the clustered feeder pitch defaulted to 120 (zero gap) and the `max_field_width`
  cap then scaled it **below** the box width — e.g. 8 PCS on 4 shared DC Blocks
  scaled the intra-group pitch to 111 px, overlapping adjacent PCS by ~9 px.
  The pitch is now floored at `_MIN_FEEDER_PITCH` (box width + 20), and the cap's
  down-scaling is clamped by the **smallest gap actually used** so it can never
  push symbols into overlap — the content-adaptive canvas grows instead.
- Known boundary (unchanged, raises explicitly): the layout supports at most
  **4 dedicated DC Blocks per feeder**; beyond that it refuses rather than draw
  an unreadable sheet.
- Governed production path verified consistent for 4/7/8/16/92/100 DC Blocks:
  `sum(group DC) == site DC`, the power identity holds, and every group satisfies
  the feeder-capacity rule. Report §9 schedule sums back to `ac_blocks_total`
  (92 -> 11x8 + 1x4).

### 2e. DC busbar model CORRECTED (owner, 2026-08-02)

The earlier model was **wrong** and is corrected here. Record permanently:

1. **Different PCS must NEVER share a DC busbar** — not outside the DC Block and
   **not inside it either**. The old note "a shared DC Block's common bus lives
   INSIDE the block" was an incorrect justification.
2. **"The common busbar is inside the PCS"** describes the **PCS side**: the DC
   BUSBAR under ONE PCS has **several ports**, so **one PCS can take several DC
   Blocks**. It never described the DC Block.
3. **A DC Block is built with TWO INDEPENDENT DC circuits** ("segregated").
4. Those two circuits **may feed two different PCS**, but **only PCS inside the
   SAME AC Block**.

Enforcement (contract layer — `schemas/ac_electrical_topology.py`; the sizing
service itself is FROZEN canon and was not touched):
- `DEFAULT_DC_BLOCK_INTERNAL_MODE = "segregated"` is what every producer emits.
- `DcBlockConnection` **rejects** `internal_dc_busbar_mode="common"` whenever the
  block feeds more than one PCS; `common` stays admissible for a single-PCS block.
- `build_dc_block_connection_plan` guards that every emitted feeder index lies in
  the AC Block's own `1..pcs_count` range (same-AC-Block rule).
- Capacity rule `⌈PCS / 2⌉` is **unchanged** — a block's two circuits can still
  serve two PCS, so DC-Block-count < PCS-count stays valid.

- **AC Sizing -> SLD chain audit (2026-08-02):** `feeder_allocations` is a
  **per-feeder connection count**, so a DC Block shared across N feeders appears
  N times. `sld_formal_readiness_service` summed it as a DC-Block count whenever
  a plan entry carried no explicit `dc_blocks_total` — 2 shared blocks over 4
  feeders read as **4**, raising a false `dc_ac_block_total_mismatch` /
  `sld_group_allocation_mismatch` and wrongly blocking a formal SLD. The count is
  now derived from the distinct `dc_block_index` values in `dc_block_connections`,
  with the feeder sum only as a last resort (`_entry_dc_block_total`). Verified
  against 1:1, shared, mixed and multi-DC groupings.
- **DC-side drawing conventions (2026-08-02, second pass):**
  - A conductor tapping the PCS-internal DC busbar is a T-connection and carries a
    solid junction dot (IEC 60617) — a crossing without a dot means *no* connection.
  - `_dc_isolator_fuse` internals are **proportional** to the declared height. They
    were absolute offsets, so the device overran its own envelope and the fuse
    overlapped the DC container by 8 px.
  - The DC protection height is explicit (`dc_device_height`) and the battery row
    sits low enough (`lv_bus_y + 256`) that the device's full envelope clears the
    container top while the lower label still stays above the title block.
  - The **AC Block boundary closes in the clear gap below the PCS and above the DC
    protection** — it previously bisected the DC isolator/fuse symbols. The DC
    isolator, fuse and containers belong to the DC side, outside the AC Block.
- **Watermark**: `_load_stamp_font` previously fell back to
  `ImageFont.load_default()` with no size — a ~11 px bitmap font — so on hosts
  without DejaVu the mandatory NOT-FOR-CONSTRUCTION stamp silently shrank to
  near-invisible (~527 red px vs ~6500). It now tries explicit font paths and asks
  Pillow's embedded fallback for the size it needs (>= 4800 red px with no system
  fonts), so the regression threshold stays high (2000) instead of being lowered
  to accommodate a degraded stamp. Pixel access is Pillow 11/12 agnostic.

### 2c. Landed directly on ops (2026-07-29)
- **Compact adaptive SLD sheet** — feeders were stretched evenly across a fixed
  2000 px canvas (sprawling PCS/DC rows, huge side margins). Now:
  (1) feeders that share a DC Block cluster into a tight pair, groups are
  separated, and the field is placed just right of the equipment list, centred
  under the transformer (`_feeder_groups` + `_grouped_feeder_positions`);
  (2) the **canvas width is content-adaptive** — the sheet is sized to the drawing
  (e.g. ~1260 px for a 4-PCS shared station, ~1820 px for 8-PCS 1:1) instead of a
  fixed 2000, so side whitespace is minimal; (3) the MV geometry is now **derived
  from the RMU layout box** in `sld_professional_sheet` (no more hardcoded centres
  that drift from the layout); (4) per-feeder boxes (DC interface) size to the
  actual feeder gap so they never overlap at tight spacing.
- **Shared DC container shows one battery group per PCS circuit** — a DC Block
  shared by N PCS is drawn compactly (spanning just its feeders) with N
  independent battery glyphs inside, one under each output terminal, separated by
  thin dividers (`_shared_bess_container` / `_battery_symbol`) — instead of one
  stretched glyph in an over-wide slab.
  Geometry only — the electrical topology, feeder spans, ratings and AC-sizing are
  unchanged; the render regression baseline was regenerated.
- **Shared DC Block drawing redesigned** — when several PCS share one DC Block,
  the renderer no longer converges the feeders left/right onto a small centred
  block (which read as one block fed from both sides). It now draws ONE wide
  multi-port container spanning under the feeders it serves, and each PCS drops
  STRAIGHT DOWN into its own output terminal directly beneath that PCS. The
  electrical rule is unchanged (independent output circuit per PCS, common bus
  inside the block; no external branch bus). `_bess_block` gained `symbol_span`
  so the wide container keeps a normal-sized centred battery glyph.
- **Report watermark fail-closed** — `_stamp_not_for_construction` no longer
  returns the original image on error; it substitutes a visibly-marked red
  placeholder (`_watermark_failure_placeholder`) or raises `WatermarkError` to
  abort export (never an unmarked drawing). All §7/§8/§9 captions carry
  NOT FOR CONSTRUCTION; a full-report regression
  (`tests/test_report_watermark_fullreport.py`) unpacks the DOCX for the
  non-governed, governed-bilateral and governed-mixed paths and asserts every
  concept figure is watermarked.
- **Transformer winding drawn for unconfirmed vector group (owner decision)** —
  the engineering_v2 renderer no longer draws the red "NOT A DRAWING" placeholder
  box. An unconfirmed vector group is now drawn with the real interlocked-circle
  symbol using the standard default (`Dyn11` / `Dyn11yn11`, via
  `_default_vector_group`) and annotated `assumed (standard default - to be
  confirmed)`. The wye (star) symbol keeps all three arms — the lower
  star-point / neutral arm is intrinsic to the symbol, not grounding — and no ANSI
  earth symbol is ever fabricated from a vector group. The **formal-readiness gate
  is unchanged** — an unconfirmed or assumed-default group still marks the sheet
  non-official (CONCEPT watermark), so the drawing is readable without
  over-claiming.

Detailed rationale: `CURRENT_STATUS_2026-07-12.md` §2.7 (SLD head-fleet), §2.8
(report head-representative), §2.9 (Codex round 1), §2.10 (dropdown + vector
gate + placeholder), §2.11 (sheet redesign), §2.12 (NOT-FOR-CONSTRUCTION rule).

## 3. End-to-end coherence (audited)

The mixed / SLD chain is consistent front-to-back:
`AC Sizing (per-block table)` → `ac_output (breakdown + per-block lists)` →
`Report §6.1 head/tail, §8/§9 head-representative` → `SLD head-fleet, non-official` →
`Interactive Layout (already per-block)` → `Product catalogue (basis-tagged)`.
Formality is enforced at the authoritative layer (`sld_formal_readiness_service`):
a drawing is non-formal if it is a representative head fleet, an unconfirmed /
mismatched vector group, or an assumed standard-default vector group; and the
**report always stamps NOT FOR CONSTRUCTION regardless**.

## 4. Standing rules recorded this stage

1. **Report figures are always NOT FOR CONSTRUCTION** — embed via
   `report_v2._add_concept_figure`, never a bare `doc.add_picture`.
2. **No auto three-winding by PCS count** — winding count is operator-selected;
   defaults only supply the vector group *for an already-chosen* winding count.
3. **Assumed values are never formal** — any `*_basis =
   standard_default_pending_confirmation` is refused by the formal-readiness gate.
4. **SLD V1 is uniform-only** — a mixed station renders via the head-fleet
   projection; a true **per-model mixed SLD** (draws every AC Block model) is a
   deferred *data-contract* enhancement — NOT the same as the "Engineering V2"
   renderer mode in the SLD dropdown.

## 5. Residuals / deferred (none blocking)

- **Per-model mixed SLD** — draw head *and* tail blocks; needs the versioned
  uniform invariant + topology builder + renderer extended. (Data-contract
  feature; not the "Engineering V2" renderer mode. Formerly nicknamed "SLD V2"
  — renamed to avoid colliding with the renderer's "V2" name.)
- **Manual-mixed vs governed** — a run carrying both `configuration_code` and
  `ac_block_mixed` is an untested combination; low-priority edge case.
- **Cosmetic** — in a multi-DC-per-feeder layout the `BESS-0x` tag can slightly
  overlap the adjacent container box; label placement tweak only.
- **Product catalogue OEM data** — the 10 KEHUA records carry assumed
  `standard_default` vector groups (kept non-formal); real OEM values would
  upgrade them to `datasheet` basis.

## 6. For the next session

1. Read `CURRENT_STATUS_2026-07-12.md` module map (§4.1) first.
2. Work on `ops/ubuntu-docker-coexist-20260311` directly (owner directive: no
   new branches); commit with `noreply@anthropic.com`.
3. Run `python -m pytest tests/ -x -q` before committing; regenerate the SLD
   baseline via `scripts/generate_sld_regression_baseline.py` only when a
   *deliberate* rendering change is made, and confirm geometry is unchanged.
