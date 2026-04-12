# SLD DB Governance V1

This document freezes the database-backed runtime governance for DC -> AC -> SLD after the refactor branch diverged from the server-stable branch `refactor/streamlit-structure-v1`.

## Why This Patch Was Required

The older server-stable branch effectively treated DC run data as the source of truth for POI / MV values when AC sizing and SLD were opened later. The refactor branch introduced DB-backed run restore, but left downstream AC/SLD session state alive across run changes.

That created a real failure mode:

1. User restores or switches to DC run `A`
2. Session still contains `ac_output` from prior run `B`
3. SLD builder reads AC result first for `mv_voltage_kv`
4. Final SLD uses the wrong voltage level even though the DC run bundle already contains the correct `case_input.poi_nominal_voltage_kv`

This is forbidden in the DB-backed version.

## Frozen Governance Rules

### 1. Persisted DC case input is authoritative for POI / MV / frequency

For SLD generation, the authoritative persisted fields are:

- `case_input.poi_nominal_voltage_kv`
- `case_input.poi_frequency_hz`

If AC runtime data also carries the same meaning:

- the persisted case input wins
- any mismatch is a validation error in strict mode
- the system must not silently choose one side

### 2. AC output is only valid for the run/case/project that produced it

`ac_output` must carry provenance fields:

- `source_project_id`
- `source_case_id`
- `source_run_id`
- `source_ac_run_id`

SLD generation is allowed only when the AC snapshot matches the active / requested DC run context.

If provenance is missing or mismatched:

- SLD must refuse formal generation
- user must re-run AC sizing for the active database run

### 3. Restoring a DC run must clear downstream AC / SLD runtime state

`restore_run_bundle_to_session()` must clear:

- `ac_output`
- `ac_inputs`
- `ac_results`
- selected AC ratio / transient AC choices
- SLD preview artifacts and SLD trace metadata

Reason:

- AC is not persisted as part of the formal DC run bundle
- stale downstream session state must never survive a run switch

### 4. Restore must re-seed the shared runtime voltage fields from the run bundle

After restoring a run, the session must be re-seeded from persisted case input:

- `poi_nominal_voltage_kv`
- `grid_kv`
- `poi_frequency_hz`
- `ac_inputs.grid_kv`
- `ac_inputs.mv_kv`
- `ac_inputs.grid_frequency_hz`

This keeps later AC/SLD pages aligned with the restored run before any further user action.

## Code Boundary

The governance is enforced in these places:

- `calb_sizing_tool/state/workspace_state.py`
  clears downstream AC/SLD state and re-seeds runtime voltage/frequency from the run bundle
- `calb_sizing_tool/ui/ac_view.py`
  stamps AC output with project/case/run provenance
- `calb_sizing_tool/ui/single_line_diagram_view.py`
  rejects AC snapshots whose provenance does not match the active/requested run
- `calb_sizing_tool/services/sld_input_builder.py`
  prefers persisted case input for MV/frequency and raises on conflict

## Change-Control Rule

Future UI refactors, DB migrations, or SLD renderer changes must preserve these rules.

Any future change is not allowed to:

- let session-only AC data override persisted case input for POI / MV / frequency
- reuse AC output across runs without provenance validation
- keep downstream AC / SLD state alive after run/case/project changes
- silently downgrade a DB-vs-AC conflict into a warning while still generating a formal SLD
