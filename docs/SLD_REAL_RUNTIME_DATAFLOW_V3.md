# SLD V3 Real Runtime Dataflow

Scope: current observed runtime flow for SLD generation. This document records how data actually moves today and where the priority is not yet aligned with the V3 target.

## Current Main Runtime Flow

```text
AC page
  -> session/shared AC state
  -> optional persisted AC runtime snapshot on run

SLD page
  -> active workspace/run selection
  -> run bundle from DB
  -> preferred AC snapshot resolver
  -> case/run SLD project settings
  -> canonical SLD input
  -> SLD topology
  -> engineering renderer
  -> persisted artifacts + session preview
```

## AC Runtime Snapshot Priority

`calb_sizing_tool/services/sld_data_source_service.py` currently resolves AC runtime data as:

| Priority | Source | Mode Meaning | Current Risk |
| --- | --- | --- | --- |
| 1 | persisted run output snapshot `ac_runtime_snapshot_v1` | authoritative persisted AC runtime data | correct priority for AC snapshot |
| 2 | compatibility adapter from project/shared state | compatibility bridge | can look too formal unless the page marks it as draft/compatibility |
| 3 | session cache | session draft | can preserve stale values across UI actions |

This resolver is the right direction. The remaining issue is that not every SLD field display follows this priority.

## MV / RMU Display Dataflow

Current AC page behavior:

```text
stage13.poi_nominal_voltage_kv
  -> session poi_nominal_voltage_kv/grid_kv
  -> ac_inputs grid_kv/mv_kv
  -> AC output aliases
  -> persisted AC runtime snapshot if run context exists
```

Current SLD page MV form behavior:

```text
session poi_nominal_voltage_kv
  -> project_state dc_inputs poi_nominal_voltage_kv
  -> shared state dc_inputs poi_nominal_voltage_kv
  -> ac_snapshot.output mv_voltage_kv
  -> ac_snapshot.inputs grid_kv
```

Target behavior for later phases:

```text
persisted authoritative run/case data
  -> compatibility adapter
  -> session draft cache
```

Current RMU display behavior:

```text
visible RMU rated voltage = resolve_mv_rmu_voltage_contract(visible MV).rmu_rated_voltage_kv
```

The current contract maps RMU rated voltage exactly to MV voltage. That matches the V3 visible-page requirement. The remaining issue is that the visible MV source priority is still session-first in the SLD page.

## Formal Generation Dataflow

When the user clicks Generate SLD in `single_line_diagram_view.py`, the current formal path is:

1. Validate selected `run_id`.
2. Load the run bundle through DB repositories.
3. Validate active project/case/run context.
4. Load run-linked SLD project settings through `load_run_sld_project_settings()`.
5. Build render options.
6. Pass run bundle, AC snapshot, options, overrides, and project settings to `run_sld_pipeline_from_run_bundle()`.
7. Build `SldCanonicalInput` in `sld_input_builder.py`.
8. Build `SldTopology` in `sld_topology_builder.py`.
9. Render through plugin `sld_engineering_v1`.
10. Persist artifacts and store a session preview pointer.

The pure renderer entrypoint is `render_sld_svg(topology, ...)`. It does not inspect Streamlit session, AC dicts, DC dicts, or stage outputs directly.

## Settings Dataflow

Current settings read/write behavior:

| Area | Current Source |
| --- | --- |
| Settings form initial value | active case settings through `load_case_sld_project_settings(workspace.case_id)` |
| Generate SLD settings | run-linked case settings through `load_run_sld_project_settings(run_id)` |
| Save settings | `CaseRepository.save_case_project_settings()` under `input_json["project_settings"]` |
| RMU rated voltage in saved settings | overwritten from MV/RMU contract before save |

Risk: the displayed settings form and the generated run settings can diverge if the active workspace case and selected run case are not the same. The current page has context validation, but Phase 2 should make the source-of-truth status more explicit.

## Data Item Source Table

| Data Item | Persisted Source | Session / Compatibility Source | Current Effective Priority |
| --- | --- | --- | --- |
| DC run input/output | run snapshots via `RunRepository.get_run_bundle()` | none for formal generation | persisted first |
| AC runtime output | `ac_runtime_snapshot_v1` output snapshot | project/shared state, session cache | persisted, then compat, then session |
| MV visible form value | not consistently first | session/project/shared before AC snapshot | session first today |
| RMU visible form value | derived from visible MV | draft default if MV missing | follows whatever MV display resolved |
| SLD labels/equipment ratings | case `project_settings` | override payload or draft preset | strict rejects missing; draft fills |
| Generated artifacts | artifact persistence | session preview cache | persisted artifacts plus session preview |

## Legacy Paths

The following paths still exist for compatibility:

- `build_single_unit_snapshot()` in `snapshot_single_unit.py`
- `build_ac_block_group_spec()` in `ac_block_group.py`
- `build_sld_group_spec()` and `build_topology_from_legacy_sld_group_spec()` in `calb_diagrams/specs.py`
- `render_sld_pro_svg()` compatibility wrapper in `sld_pro_renderer.py`

These paths should not become the formal source of truth. They are useful only if they adapt already-authoritative data into old shapes without inventing topology, PCS counts, transformer ratings, or DC allocation.

## Formal Mode Vs Draft / Session Mode

Current validation mode:

```text
override mode off -> strict
override mode on  -> draft
```

Current source mode:

```text
persisted_run_snapshot
compatibility_adapter
session_cache
```

Problem: validation mode and source mode are related but not identical. A strict validation run can still start from a compatibility AC source if persisted AC data is missing. Phase 2 should make the page state explicit:

- persisted authoritative mode: DB/run-backed AC snapshot and run/case settings are active
- draft/session mode: compatibility adapter or session cache is used

The page must not let a session-only or compatibility-derived diagram look like a formal persisted diagram.

## Renderer Boundary

Current renderer boundary:

```text
SldTopology -> build_sld_layout_plan() -> render_sld_svg()
```

This boundary is mostly correct because allocation logic is outside the renderer. The current engineering issue is the template encoded in the layout plan:

- top MV area is still drawn as a bus with RMU below it, not explicit Ring In / Transformer Feeder / Ring Out switchgear structure
- topology still carries a per-feeder `dc_busbar` abstraction, which can be visually misleading for a 1 PCS : 1 DC Block one-line SLD
- equipment list mirrors topology/equipment ratings, so upstream MV/RMU drift will appear in the table

Phase 4 should keep the renderer as a topology consumer, but replace the visual template with the Engineering Readable Block SLD template.

## Phase 0 Dataflow Conclusion

The project has moved beyond a pure Streamlit-session prototype for formal SLD generation, but the SLD page is not yet fully governed by persisted authoritative data. The next phases should close the gaps in this order:

1. Phase 1: force the visible MV/RMU voltage contract to one authoritative display value.
2. Phase 2: make persisted authoritative data the page priority and label session/compatibility output as draft.
3. Phase 3: lock one AC-to-SLD field contract and one legacy adapter boundary.
4. Phase 4: replace the SLD layout template with an engineering-readable block SLD.
