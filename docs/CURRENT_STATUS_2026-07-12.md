# Current Status 2026-07-12

Branch: `ops/ubuntu-docker-coexist-20260311`
Milestone commit: `b992818` — "SLD Proposal Package V1 + Site Constraint Set V1"
Verification: `python -m compileall` clean, 215/215 tests passing (~50 s).

This document records the state of the proposal-output governance version and
the agreed direction for future maintenance decomposition. The previous status
baseline (`CURRENT_STATUS_2026-04-13.md`) remains valid as the frozen sizing
reference; this document supersedes it only for SLD/Layout document governance.

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
| SLD engine | `sld/` (18 files, 3.1k), `services/sld_*`, `schemas/sld_*`, `schemas/ac_electrical_topology.py`, `schemas/governed_ac_block_config.py`, `adapters/ac_to_sld_adapter.py` | ~6k lines | High — owns AC-to-SLD physical topology contract and the governed AC Block configuration; remains the most active area |
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
