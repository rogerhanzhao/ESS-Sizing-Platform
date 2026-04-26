# MV / RMU Voltage Contract V2

Scope: Phase 1 SLD fix. This contract governs the current visible project page values only.

## Contract

`POI / MV Voltage (kV)` is the single authoritative visible MV voltage field for the current workflow.

`RMU Rated Voltage (kV)` mirrors that same visible MV value:

```text
RMU Rated Voltage (kV) = POI / MV Voltage (kV)
```

There is no visible-page mapping such as:

- `22 kV -> 24 kV`
- `33 kV -> 36 kV`

The renderer must not infer, upgrade, or rewrite the visible RMU voltage from MV voltage.

## Current Source Priority For The Visible SLD MV Field

The SLD page resolves one visible MV value and passes it into the RMU settings form.

Priority:

1. resolved AC snapshot output: `mv_voltage_kv`
2. resolved AC snapshot output aliases: `grid_kv`, `mv_kv`, `source_poi_nominal_voltage_kv`
3. resolved AC snapshot input aliases: `grid_kv`, `mv_kv`, `poi_nominal_voltage_kv`
4. project/shared DC input: `poi_nominal_voltage_kv`
5. Streamlit session fallback: `st.session_state["poi_nominal_voltage_kv"]`

This means stale session values cannot override the active AC snapshot value.

## RMU UI Behavior

`calb_sizing_tool/ui/sld_inputs.py` derives the RMU voltage through:

```python
resolve_mv_rmu_voltage_contract(mv_nominal_voltage_kv=...)
```

The RMU voltage widget is disabled and uses a derived session key. Legacy manual RMU session keys are cleared before rendering:

- `rmu_rated_kv`
- `rmu_rated_kv_auto`
- `rmu_rated_kv_manual`
- `rmu_rated_kv_manual_override`

This prevents old session residue from keeping RMU at a previous value after MV changes.

## Persistence Behavior

Formal SLD project settings are saved through `build_persisted_sld_project_settings()`.

Before saving, `equipment_ratings.rmu.rated_kv` is overwritten by the same MV/RMU contract. If the form or a stale preset carries a different RMU voltage, it is not persisted as the visible RMU voltage.

The authoritative SLD builder also calls `_sync_rmu_rated_voltage_to_mv()` and overwrites any mismatched RMU voltage before topology is built.

## Future Equipment-Class Split

If the project later needs to distinguish nominal system voltage from equipment-class voltage, it must use a separate field, for example:

```text
mv_nominal_voltage_kv
rmu_equipment_class_voltage_kv
```

That equipment-class field must be hidden or placed behind an advanced engineering mode. It must not replace or silently modify the current visible `RMU Rated Voltage (kV)` value.

## Phase 1 Acceptance

- MV and RMU visible values share one contract.
- Old session RMU values do not survive MV changes.
- Renderer and compatibility wrappers require explicit RMU rated voltage and do not infer 33 -> 36 or 22 -> 24.
- Current Phase 1 tests cover contract behavior, renderer behavior, and UI/session sync behavior.
