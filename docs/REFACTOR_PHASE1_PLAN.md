# Refactor Phase 1 Plan

## Goal

Refactor the current CALB ESS Sizing Platform from Excel and Streamlit-session driven prototype code into a layered platform with:

- unified domain data
- governed parameter definitions
- repository-based persistence
- reproducible run snapshots
- UI separated from DC Stage 1 to Stage 3 core logic

## Scope For This Phase

Included:

- Freeze the current DC baseline with golden cases.
- Introduce domain enums, units, field codes, and Pydantic schemas.
- Move Stage 1 to Stage 3 calculation logic into pure Python services.
- Add SQLAlchemy 2.0 models, repositories, and Alembic migration baseline.
- Add Excel importer and validation path for DC master data.
- Keep Streamlit UI callable through compatibility adapters.

Explicitly excluded:

- AC sizing mathematical refactor
- SLD core logic changes
- Layout core logic changes
- Removal of Excel as import and regression reference source
- Frontend redesign

## Deliverables

### Phase 0. Baseline Freeze

- [BASELINE_FREEZE_PLAN_V1.md](d:/CALB_SizingTool/docs/BASELINE_FREEZE_PLAN_V1.md)
- `tests/fixtures/golden_cases/`
- `scripts/generate_phase1_golden_cases.py`
- [test_dc_pipeline_regression.py](d:/CALB_SizingTool/tests/integration/test_dc_pipeline_regression.py)

### Phase 1. Domain Model

- [DATA_MODEL_MAP_V1.md](d:/CALB_SizingTool/docs/DATA_MODEL_MAP_V1.md)
- [enums.py](d:/CALB_SizingTool/calb_sizing_tool/domain/enums.py)
- [units.py](d:/CALB_SizingTool/calb_sizing_tool/domain/units.py)
- [field_codes.py](d:/CALB_SizingTool/calb_sizing_tool/domain/field_codes.py)
- `calb_sizing_tool/schemas/*.py`

### Phase 2. Persistence Foundation

- [DB_SCHEMA_OVERVIEW_V1.md](d:/CALB_SizingTool/docs/DB_SCHEMA_OVERVIEW_V1.md)
- `calb_sizing_tool/infra/db/`
- `calb_sizing_tool/repositories/`
- `migrations/`
- `alembic.ini`

### Phase 3. DC Service Extraction

- `calb_sizing_tool/services/stage1_service.py`
- `calb_sizing_tool/services/stage2_service.py`
- `calb_sizing_tool/services/stage3_service.py`
- `calb_sizing_tool/services/dc_pipeline_service.py`
- compatibility wrappers in [dc_view.py](d:/CALB_SizingTool/calb_sizing_tool/ui/dc_view.py)

### Phase 4. Import And Snapshot Plumbing

- `calb_sizing_tool/importers/excel_dictionary_importer.py`
- `calb_sizing_tool/importers/import_validators.py`
- `calb_sizing_tool/adapters/excel_loader_adapter.py`
- `calb_sizing_tool/adapters/session_state_adapter.py`
- snapshot persistence tests

## Target Directory Layout

This phase now aligns to the following structure:

- `calb_sizing_tool/domain/`
- `calb_sizing_tool/schemas/`
- `calb_sizing_tool/services/`
- `calb_sizing_tool/repositories/`
- `calb_sizing_tool/infra/db/`
- `calb_sizing_tool/importers/`
- `calb_sizing_tool/adapters/`
- `migrations/`
- `tests/unit/`
- `tests/integration/`
- `tests/fixtures/golden_cases/`
- `tests/fixtures/sample_excels/`

## Exit Criteria

Phase 1 is considered complete when:

- UI no longer contains Stage 1 to Stage 3 core math implementations.
- DC core logic is callable independently of Streamlit.
- Schema migration can be upgraded, downgraded, and upgraded again.
- Golden-case regression is stable.
- Output contract changes are documented before any future formula change.

## Current Status

Completed on 2026-04-10:

- baseline frozen
- service layer introduced
- database and migration foundation introduced
- Excel importer and validation path introduced
- snapshot persistence path introduced

Deferred to later phases:

- DB as primary runtime source of truth
- parameter definition seeding and publish workflow
- AC / SLD / Layout migration onto shared snapshots
