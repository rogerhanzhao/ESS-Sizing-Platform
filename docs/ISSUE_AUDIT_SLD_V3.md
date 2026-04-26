# SLD V3 Phase 0 Issue Audit

Scope: Phase 0 fact audit only. No renderer output, Layout, login, RBAC, or DC sizing math was changed in this phase.

Branch audited: `ops/ubuntu-docker-coexist-20260311`.

## Audited Files

- `calb_sizing_tool/ui/ac_view.py`
- `calb_sizing_tool/ui/single_line_diagram_view.py`
- `calb_sizing_tool/ui/sld_inputs.py`
- `calb_sizing_tool/state/session_state.py`
- `calb_sizing_tool/repositories/run_repository.py`
- `calb_sizing_tool/repositories/case_repository.py`
- `calb_sizing_tool/sld/snapshot_single_unit.py`
- `calb_sizing_tool/sld/ac_block_group.py`
- `calb_diagrams/specs.py`
- `calb_diagrams/sld_pro_renderer.py`
- `docs/REFACTOR_PHASE1_PLAN.md`

Additional runtime files checked because they sit on the actual SLD path:

- `calb_sizing_tool/services/sld_data_source_service.py`
- `calb_sizing_tool/services/sld_engineering_settings_service.py`
- `calb_sizing_tool/adapters/ac_to_sld_adapter.py`
- `calb_sizing_tool/services/sld_input_builder.py`
- `calb_sizing_tool/services/sld_topology_builder.py`
- `calb_sizing_tool/services/sld_pipeline_service.py`
- `calb_diagrams/sld_layout_engine.py`

## 1. MV And RMU Voltage Sources

Current MV voltage is not sourced from one place across the UI and SLD runtime.

In `calb_sizing_tool/ui/ac_view.py`, `_resolve_mv_kv()` resolves the AC page MV value from:

1. `stage13_output["poi_nominal_voltage_kv"]`
2. `st.session_state["poi_nominal_voltage_kv"]`
3. `ac_inputs["grid_kv"]`
4. `ac_inputs["mv_kv"]`
5. `st.session_state["grid_kv"]`
6. fallback `33.0`

After resolving it, AC view writes the same value back into session and AC inputs under multiple aliases:

- `st.session_state["grid_kv"]`
- `st.session_state["poi_nominal_voltage_kv"]`
- `ac_inputs["grid_kv"]`
- `ac_inputs["mv_kv"]`

In `calb_sizing_tool/ui/single_line_diagram_view.py`, `_resolve_mv_nominal_voltage_kv()` currently resolves the SLD form MV value from:

1. `st.session_state["poi_nominal_voltage_kv"]`
2. `project_state["dc_inputs"]["poi_nominal_voltage_kv"]`
3. `state.dc_inputs["poi_nominal_voltage_kv"]`
4. `ac_snapshot.output["mv_voltage_kv"]`
5. `ac_snapshot.inputs["grid_kv"]`

This is a key mismatch: even when `resolve_preferred_ac_snapshot()` finds a persisted run snapshot, the form-level MV display can still be driven by stale session/project-state values first.

In `calb_sizing_tool/ui/sld_inputs.py`, `render_electrical_inputs()` derives the visible RMU rated voltage from `resolve_mv_rmu_voltage_contract(mv_nominal_voltage_kv=...)`. The current contract in `calb_sizing_tool/sld/voltage_contract.py` maps RMU rated voltage to the exact MV value, so the visible contract is now `MV == RMU`.

However, if MV is unavailable, `sld_inputs.py` falls back to `rmu_defaults["rated_kv"]` or `24.0`. That fallback is useful for draft rendering, but it can hide missing MV source-of-truth problems if not marked as draft/session mode.

Persistence paths also force RMU to follow MV:

- `calb_sizing_tool/services/sld_engineering_settings_service.py` overwrites persisted `equipment_ratings.rmu.rated_kv` from the MV contract before saving case-level SLD settings.
- `calb_sizing_tool/services/sld_input_builder.py` calls `_sync_rmu_rated_voltage_to_mv()` and overwrites any mismatched RMU value while adding a draft warning.

Audit conclusion: the low-level MV/RMU contract already exists, but the SLD page still resolves the visible MV value from session before persisted AC/run data. Phase 1 must make the displayed value and persisted/runtime value share one authoritative visible field.

## 2. What The Final SLD Actually Consumes

There are two SLD chains in the codebase.

The current formal UI path in `calb_sizing_tool/ui/single_line_diagram_view.py` is:

1. Load selected run bundle from DB through `RunRepository.get_run_bundle()`.
2. Resolve AC runtime data through `resolve_preferred_ac_snapshot()`.
3. Load SLD project settings from the run's case through `load_run_sld_project_settings()`.
4. Call `run_sld_pipeline_from_run_bundle()`.
5. Build canonical SLD input in `sld_input_builder.py`.
6. Build topology in `sld_topology_builder.py`.
7. Render through the SLD engineering plugin and `calb_diagrams/sld_pro_renderer.py`.

In this formal path, the renderer does not read raw Streamlit UI dicts directly. The renderer consumes `SldTopology` through `render_sld_svg()`. The compatibility wrapper `render_sld_pro_svg()` still accepts legacy `SldGroupSpec`, but it converts it into topology first.

Legacy compatibility paths still exist:

- `calb_sizing_tool/sld/snapshot_single_unit.py`
- `calb_sizing_tool/sld/ac_block_group.py`
- `calb_diagrams/specs.py`

These files adapt old dict-based inputs (`stage13_output`, `ac_output`, `dc_summary`, `sld_inputs`) into the newer topology shape. They are marked as deprecated/legacy compatibility, but they still matter because tests and older call sites can route through them.

Audit conclusion: the final formal SLD path is topology-based, not raw UI-dict based. The unresolved risk is earlier in the data-source priority and compatibility adapters, not in the pure renderer entrypoint.

## 3. DB Values Vs Session / Project-State Values

DB-backed values currently include:

- DC run bundle through `RunRepository.get_run_bundle()`
- input snapshots and output snapshots through `RunRepository`
- persisted AC runtime snapshot kind `ac_runtime_snapshot_v1`
- case-level SLD project settings through `CaseRepository.get_case_project_settings()`
- generated SLD artifacts through artifact persistence

Session/project-state values currently include:

- shared Streamlit state containers initialized in `session_state.py`
- AC page working inputs and results
- `project_state["dc_inputs"]` and shared-state compatibility values
- SLD preview artifacts in `st.session_state["sld_artifacts"]`
- SLD pipeline preview metadata in `st.session_state["sld_pipeline_meta"]`
- SLD form MV display candidate through `st.session_state["poi_nominal_voltage_kv"]`

`calb_sizing_tool/services/sld_data_source_service.py` currently resolves AC runtime data in this order:

1. persisted run snapshot: `ac_runtime_snapshot_v1`
2. compatibility adapter from project/shared state
3. session cache

That priority is directionally correct for AC runtime data. The problem is that `single_line_diagram_view.py` does not consistently use that priority for every visible or generated field.

Audit conclusion: the database is partially in charge, but not fully in charge of the SLD page. Phase 2 must make persisted authoritative data the page-level source-of-truth priority and explicitly label session-only output as draft/session mode.

## 4. AC To SLD Field Contract Mismatches

`calb_sizing_tool/adapters/ac_to_sld_adapter.py` defines the intended AC-to-SLD contract and legacy aliases. The canonical fields include:

- `num_blocks`
- `pcs_per_block`
- `pcs_kw`
- `block_size_mw`
- `dc_allocation_plan`
- `dc_blocks_total_by_block`
- `dc_blocks_per_feeder_by_block`
- `pcs_count_total`

Legacy aliases still accepted by the adapter include:

- `ac_blocks_total -> num_blocks`
- `pcs_count_per_ac_block -> pcs_per_block`
- `pcs_power_kw` / `pcs_rating_kw_each -> pcs_kw`
- `dc_block_allocation -> dc_allocation_plan`
- `total_pcs -> pcs_count_total`
- `mv_kv` / `grid_kv -> mv_voltage_kv`

`calb_sizing_tool/ui/ac_view.py` still emits both canonical-looking fields and aliases. That is acceptable as a transition step, but it also makes it easy for callers to accidentally keep using old names.

The current formal builder in `calb_sizing_tool/services/sld_input_builder.py` calls `normalize_ac_output_for_sld()` and then reads normalized fields. This is the correct pattern.

Legacy paths in `snapshot_single_unit.py`, `ac_block_group.py`, and `specs.py` still adapt dicts into topology. They are stricter than earlier versions, but they remain a second entrance into SLD generation.

Audit conclusion: the contract is mostly centralized, but not yet organizationally final. Phase 3 should document one authoritative AC-to-SLD field map, make one adapter the only alias boundary, and prevent builders/renderers from accepting scattered legacy meanings.

## 5. Fallbacks Currently Masking Errors

The following fallbacks can hide missing or stale data:

- `ac_view.py` falls back MV voltage to `33.0`.
- `single_line_diagram_view.py` resolves visible MV from session/project-state before the resolved AC snapshot.
- `sld_inputs.py` falls back RMU rated voltage to draft defaults when MV is unavailable.
- `sld_data_source_service.py` falls back from persisted AC snapshot to compatibility adapter and then session cache.
- `sld_input_builder.py` can fill labels, transformer settings, equipment ratings, and DC voltage from legacy draft presets when validation mode is draft.
- `snapshot_single_unit.py` and legacy spec adapters still normalize old dict shapes.
- `sld_topology_builder.py` still models a per-feeder `dc_busbar` abstraction, which can be rendered as a local DC bus if the layout profile chooses to show it that way.

Some fallbacks are necessary for compatibility and draft mode. The unreasonable part is when these fallbacks are not clearly labeled as draft/session mode or when they affect visible formal values.

Audit conclusion: strict mode and draft mode exist, but source mode and validation mode are not fully tied together. Phase 2 must prevent session/compatibility output from looking formal.

## 6. Why The Drawing Structure Became Confusing

The bad SLD screenshots are not just a styling issue. The underlying causes are:

- The current MV topology still has generic nodes/edges: `mv_bus`, `rmu`, `transformer`, with edge types such as `mv_link` and `rmu_to_transformer`. It does not yet encode Ring In, Transformer Feeder, and Ring Out as explicit switchgear cubicles.
- `calb_diagrams/sld_layout_engine.py` still lays out the top MV area as a horizontal MV bus with an RMU symbol below it. That is exactly the structure the V3 requirement rejects.
- The topology still uses per-feeder `dc_busbar` nodes. For a 1 PCS : 1 DC Block one-line SLD, that abstraction is too strong unless rendered as a local DC interface/feeder, not as floating DC+ / DC- busbars.
- The renderer has improved separation from allocation logic, but the layout template is not yet the requested engineering-readable block SLD template.
- Equipment List values are derived from topology/equipment ratings. If upstream MV/RMU/project settings disagree, the table and drawing can expose that inconsistency.

Audit conclusion: Phase 4 must change the template/topology presentation, not only colors or spacing. The target should be an engineering-readable block SLD: Ring In -> RMU/MV Switchgear -> Transformer Feeder -> Ring Out, then Transformer -> LV Busbar -> feeder-labeled PCS -> DC interface -> DC Block.

## Phase 0 Bottom Line

Confirmed problems:

- MV/RMU visible value can still drift because SLD page MV display resolves session/project-state before the persisted AC snapshot.
- Formal SLD generation is not purely session-based, but the page does not yet make persisted/session/draft status strict enough.
- AC-to-SLD field normalization exists, but legacy aliases and compatibility paths remain.
- The renderer is topology-driven, but the current top MV layout and DC abstraction are not yet the requested engineering-readable block SLD.

Not changed in Phase 0:

- No renderer output changed.
- No Layout behavior changed.
- No login/RBAC behavior changed.
- No DC sizing math changed.
