# Documentation Index

This folder contains the active project documentation. Temporary implementation notes, repair plans, PR writeups, and one-off verification reports have been archived under `docs/archive/root-legacy/`.

## Core Usage

- `QUICK_START.md`: basic app startup and operator workflow
- `REPORTING_AND_DIAGRAMS.md`: report export, SLD, and layout guidance
- `PCS_RATING_GUIDE.md`: PCS option selection and container sizing rules
- `optional_dependencies.md`: optional packages used by some features

## SLD Baseline And Contracts

- `SLD_CURRENT_ISSUE_ROOT_CAUSE.md`: current SLD failure root cause and V1 repair scope
- `SLD_AC_FIELD_CONTRACT_V1.md`: authoritative AC->SLD contract and compatibility alias rules
- `SLD_RENDERER_BOUNDARY_PATCH_V1.md`: renderer boundary shrink and remaining compatibility scope
- `SLD_REGRESSION_BASELINE_V1.md`: topology/render baseline strategy and update gate

## Deployment

- `UBUNTU_DOCKER_DEPLOYMENT.md`: recommended Ubuntu Docker deployment path
- `N1_DEPLOYMENT.md`: N1 deployment overview
- `N1_DEPLOYMENT_RUNBOOK.md`: N1 operations and runbook details
- `N1_DEPLOYMENT_CHANGES.md`: deployment-specific changes applied on N1
- `SETUP_FOR_REMOTE_DEV.md`: remote development setup
- `remote_dev.md`: remote port forwarding notes

## Data And Backend Planning

- `REFACTOR_PHASE1_PLAN.md`: current Phase 1 refactor scope and deliverables
- `BASELINE_FREEZE_PLAN_V1.md`: golden-case baseline freeze plan and regression contract
- `SIZING_LOGIC_CANON_V1.md`: frozen DC/AC sizing law and change-control rules
- `DATA_MODEL_MAP_V1.md`: canonical field and entity mapping for DC sizing
- `DB_SCHEMA_OVERVIEW_V1.md`: SQLAlchemy and Alembic schema overview
- `COMPATIBILITY_NOTES_V1.md`: compatibility constraints for the Phase 1 refactor
- `database_design_and_er.md`: database design and ER notes
- `current_state_db_migration_prep.md`: current-state system and migration prep
- `master_data_maintenance_api_prep.md`: master data maintenance API preparation
- `dc_master_import_runbook.md`: DC master data import workflow
- `planning_handoff_2026-04-10.md`: planning handoff snapshot
- `ARCHITECTURE_CURRENT_STATE.md`: current architecture snapshot
- `PHASE_FINAL_ACCEPTANCE_CHECKLIST.md`: Phase F acceptance checklist
- `NEXT_PHASE_BACKLOG.md`: next-phase backlog and priorities

## Release And Audit Records

- `releases/v2025.12.28-ops-release1.md`: tagged release note
- `releases/v2025.12.30-v2.1.md`: v2.1 release notes
- `audits/system_audit_2026-01-05.md`: system audit snapshot
- `regression/master_vs_refactor_calc_diff.md`: regression analysis notes

## Repository Cleanup

- `ROOT_DOC_AUDIT.md`: root markdown retention, archival, and cleanup decisions
