# Current Status 2026-04-13

Branch: `ops/ubuntu-docker-coexist-20260311`

## Scope Completed

The requested phased repair sequence is complete:

1. Phase 0: fact audit only
2. Phase 1: MV / RMU voltage contract cleanup
3. Phase 2: SLD runtime source priority changed to persisted-first
4. Phase 3: SLD authoritative builder and renderer boundary stabilization
5. Follow-up: formal SLD engineering settings entry and persistence added to the SLD page

## Current Functional State

### MV / RMU voltage

- `POI / MV Voltage (kV)` is the single authoritative MV-side voltage.
- `RMU rated voltage (kV)` mirrors the authoritative MV value.
- renderer no longer infers RMU voltage by itself.

Reference:

- `MV_RMU_VOLTAGE_CONTRACT_V1.md`

### Runtime source of truth

- DC run snapshots are DB-backed.
- AC runtime snapshot is now persisted to DB.
- SLD resolves AC runtime with priority:
  1. persisted AC snapshot
  2. compatibility adapter
  3. session cache

Reference:

- `RUNTIME_SOURCE_OF_TRUTH_CHECK_V2.md`

### SLD engine

- formal SLD now follows one authoritative runtime path
- AC -> SLD alias normalization is centralized
- strict mode no longer hides missing engineering inputs with silent defaults
- renderer no longer owns feeder / PCS / DC engineering decisions

References:

- `SLD_CURRENT_ISSUE_ROOT_CAUSE.md`
- `SLD_AC_FIELD_CONTRACT_V1.md`
- `SLD_RENDERER_BOUNDARY_PATCH_V1.md`
- `SLD_REGRESSION_BASELINE_V1.md`

### Formal engineering settings

- SLD page now has a `Formal Engineering Settings` section
- settings are saved to the active case at:
  `SizingCase.input_json["project_settings"]`
- strict mode can now use persisted engineering settings instead of requiring draft override input

## Important Retained Tests

Regression tests were intentionally kept. They are part of the repair, not disposable test clutter.

Key retained tests:

- `tests/unit/test_mv_rmu_voltage_contract.py`
- `tests/integration/test_mv_rmu_sync_behavior.py`
- `tests/integration/test_page_runtime_data_source_priority.py`
- `tests/integration/test_sld_prefers_persisted_data_over_session.py`
- `tests/unit/test_sld_ac_field_contract.py`
- `tests/unit/test_sld_authoritative_builder.py`
- `tests/unit/test_sld_builder_unification.py`
- `tests/integration/test_sld_topology_regression.py`
- `tests/integration/test_sld_render_regression.py`
- `tests/integration/test_sld_engineering_settings_persistence.py`

## Cleanup Performed

- removed local interpreter and pytest caches
- removed local SQLite runtime database under `var/`
- ignored local SQLite runtime DBs in `.gitignore`
- removed temporary audit-only markdown files superseded by this status note and the retained contract documents

Removed temporary docs:

- `ISSUE_AUDIT_MV_RMU_DB_SLD_V2.md`
- `SLD_REAL_RUNTIME_DATAFLOW_V2.md`

## Remaining Known Limits

- formal engineering settings are currently stored at case level, not in a dedicated engineering settings table
- the formal engineering settings UI currently lives inside the SLD page
- AC page itself is still not fully DB-restored on page load
- Layout and Report Export have not been migrated to the same persisted-first pattern

## Recommended Next Work

If work continues, the next logical scope is:

1. move formal engineering settings into a dedicated maintained settings flow
2. make AC page restore persisted AC runtime directly
3. extend persisted-first runtime policy to Layout and Report Export
