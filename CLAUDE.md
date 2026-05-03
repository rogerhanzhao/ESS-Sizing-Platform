# CALB ESS Sizing Platform — Claude Code Instructions

## Critical: Server Port

This project runs on **port 8511** (configured in `.streamlit/config.toml`).

**NEVER use `--server.port=8501`.** Streamlit's built-in default is 8501, but this project
overrides it. Adding `--server.port=8501` creates a second instance on the wrong port while
the correct one keeps running on 8511 — two versions alive simultaneously.

### Correct restart procedure

```powershell
# Preferred — runs Alembic migrations first, then starts on 8511:
.\scripts\start_local_web.ps1

# Acceptable — bare invocation reads config.toml → port 8511:
streamlit run app.py
```

### Kill + restart (clean)

```powershell
Get-NetTCPConnection -LocalPort 8511 -ErrorAction SilentlyContinue |
    ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
Start-Sleep -Seconds 1
streamlit run app.py          # reads config.toml, binds to 8511
```

Verify it's up: `Get-NetTCPConnection -LocalPort 8511`

---

## Project Overview

Python / Streamlit utility-scale BESS sizing platform.

- **Stack**: Python 3.10, Streamlit, SQLite + SQLAlchemy ORM, Alembic migrations
- **Entry point**: `app.py`
- **Data file**: `data/ess_sizing_data_dictionary_v13_*.xlsx`
- **DB**: `var/calb_sizing.db` (SQLite, WAL mode)

## Database Migrations

Always run Alembic before starting the app on an existing database:

```powershell
python -m alembic upgrade head
```

`start_local_web.ps1` does this automatically. Direct `streamlit run app.py` also works on
a fresh DB (the `Base.metadata.create_all` safety net in `app.py` creates missing tables).

## Tests

```powershell
python -m pytest tests/ -x -q
```

195 tests, ~30 s. All must pass before committing.

## Git

- Active branch: `ops/ubuntu-docker-coexist-20260311`
- Main branch: `master`
- Always run the test suite before committing.
