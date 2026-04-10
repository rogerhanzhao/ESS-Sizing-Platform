# DB Schema Overview V1

## Stack

- ORM: SQLAlchemy 2.0
- Migration: Alembic
- Validation: Pydantic v2
- Dev database: SQLite
- Production-ready target: PostgreSQL via `psycopg`

Runtime database URL environment variable:

- `CALB_DATABASE_URL`

Compatibility alias currently accepted in code:

- `CALB_DB_URL`

## Migration Commands

PowerShell example:

```powershell
$env:CALB_DATABASE_URL = "sqlite:///D:/CALB_SizingTool/var/calb_sizing.sqlite"
alembic upgrade head
```

Roundtrip verification:

```powershell
$env:CALB_DATABASE_URL = "sqlite:///D:/CALB_SizingTool/var/calb_sizing.sqlite"
alembic downgrade base
alembic upgrade head
```

## Table Groups

### Parameter Governance

| Table | Purpose |
| --- | --- |
| `parameter_definition` | Canonical definition of governed fields, units, validation rules, and legacy mapping |
| `parameter_set` | Versionable named sets of input parameters by stage scope |

### DC Master Data

| Table | Purpose |
| --- | --- |
| `battery_cell_type` | Cell master records imported from Excel with canonical fields plus `raw_row_json` |
| `pack_type` | Pack master records linked to `battery_cell_type` |
| `rack_type` | Rack master records linked to `pack_type` |
| `dc_block_template` | Container and cabinet block templates linked to `rack_type` |
| `soh_profile` | SOH selection profiles linked to `battery_cell_type` |
| `soh_curve_point` | Year or cycle indexed SOH curve rows linked to `soh_profile` |
| `rte_profile` | RTE selection profiles linked to `battery_cell_type` |
| `rte_curve_band` | SOH-band RTE rows linked to `rte_profile` |

### Project / Case / Run Chain

| Table | Purpose |
| --- | --- |
| `project` | Top-level project container |
| `sizing_case` | Named case definition with scenario mode and input payload |
| `sizing_run` | Individual execution record with input and output summaries |

### Snapshot / Artifact / Audit

| Table | Purpose |
| --- | --- |
| `run_input_snapshot` | Immutable input payload snapshots bound to a run |
| `run_output_snapshot` | Immutable output payload snapshots bound to a run |
| `artifact_registry` | Reports, CSVs, diagrams, and other generated files bound to a run |
| `audit_log` | Entity-level change and action journal |

## Common Lifecycle Columns

Applied where relevant:

- `created_at`
- `updated_at`
- `version_tag`
- `source_ref`
- `is_active`
- `is_published`

## Key Relationships

- `pack_type.battery_cell_type_id -> battery_cell_type.battery_cell_type_id`
- `rack_type.pack_type_id -> pack_type.pack_type_id`
- `dc_block_template.rack_type_id -> rack_type.rack_type_id`
- `soh_profile.battery_cell_type_id -> battery_cell_type.battery_cell_type_id`
- `soh_curve_point.soh_profile_id -> soh_profile.soh_profile_id`
- `rte_profile.battery_cell_type_id -> battery_cell_type.battery_cell_type_id`
- `rte_curve_band.rte_profile_id -> rte_profile.rte_profile_id`
- `sizing_case.project_id -> project.project_id`
- `sizing_run.project_id -> project.project_id`
- `sizing_run.sizing_case_id -> sizing_case.sizing_case_id`
- `run_input_snapshot.sizing_run_id -> sizing_run.sizing_run_id`
- `run_output_snapshot.sizing_run_id -> sizing_run.sizing_run_id`
- `artifact_registry.sizing_run_id -> sizing_run.sizing_run_id`

## Notes On V1 Design

- SQLite parent directories are normalized and auto-created by the runtime session helper.
- PostgreSQL compatibility is preserved by using generic SQLAlchemy types and avoiding SQLite-only schema features.
- `raw_row_json` is intentionally retained on imported master-data tables to preserve Excel fidelity during the transition period.
- `Is_Default_Option` from the DC block Excel sheet is preserved in `raw_row_json` and the in-memory Excel bundle, but is not yet promoted to a dedicated relational column in schema V1.

## Verification

Implemented checks:

- [test_db_migration_roundtrip.py](d:/CALB_SizingTool/tests/integration/test_db_migration_roundtrip.py)
- [test_run_snapshot_persistence.py](d:/CALB_SizingTool/tests/integration/test_run_snapshot_persistence.py)
- [test_excel_importer.py](d:/CALB_SizingTool/tests/unit/test_excel_importer.py)
