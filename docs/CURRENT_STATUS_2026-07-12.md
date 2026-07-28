# Current Status 2026-07-12

Branch: `ops/ubuntu-docker-coexist-20260311`
Milestone commit: `b992818` — "SLD Proposal Package V1 + Site Constraint Set V1"
Verification: `python -m compileall` clean, 215/215 tests passing (~50 s).

This document records the state of the proposal-output governance version and
the agreed direction for future maintenance decomposition. The previous status
baseline (`CURRENT_STATUS_2026-04-13.md`) remains valid as the frozen sizing
reference; this document supersedes it only for SLD/Layout document governance.

## Active AC Sizing direction (owner decision, 2026-07-27)

For new AC runs, `AC_SIZING_UNIFIED_FLOW_V2_2026-07-27.md` is the governing
handoff. It replaces the UI-level governed-product preset with one generic
grouping -> PCS -> explicit topology -> optional product-match flow. The
supported grouping set now includes 1:8, but 1:8 is not a locked standard
product: 2 x 2,500 kW remains the normal comparison preference and 8 x 1,250
kW is an optional small-PCS candidate only for a user-selected 1:8 case.

Local verification on 2026-07-27: `AC_SIZING_UNIFIED_FLOW_V2_2026-07-27.md`
records 477 passing tests and a real Guest 1:8 -> 8 x 1,250 kW -> 3-winding
catalogue-bound SLD render. Guest SLD previews are intentionally not persisted;
formal run artifacts remain a signed-in, traceable workflow.

Cloud implementation handoff and the machine-enforced cross-module acceptance
contract are in `CLAUDE_CLOUD_AC_SIZING_SLD_EXECUTION_GUIDE_2026-07-28.md` and
`tests/integration/test_claude_ac_sizing_handoff.py`. They record the active
new-run rules, P0/P1/P2 remaining work and the requirement that 1:8 remain a
generic grouping rather than a product lock. The 2026-07-28 checkout collected
481 tests and passed the full suite after adding that contract; the 477 figure
above remains the 2026-07-27 historical verification record.

Sections 2.3–2.5 below are retained as implementation history and compatibility
context for persisted governed outputs. They must not be used to restore the
old checkbox or a separate sizing engine.

## 1. Completed in this version

### SLD Proposal Package V1 (P1)

- `services/sld_proposal_package_service.py` issues SLD-01 Site Electrical
  Index, SLD-03 Electrical Design Basis Schedule and SLD-04 Concept
  Interface/Scope sheets (JSON/SVG/PNG) around the typical SLD-02 drawing.
- `document_status` tri-state (`official` / `concept` / `draft_override`)
  drives watermarks, `.concept`/`.draft` file suffixes, artifact metadata,
  UI copy and docx report captions.
- Concept issues scrub renderer `MISSING: <label>` markers by pattern, not by
  label text; a readiness manifest artifact carries the full issue register
  with per-artifact content hashes.
- SLD-03 renders at most six issues and prints an explicit "... and N more"
  note pointing to the manifest.

### Site Constraint Set V1 (P2 gate)

- `services/site_constraint_readiness_service.py` +
  `services/site_constraint_set_service.py`: nine input groups (CRS, boundary
  polygon, POI location, routes, fire/maintenance, footprint catalogue, MV
  corridor, rule basis, by-others interfaces) must be present before any
  future Concept Master Layout is unlocked.
- Incomplete uploads persist as `draft_incomplete` with audit history.
- Registration rejects a constraint set whose `source_run.run_id` names a
  different run.

### Rename and fixes

- "Site Layout" page renamed to "Typical AC Block Arrangement" everywhere
  (nav with legacy alias, login copy, reports, docs); layout artifacts carry
  a concept watermark.
- `artifact_service.load_artifact_bytes_from_db` reads value tuples inside
  the session scope (no detached ORM access).
- Layout plugin emits per-artifact metadata dicts (no shared-dict aliasing).
- Official documents reuse the already-rendered PNG instead of re-rendering.

## 2. Deferred items (low priority, tracked here)

1. `ui/site_layout_view.py` reloads the persisted Site Constraint Set from
   DB+disk on every Streamlit rerun — cache in `st.session_state` keyed by
   run_id, invalidated on register.
2. Uploaded Site Constraint Set JSON has no size cap before persistence.
3. Concept value scrubbing is a post-render regex in
   `sld_pipeline_service._concept_safe_svg`; the cleaner design is for the
   renderer to emit placeholder text directly from `document_status`.

## 2.1 SLD drawing quality hardening (2026-07-15)

Professional redraw of the transformer symbols (3-winding = three interlocked
equal circles per IEC 60617/ANSI 315; winding marks derived from the vector
group), label/wire collision fixes, and a rendered-SVG quality gate
(`validate_rendered_sld_svg`) that asserts geometry on the actual SVG output.
Root-cause analysis and binding rules for all future diagram work (including
P2 Master Layout): `DIAGRAM_QUALITY_GOVERNANCE_2026-07-15.md`. Regression
baseline case01 regenerated.

## 2.2 AC Block product & arrangement knowledge base (2026-07-18)

`AC_BLOCK_PRODUCT_KNOWLEDGE_2026-07-18.md` records the 5.015 MWh product
construction, owner-confirmed appearance rules (mirrored pairing, roof vents on
the no-door edge, cooling-bay and end-face composition, livery positions), the
international arrangement code basis (IFC/NFPA 855/NFPA 850/UL 9540A — owner
decision: no GB), the Sineng/NR-based PCS & MV Station composition of the AC
Block, and site-array logic. The parametric concept renderer lives at
`docs/concept/ac_block_concept_render.html`. Feed both into P2 Master Layout
and any future 3D rendering work. The staged implementation plan (L1 unit
arrangement engine → L2 site-array concept → L3 Master Layout, plus report
integration as §8 upgrade / new §9) is `LAYOUT_ROADMAP_V1_2026-07-18.md`.

## 2.3 Active Claude handoff: 10 MW / 8 PCS / 8 DC (2026-07-24)

Before changing code, read
`CLAUDE_HANDOFF_10MW_8PCS_8DC_2026-07-24.md` in full. It records the
owner-confirmed bilateral 4+4 `田`-shaped DC arrangement around one central,
vertically placed 40 ft AC Block, the recommended governed-configuration
upgrade, open engineering decisions, and the recovery boundary that was used
for the mixed worktree.

Recovery completed on 2026-07-24: the invalid linear 1:8 draft was surgically
removed while the previously verified L2 Site Array and report integration
were preserved. `compileall`, the 23-test L2 target set, and the full suite
(`326 passed`) are clean. The governed bilateral 4+4 1:8 configuration remains
an implementation task; it is not present in this recovered baseline.

## 2.4 Governed AC Block 10 MW / 8 PCS / 8 DC — Phase A (2026-07-24)

The bilateral 4+4 1:8 configuration handed off in §2.3 is now implemented as a
**governed configuration** (Phase A). See
`GOVERNED_AC_BLOCK_10MW_8PCS_8DC_2026-07-24.md`.

- `schemas/governed_ac_block_config.py` (new) is the single contract
  (`ACBLK-10MW-8PCS-8DC-40FT-BILATERAL`) that threads
  `configuration_code` / `layout_variant` through AC Sizing -> SLD -> Layout ->
  Site Array -> Report. Phase A gate: `dc_blocks_total % 8 == 0`; mixed tails
  stay deferred.
- `calb_diagrams/ac_block_bilateral_layout.py` (new) is the
  `central_40ft_bilateral_4plus4` engine emitting per-equipment placements
  (~18.79 × 13.02 m envelope), not just one envelope.
- SLD render layer gained a LV-secondary busbar collision fix for wide feeder
  counts (8 PCS split 4+4); no topology/sizing change. The
  `[1,1,0,0]` dangling-PCS defect was re-verified and remains repaired at the
  physical-connection layer.
- Provisional engineering values (transformer MVA/vector group/Uk%/LV V/cooling,
  actual 40 ft dims, aisle/pair-to-pair gaps) stay gated as `None` and are never
  inferred. Frozen sizing is unchanged (`git diff` over frozen modules empty).
- L2 Site Array / report integration from `252bc75` preserved unchanged.
- Report-layer consistency (Phase A finishing): the report no longer fabricates
  a transformer nameplate for governed configs (no silent 10 MW / 0.9 = 11.11
  MVA), report §8 routes to the bilateral engine by `layout_variant`, and the
  linear §9 site figure is suppressed for the bilateral variant. Ungoverned
  runs unchanged; locked by `tests/unit/test_report_governed_consistency.py`.

### 2.5 Governed AC POI power-closure gate (2026-07-27)

- `services/governed_ac_block_service.py` now evaluates the already-selected
  governed PCS capacity at the POI plane using the Stage 1 MVT, MV
  cable/switchgear and HVT efficiency handoff. It does not change a sizing
  formula or synthesize a smaller station configuration.
- A governed output is held when it cannot meet POI power or exceeds the
  temporary 10% POI oversize safety ceiling. The 200 MW / 202 DC example
  (252.5 MW installed PCS; approximately 249.23 MW deliverable at POI) is
  therefore held at approximately 24.6% excess instead of being persisted as
  a valid AC, SLD or report selection.
- The AC page now prefers the Stage 1/3 POI P/E handoff over legacy summary
  aliases. SLD rejects historical governed snapshots without a passing
  persisted POI-closure record, so an old one-DC-to-one-PCS result cannot be
  rendered as a current engineering selection. A physically usable smaller
  PCS/station mix remains a separate DC-augmentation and connection-contract
  implementation; it must not be represented by an average DC split.

### 2.6 AC-to-SLD transformer vector-group contract (2026-07-27)

- `sld/transformer_vector_group.py` is the shared authoritative parser for
  every AC Sizing route.  It requires exactly one declared LV vector token per
  independently drawn LV winding: `Dyn11` is valid only for a two-winding
  transformer; `Dy11y11` / `Dy11-y11` declares two LV windings.
- SLD strict mode rejects a vector/topology mismatch. Draft mode renders `TBD`
  without inferring a neutral or earth connection. `n` only means the neutral
  terminal is brought out; all `y` / `yn` / `z` / `zn` vector tokens render as
  a plain Y unless a future explicit grounding-design contract is provided.
- For governed catalogue products, product vector data cannot be silently
  overridden by a conflicting Engineering Settings value. The conflict is
  explicit (strict rejection or draft `TBD`). Engineering V2 SVG regression
  tests assert actual winding elements and the absence of earth-bar elements,
  including both low-voltage windings for `Dy11y11` and a `Dyn11` two-winding
  path.
- The approved `case01` regression fixture now explicitly declares its two
  LV neutral terminals as `Dyn11yn11`; normalized topology/render baselines
  are regenerated through `scripts/generate_sld_regression_baseline.py`.
- Generic AC Sizing no longer auto-selects a three-winding transformer merely
  because an AC Block has more than two PCS.  New runs, and legacy runs without
  an explicit confirmation marker, require the operator to select the actual
  secondary arrangement before they can be issued.  A three-winding selection
  warns that an OEM-declared vector group with two LV tokens is required.

### 2.7 Mixed AC Block station → SLD head-fleet projection (2026-07-28)

- The opt-in mixed AC Block station (head + tail models; report §6.1 schedule)
  produces a non-uniform `pcs_count_by_block`. The SLD authoritative contract
  is uniform-only *by design* — `schemas/sld_authoritative_input.py` requires
  `pcs_count_by_block` uniform in SLD V1 — so feeding a mixed output straight to
  `adapters/ac_to_sld_adapter.py` fails the contract (the adapter rebuilds a
  uniform plan from the scalar `pcs_per_block` and it no longer matches the true
  per-block lists). A mixed run therefore could not render an SLD at all.
- `services/ac_mixed_station.py` gained `head_fleet_ac_output_for_sld()`: it
  projects a (possibly mixed) AC output onto its **head AC-Block fleet** — a
  genuine uniform sub-station of the real site (same PCS count/rating; DC Blocks
  may still fill unevenly, which V1 permits), nothing fabricated. The tail
  model(s) remain fully described by the report §6.1 schedule.
- `ui/single_line_diagram_view.py` detects `ac_block_mixed` and swaps the
  resolved `ac_snapshot` for this head-fleet projection, with an explicit note
  that the SLD shows the representative head fleet and that tails live in the
  report. Uniform stations (including single-model, uneven-DC ones) are
  unaffected — the projection is an identity for them.
- A true per-model mixed SLD (drawing head *and* tail blocks) is deferred as an
  SLD V2 enhancement; it requires extending the versioned uniform invariant plus
  the topology builder and renderer, out of scope for this manual-adjustment
  layer.

### 2.8 Mixed AC Block station → report §8/§9 head-representative (2026-07-28)

- Follow-up audit of the mixed-station chain: the report's §8 (Typical AC Block
  Arrangement) and §9 (Concept Site Arrangement) still drew from the *fractional
  average* `dc_per_ac = round(dc_total / ac_total)`, which for a mixed station is
  a block that exists nowhere — inconsistent with §6.1 (head/tail schedule), §7
  (SLD head fleet) and the interactive Layout page (already per-block via
  `plugins/layout_engineering_plugin.py`, which reads `pcs_count_by_block[idx]`
  and the per-block `dc_allocation_plan`).
- `reporting/report_v2.py` gained `_representative_dc_per_ac()` /
  `_mixed_head_entry()`: §8 and §9 now draw the **Head AC Block** for a mixed
  station (identity/average for uniform, including single-model uneven-DC), with
  an explicit note pointing to §6.1. §9's whole-site power/energy come from the
  actual head + tail sizing (`total_ac_mw`, `dc_total_energy_mwh`) rather than a
  uniform multiplication of the head block, and the "DC/block" label is replaced
  by a mixed head + tail descriptor.
- Not changed (by design / flagged for later): the manual-mixed toggle is not
  gated from a governed run — a run carrying both `configuration_code` and
  `ac_block_mixed` is an untested combination (governed §9 vs manual §6.1); and
  the mixed editor allows a per-row PCS rating that the SLD head-fleet does not
  render for tails. Both are low-priority edge cases, not regressions.

### 2.9 Mixed AC Block station — formality boundary hardening (2026-07-28)

Review follow-up (Codex) closing three engineering-integrity gaps so a mixed
station is never mistaken for a formal engineering result:

1. **Product nameplate attribution.** A bound catalogue product only matches the
   HEAD spec; applying its transformer nameplate across a differing tail and
   labelling it "per block" was a false attribution. `ui/ac_view.py` now
   **disables single-product binding for a mixed run** (skips
   `product_transformer_overrides`, records `ac_block_product_binding_suppressed`)
   so every model falls back to a MW ÷ PF estimate; uniform runs keep the
   confirmed nameplate. Per-model product binding is future work.
2. **SLD formality.** The head-fleet projection was only forced non-official
   *incidentally* (head DC total ≠ whole DC total). `sld_formal_readiness_service`
   now raises an **explicit `representative_head_fleet_only` error** when
   `sld_representative_of_mixed` is set (→ `document_status=concept`, CONCEPT
   watermark, `not_for_construction`), and **suppresses the incidental
   head-vs-whole total/energy mismatches** so the drawing carries an honest
   reason. The marker is also threaded into `sld_pipeline_meta`.
3. **Validation boundary.** The manual table validates DC sum / feeder capacity /
   raw AC MW only — not per-model OEM data or full POI-efficiency capacity
   closure. It is now explicitly labelled **concept/draft** in the AC Sizing UI
   and in report §6.1, directing the user to confirm per-model product and
   transformer data before formal use.

### 2.10 SLD transformer-winding formality + renderer dropdown (2026-07-28, in progress)

Review of a rendered SLD (uniform 25×2-PCS station) surfaced that a
three-winding transformer with an unconfirmed vector group draws three "TBD"
winding circles behind a DRAFT watermark — not a readable engineering drawing.
Owner direction: (1) never pass a TBD-winding three-winding SLD off as a normal
drawing; (2) drop the legacy renderer from the public dropdown; (3) backfill AC
Block product topology / vector group / LV arrangement with standard defaults
marked *assumed, pending confirmation*; (4) add real page-export acceptance for
two-winding/`Dyn11` and three-winding/`Dyn11yn11` (plain Y, no earth bar,
busbar structure, PNG).

Landed so far (this increment):
- **#2 done** — `sld_renderer_mode_service` gains `PUBLIC_SLD_RENDERER_MODES`
  (`engineering_v2` only) + `DEV_ONLY_SLD_RENDERER_MODES` (`legacy_server`);
  `is_sld_renderer_mode_public`. The SLD page dropdown offers only the public
  mode; legacy is reachable only behind the dev entry `?sld_dev=1`. Legacy stays
  in `AVAILABLE_*` for dev tooling/tests.
- **#1 formality gate done** — `sld_formal_readiness_service` now raises
  `transformer_vector_group_unconfirmed` (missing/TBD) or
  `transformer_vector_group_topology_mismatch` (wrong LV-token count for the
  winding count), reading the authoritative resolved value from
  `canonical_input`. Strict build already *requires* a vector group; this makes
  the draft/TBD path carry an explicit non-formal reason.

Still open: **#1 renderer placeholder** (draw an explicit "vector group
unconfirmed — not a drawing" block instead of TBD winding circles),
**#3 product-data standard defaults**, **#4 two-/three-winding PNG acceptance**.

## 3. Next boundary

The package deliberately stops before a Concept Master Layout. Unlocking it
requires (in order): a registered complete Site Constraint Set, a controlled
equipment footprint catalogue, a deterministic geometry validator, and an
explicit project/authority rule basis. Do not extrapolate site geometry from
the AC Block index. See `SITE_CONSTRAINT_SET_V1.md` and
`SLD_PROPOSAL_PACKAGE_V1.md`.

## 4. Maintenance decomposition plan

Motivation: the repo is now ~30k lines of source plus 7k lines of tests.
Every agent session (Codex/Claude) that starts from zero re-reads large parts
of the tree, which is slow and error-prone. The codebase already has clean
seams; maintenance should exploit them instead of scanning everything.

### 4.1 Module map (2026-07-12)

| Domain | Packages | Size | Change frequency |
| --- | --- | --- | --- |
| Sizing core (FROZEN) | `services/stage*_service`, `dc_pipeline`, AC capacity/calculation services | part of `services/` (29 files, 6.3k lines) | Frozen — no edits without explicit logic-upgrade approval |
| SLD engine | `sld/` (18 files, 3.1k), `services/sld_*`, `schemas/sld_*`, `schemas/ac_electrical_topology.py`, `schemas/governed_ac_block_config.py`, `adapters/ac_to_sld_adapter.py`; mixed→SLD bridge in `services/ac_mixed_station.py` (`head_fleet_ac_output_for_sld`) | ~6k lines | High — owns AC-to-SLD physical topology contract and the governed AC Block configuration; SLD V1 is uniform-only, so mixed stations render via a head-fleet projection; remains the most active area |
| Diagram renderers | `calb_diagrams/` (incl. `ac_block_bilateral_layout.py`) | ~6.9k lines | Medium — renderer/template + governed layout-variant engines |
| Layout / constraint gate | `plugins/layout_*`, `services/site_constraint_*` | ~1k lines | Medium — P2 Master Layout work lands here |
| Reporting | `reporting/` (5 files, 2.0k) | 2k lines | Low — wording/section changes |
| Web UI | `ui/` (18 files, 6.7k), `state/`, `app.py` | ~7.5k lines | Medium — copy and workflow polish |
| Platform | `infra/` (36 files), `db/`, `importers/`, `adapters/`, `migrations/` | ~3.4k lines | Low — deployment/migration driven |

### 4.2 Working rules effective immediately (no code moves)

1. **Scope declaration first**: every task states up front which domains it
   touches. An agent reads only those domains plus this document — not the
   whole tree.
2. **This section is the navigation index**: update the module map in the
   same commit whenever a domain gains or loses responsibility, so future
   sessions can trust it instead of re-scanning.
3. **Frozen core stays frozen**: sizing formula modules are read-only;
   `git diff` review before commit must show no changes there (rule inherited
   from `OPTIMIZATION_EXECUTION_PLAN_2026-06-17.md`).
4. **Tests are partitioned by domain**: run the domain's tests during
   iteration; run the full suite once before commit.

### 4.3 Split roadmap (future, in order)

- **Step 1 — Import-boundary enforcement (cheap)**: add a lint/CI check that
  `ui/` imports only `services/` + `schemas/` + `state/`; `calb_diagrams/`
  imports nothing from `ui/` or `infra/`; sizing core imports nothing from
  SLD/layout/reporting. This makes the seams mechanical before any move.
- **Step 2 — Package extraction inside the repo**: promote `calb_diagrams` +
  `sld/` + diagram plugins into a `calb-diagram-engine` package with its own
  tests and doc index; reporting likewise. App remains one deployable.
- **Step 3 — Repo split (only if team/process needs it)**: diagram engine and
  sizing core become versioned dependencies of the web app. Do not split
  earlier than Step 2 proves stable, and never split the frozen sizing core
  away from its golden-case tests.

Trigger for Step 2: when SLD/Master-Layout work (P2) starts in earnest, the
diagram engine is the first extraction candidate — it is the largest
high-churn domain and has the fewest inbound dependencies.
