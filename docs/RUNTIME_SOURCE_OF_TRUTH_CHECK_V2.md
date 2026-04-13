# Runtime Source Of Truth Check V2

Date: 2026-04-13  
Branch: `ops/ubuntu-docker-coexist-20260311`

## Scope

This phase checks whether the current Streamlit page runtime is truly DB-backed and applies the minimum fix required by the Phase 2 target:

- confirm the real runtime source for DC / AC / SLD pages
- stop treating session as the only truth for SLD
- make SLD prefer persisted authoritative run data over legacy compatibility state

This phase does **not** attempt to complete the full AC / SLD / Layout DB migration.

## Current Runtime Status After Phase 2

### DC page

Runtime source:

- Primary persisted source: DB `dc_case_input` + `dc_pipeline_output`
- Compatibility runtime cache: `restore_run_bundle_to_session()` rebuilds:
  - `st.session_state["dc_result_summary"]`
  - `st.session_state["stage13_output"]`
  - `st.session_state["poi_nominal_voltage_kv"]`
  - `st.session_state["grid_kv"]`

Conclusion:

- DC run restore is DB-backed.
- The page still consumes rebuilt session compatibility objects at runtime, but those objects are seeded from DB.

### AC page

Runtime source:

- Upstream input still comes from restored session compatibility objects:
  - `dc_result_summary`
  - `stage13_output`
  - `poi_nominal_voltage_kv`
- AC sizing still executes in-page and still writes runtime cache to:
  - `st.session_state["ac_output"]`
  - `ac_results`
  - `project_state["ac_results"]`

New in Phase 2:

- AC page now also persists the runtime AC snapshot into DB as:
  - `run_output_snapshot.snapshot_kind = "ac_runtime_snapshot_v1"`

Conclusion:

- AC page itself is **not yet fully DB-driven** at runtime.
- But AC output is no longer session-only; persisted AC runtime data now exists and can be consumed downstream.

### SLD page

Old behavior:

- SLD page built `AcSnapshot` from:
  - `st.session_state["ac_output"]`
  - `project_state["ac_results"]`
  - `state.ac_results`
- DB only supplied DC-side run bundle.

New behavior in Phase 2:

SLD AC runtime resolution priority is now:

1. DB persisted AC snapshot  
   `run_output_snapshot(snapshot_kind="ac_runtime_snapshot_v1")`
2. Compatibility adapter  
   `project_state["ac_results"]` / `state.ac_results` + `ac_inputs`
3. Session cache  
   `st.session_state["ac_output"]` + `st.session_state["ac_inputs"]`

Selection is provenance-aware:

- when a target `run_id` is known, a candidate AC snapshot must carry matching `source_run_id`
- stale compatibility or session data for another run is rejected instead of silently winning by lookup order

Conclusion:

- SLD is no longer session-first.
- SLD now prefers persisted authoritative run data.
- Session remains a fallback cache only.

## Key Code Changes

### 1. DC bundle lookup is now kind-aware

`RunRepository.get_run_bundle()` now prefers:

- input: `dc_case_input`
- output: `dc_pipeline_output`

This matters because AC runtime snapshots are now stored in the same `run_output_snapshot` table. Without kind-aware selection, the latest AC snapshot could accidentally replace the DC pipeline snapshot during run restore.

### 2. AC runtime snapshot is now persisted

New persisted object:

- `run_output_snapshot.snapshot_kind = "ac_runtime_snapshot_v1"`

Payload:

- serialized `AcSnapshot`

Producer:

- `calb_sizing_tool/ui/ac_view.py`

### 3. SLD page now resolves AC runtime by source priority

New service:

- `calb_sizing_tool/services/sld_data_source_service.py`

Responsibilities:

- persist AC runtime snapshot
- load persisted AC runtime snapshot
- resolve preferred AC snapshot with priority:
  - persisted run snapshot
  - compatibility adapter
  - session cache

## Pages Still Not Fully DB-Taken-Over

### Still not fully DB authoritative

- AC page runtime inputs
- Report Export runtime merge logic
- Site Layout page runtime AC source

### Improved this phase

- SLD page runtime AC source
- DB persistence of AC runtime output
- DC bundle restore safety after adding non-DC output snapshots

## Remaining Limits

1. Restoring a run does not yet repopulate AC session cache from persisted AC snapshot.
   SLD can read persisted AC data directly, but AC page still behaves as an in-page calculator instead of a fully restored DB-first runtime.

2. Layout page still uses legacy session/project-state AC snapshot resolution.
   This phase intentionally did not expand the patch to Layout because the minimum acceptance target only required SLD to prefer persisted authoritative data.

3. Report Export still merges `ac_results` and raw session `ac_output`.
   It has not yet been switched to a persisted-first chain.

4. Case/project repositories still provide registry metadata, not downstream page runtime snapshots.

## Acceptance Check

- [x] It is now explicit which pages are and are not DB-backed.
- [x] SLD prefers persisted authoritative data over session cache.
- [x] Session is no longer the only runtime truth for SLD.
- [x] AC runtime data now has a persisted snapshot path.
- [x] DC bundle restore remains stable after adding AC runtime snapshots.
