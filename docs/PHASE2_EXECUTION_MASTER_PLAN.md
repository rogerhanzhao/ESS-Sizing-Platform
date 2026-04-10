# Phase 2 Execution Master Plan

Date: 2026-04-10
Owner: Refactor Lead

## Current Status Summary
- DB infrastructure is present (SQLAlchemy 2.0 + Alembic + base/session/models/migrations). Evidence: requirements and migrations. [requirements.txt](D:/CALB_SizingTool/requirements.txt), [alembic.ini](D:/CALB_SizingTool/alembic.ini), [migrations/env.py](D:/CALB_SizingTool/migrations/env.py), [20260410_0001_initial_schema.py](D:/CALB_SizingTool/migrations/versions/20260410_0001_initial_schema.py), [base.py](D:/CALB_SizingTool/calb_sizing_tool/infra/db/base.py), [session.py](D:/CALB_SizingTool/calb_sizing_tool/infra/db/session.py), [models/](D:/CALB_SizingTool/calb_sizing_tool/infra/db/models)
- DC Stage1/2/3 services exist and are separated from UI. Evidence: [stage1_service.py](D:/CALB_SizingTool/calb_sizing_tool/services/stage1_service.py), [stage2_service.py](D:/CALB_SizingTool/calb_sizing_tool/services/stage2_service.py), [stage3_service.py](D:/CALB_SizingTool/calb_sizing_tool/services/stage3_service.py), [dc_pipeline_service.py](D:/CALB_SizingTool/calb_sizing_tool/services/dc_pipeline_service.py)
- Runtime persistence and restore services exist for DC runs. Evidence: [run_persistence_service.py](D:/CALB_SizingTool/calb_sizing_tool/services/run_persistence_service.py), [run_restore_service.py](D:/CALB_SizingTool/calb_sizing_tool/services/run_restore_service.py)
- Importer + validators exist for Excel dictionary ingestion. Evidence: [excel_dictionary_importer.py](D:/CALB_SizingTool/calb_sizing_tool/importers/excel_dictionary_importer.py), [import_validators.py](D:/CALB_SizingTool/calb_sizing_tool/importers/import_validators.py)
- Project/Case/Run UI pages and history view exist. Evidence: [projects_view.py](D:/CALB_SizingTool/calb_sizing_tool/ui/projects_view.py), [cases_view.py](D:/CALB_SizingTool/calb_sizing_tool/ui/cases_view.py), [run_history_view.py](D:/CALB_SizingTool/calb_sizing_tool/ui/run_history_view.py), [app.py](D:/CALB_SizingTool/app.py)
- Regression + persistence tests exist. Evidence: [tests/integration](D:/CALB_SizingTool/tests/integration), [tests/unit](D:/CALB_SizingTool/tests/unit)

## Unfinished Main-Chain Switch Points
- AC / SLD / Layout pages still read from `session_state` and legacy `stage13_output` rather than DB snapshots. Evidence: [ac_view.py](D:/CALB_SizingTool/calb_sizing_tool/ui/ac_view.py), [single_line_diagram_view.py](D:/CALB_SizingTool/calb_sizing_tool/ui/single_line_diagram_view.py), [site_layout_view.py](D:/CALB_SizingTool/calb_sizing_tool/ui/site_layout_view.py), [report_export_view.py](D:/CALB_SizingTool/calb_sizing_tool/ui/report_export_view.py)
- Legacy adapters still convert new snapshots into `stage13_output`. Evidence: [session_state_adapter.py](D:/CALB_SizingTool/calb_sizing_tool/adapters/session_state_adapter.py), [stage4_interface.py](D:/CALB_SizingTool/calb_sizing_tool/ui/stage4_interface.py)
- Parameter/master data repositories are only wired to importer flows, not UI or runtime flows. Evidence: [master_data_repository.py](D:/CALB_SizingTool/calb_sizing_tool/repositories/master_data_repository.py), [parameter_repository.py](D:/CALB_SizingTool/calb_sizing_tool/repositories/parameter_repository.py), [excel_dictionary_importer.py](D:/CALB_SizingTool/calb_sizing_tool/importers/excel_dictionary_importer.py)
- Run history is DC-only; AC/SLD/Layout do not yet write artifacts to DB or attach to run history.
- No auth/RBAC; no plugin system for diagrams/layout.

## Phase A–F Execution Order (Strict)

### Phase A: Runtime Source of Truth Switch (DC only)
- Input: existing DC services, run persistence services, DB schema.
- Output: DC run always writes to DB; DC page restores by run_id; session_state only cache.
- Risks: hidden session_state fallbacks; drift between DB snapshot and UI summary.
- Stop condition: DC run persistence and restore verified; regression green.

### Phase B: Project / Case / Run Record Center (DC history)
- Input: Phase A run persistence, project/case/run tables.
- Output: Projects/Cases/Run History pages; DC sizing bound to active project/case; run history restore.
- Risks: UI still carries stale session selections; run filters inconsistent.
- Stop condition: project/case/run flows usable; run history restore verified.

### Phase C: Importer Hardening + Parameter Governance
- Input: Excel importer + validators; parameter/master data repositories.
- Output: validated importer CLI, repeatable dry-run/apply, audit logs; importer tests hardened.
- Risks: schema drift between Excel and DB; missing validation coverage.
- Stop condition: importer passes validation and row-count parity checks.

### Phase D: Snapshot Read Path for AC / SLD / Layout
- Input: run snapshot bundle + artifact registry tables.
- Output: AC/SLD/Layout read from run snapshots; remove direct `stage13_output` dependency.
- Risks: legacy UI relies on session-only values; report export may break.
- Stop condition: AC/SLD/Layout can run from run_id without session seed.

### Phase E: Auth + RBAC Foundation (No plugin work)
- Input: target auth model and role matrices.
- Output: minimal auth scaffolding, role checks per page or API.
- Risks: cross-page access holes; breaking non-auth environments.
- Stop condition: role-based access behavior is deterministic and documented.

### Phase F: Diagram/Layout Plugin System (Including AI Layout contract)
- Input: artifact registry, run snapshots, auth.
- Output: plugin contracts, validation and review workflow, artifact storage.
- Risks: plugin API instability; governance unclear.
- Stop condition: plugin contract validated by at least one reference implementation.

## Acceptance Gates Per Phase
- Phase A: DC run writes DB; run_id restores; regression green.
- Phase B: Project/Case/Run history works; run restore from history verified; regression green.
- Phase C: Importer dry-run/apply consistent; validation coverage; migration roundtrip passes.
- Phase D: AC/SLD/Layout consume DB snapshots; report export uses run_id; no session-only dependency.
- Phase E: Auth/RBAC enforced; project membership rules applied.
- Phase F: Plugin contracts documented and used; artifact registry tied to run_id.
