# Optimization Execution Plan 2026-06-17

## Non-Negotiable Rule

Business sizing logic is frozen. This optimization work must not change:

- DC Stage 1 formulas, input normalization, S&C loss mapping, or efficiency chain
- DC Stage 2 block selection, scenario semantics, or `K_MAX_FIXED`
- DC Stage 3 SOH/RTE selection, yearly calculation, or monotonic RTE handling
- guarantee-year augmentation strategy
- AC ratio set, PCS standard library, AC block count formulas, validation thresholds, or DC-to-AC allocation
- SLD/Layout/Report engineering meaning derived from those outputs

Frozen references:

- `docs/SIZING_LOGIC_CANON_V1.md`
- `docs/DATA_MODEL_MAP_V1.md`
- `docs/RUNTIME_SOURCE_OF_TRUTH_CHECK_V2.md`
- `docs/CURRENT_STATUS_2026-04-13.md`

## Current Business Chain Summary

1. DC page collects case inputs and defaults from the DC workbook.
2. `stage1_service.py` computes normalized inputs, efficiency chain, S&C loss, and DC requirement.
3. `stage2_service.py` selects DC block templates and quantities by scenario.
4. `stage3_service.py` selects SOH/RTE profiles and computes yearly POI usable energy.
5. `dc_pipeline_service.py` performs guarantee-year augmentation.
6. `run_persistence_service.py` stores Project, Case, Run, input snapshot, and output snapshot.
7. AC sizing consumes the selected DC result and produces the AC runtime output.
8. SLD/Layout/Report consume persisted run data and AC outputs; they must not re-define sizing.

## Optimization Scope

### Phase 1: Runtime And Deployment Safety

- Persist Docker SQLite database under the bind-mounted runtime state directory.
- Keep generated outputs and preferences in runtime mounts.
- Add a first-admin bootstrap token guard for deployed empty databases.
- Make startup migration failures fail fast unless an explicit local fallback flag is enabled.

### Phase 2: File And Artifact Safety

- Sanitize uploaded/stored filenames.
- Prevent path traversal outside configured asset and artifact directories.
- Add unit tests for unsafe filename inputs.

### Phase 3: CI And Release Verification

- Add a minimal CI workflow:
  - install dependencies
  - run Alembic migration against a temporary SQLite DB
  - run the full test suite
- Preserve existing local fixed-port development flow.

### Phase 4: DB-First Runtime Completion

This phase is intentionally separated because it touches page runtime sources. It must be done only after Phase 1-3 are green:

- AC page restores persisted AC runtime by run_id.
- Layout reads persisted AC snapshot before session/project cache.
- Report Export reads persisted run/artifact data before session/file fallback.

Phase 4 must keep all V1 sizing canon tests and golden cases unchanged.

Execution update:

- AC page hydrates the active persisted AC runtime snapshot and displays the saved AC configuration without re-running sizing.
- Layout resolves AC runtime data through the same persisted-first chain as SLD.
- Report Export resolves AC runtime and SLD/Layout artifacts from DB before session/file fallbacks.
- AI Layout Prompt uses the persisted AC snapshot when available instead of issuing AC assumptions from an empty snapshot.

### Phase 5: Dedicated SLD Engineering Settings Storage

- Formal SLD engineering settings move to the dedicated `sld_project_settings` table.
- Existing settings stored under `SizingCase.input_json["project_settings"]` are backfilled during migration.
- Runtime loading keeps legacy JSON fallback for old or partially migrated databases.
- SLD rendering meaning remains unchanged; this phase only changes persistence ownership.

Execution update:

- The SLD page no longer owns the formal engineering settings edit form.
- A dedicated `Engineering Settings` page owns formal SLD settings maintenance and recent save history.
- The SLD page keeps using saved settings for generation and links users to the dedicated maintenance page.

## Required Verification

Before considering any phase complete:

- `python -m compileall -q app.py calb_sizing_tool calb_diagrams`
- `python -m alembic upgrade head` against a temporary SQLite DB
- `python -m pytest -q`
- `git diff` review must show no changes to frozen sizing modules unless explicitly approved as a logic upgrade
