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
streamlit run app.py
```

The required Excel dictionaries should remain under `data/`.

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
- `docs/DATA_MODEL_MAP_V1.md`: canonical field and entity mapping
- `docs/DB_SCHEMA_OVERVIEW_V1.md`: database schema overview
- `docs/COMPATIBILITY_NOTES_V1.md`: compatibility rules for the refactor
- `docs/REPORTING_AND_DIAGRAMS.md`: report, SLD, and layout usage
- `docs/PCS_RATING_GUIDE.md`: PCS selection guidance
- `docs/UBUNTU_DOCKER_DEPLOYMENT.md`: Ubuntu Docker deployment
- `docs/ROOT_DOC_AUDIT.md`: root markdown cleanup and archive map

Legacy implementation notes, repair proposals, test execution writeups, and PR or push artifacts were removed from the repository root and archived under `docs/archive/root-legacy/`.
