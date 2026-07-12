# ESS Sizing Tool

Streamlit application for utility-scale ESS sizing, AC block configuration, reporting, and diagram generation.

## Project Layout

- `app.py`: Streamlit entry point
- `calb_sizing_tool/`: core sizing, reporting, runtime, and UI modules
- `calb_diagrams/`: SLD and layout renderers
- `data/`: input workbooks and sizing dictionaries
- `tests/`: automated tests
- `docs/`: active documentation

## Setup

1. Create and activate a virtual environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

Optional diagram export dependencies:

```bash
pip install svgwrite cairosvg
```

## Run

```bash
pwsh ./scripts/start_local_web.ps1
```

Local development is fixed to `http://127.0.0.1:8511`.
The startup script refuses to auto-switch ports. If `8511` is occupied, it exits with a clear error instead of silently moving to `8502+`.

The required Excel dictionaries should remain under `data/`.

## Initialize Database

Default SQLite DB path: `var/calb_sizing.sqlite`. Override with `CALB_DATABASE_URL` or `CALB_DB_URL`.

```powershell
$env:CALB_DATABASE_URL = "sqlite:///D:/CALB_SizingTool/var/calb_sizing.sqlite"
alembic upgrade head
```

## Import Excel Dictionary

```powershell
python scripts/import_excel_dictionary.py --mode dry_run
python scripts/import_excel_dictionary.py --mode apply_import
```

Use `--workbook` to point to a custom Excel dictionary if needed.

## Login

On first run, the login page prompts to create the initial admin account. After that, sign in with the created credentials.

## DC Sizing And Run History

1. Create a Project.
2. Create a Case under the Project.
3. Run DC Sizing. The system persists a run and returns a `run_id`.
4. Use Run History to list runs and restore results by `run_id`.

## Diagrams (SLD / Layout)

SLD and the Typical AC Block Arrangement are generated from `run_id` via the plugin system. The Arrangement is a concept-only view of one AC Block; it is not a full site plan or construction drawing. Artifacts are registered in the database.

## External AI Layout Workflow

1. In Typical AC Block Arrangement, generate and download the concept prompt payload or prompt text.
2. Run the external AI tool and upload the returned image.
3. Admin reviews and approves/rejects the submission. Approved artifacts are stored alongside deterministic layouts.

## Test

```bash
pytest -q
```

Focused Phase 1 regression and DB checks:

```bash
python scripts/generate_phase1_golden_cases.py
pytest tests/unit tests/integration -q
```

## Database And Migration

Set `CALB_DATABASE_URL` before running Alembic. Example:

```powershell
$env:CALB_DATABASE_URL = "sqlite:///D:/CALB_SizingTool/var/calb_sizing.sqlite"
alembic upgrade head
```

See `docs/DB_SCHEMA_OVERVIEW_V1.md` for table groups and migration notes.

## Documentation

Use the active docs under `docs/`:

- `docs/README.md`: documentation index
- `docs/QUICK_START.md`: operator quick start
- `docs/REFACTOR_PHASE1_PLAN.md`: current Phase 1 refactor scope
- `docs/BASELINE_FREEZE_PLAN_V1.md`: DC baseline freeze plan
- `docs/SIZING_LOGIC_CANON_V1.md`: frozen DC/AC sizing law and change-control rules
- `docs/DATA_MODEL_MAP_V1.md`: canonical field and entity mapping
- `docs/DB_SCHEMA_OVERVIEW_V1.md`: database schema overview
- `docs/COMPATIBILITY_NOTES_V1.md`: compatibility rules for the refactor
- `docs/REPORTING_AND_DIAGRAMS.md`: report, SLD, and layout usage
- `docs/PCS_RATING_GUIDE.md`: PCS selection guidance
- `docs/UBUNTU_DOCKER_DEPLOYMENT.md`: Ubuntu Docker deployment
- `docs/ROOT_DOC_AUDIT.md`: root markdown cleanup and archive map
- `docs/ARCHITECTURE_CURRENT_STATE.md`: current system architecture snapshot
- `docs/PHASE_FINAL_ACCEPTANCE_CHECKLIST.md`: Phase F acceptance checklist
- `docs/NEXT_PHASE_BACKLOG.md`: next-phase backlog and priorities

Legacy implementation notes, repair proposals, test execution writeups, and PR or push artifacts were removed from the repository root and archived under `docs/archive/root-legacy/`.
