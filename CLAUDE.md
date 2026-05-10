# CALB ESS Sizing Platform — Claude Code Instructions

## Critical: Server Port

**Local development** runs on **port 8511**, set via CLI args in `start_local_web.ps1`.
`config.toml` no longer hard-codes port or address — those were removed to allow cloud deployment
(Streamlit Community Cloud health-checks port 8501 and needs address 0.0.0.0).

### Correct local restart procedure

```powershell
# Preferred — runs Alembic migrations first, then starts on 8511:
.\scripts\start_local_web.ps1

# Manual — must pass port explicitly (config.toml no longer sets it):
streamlit run app.py --server.port 8511 --server.address 127.0.0.1
```

### Kill + restart (clean)

```powershell
Get-NetTCPConnection -LocalPort 8511 -ErrorAction SilentlyContinue |
    ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
Start-Sleep -Seconds 1
.\scripts\start_local_web.ps1
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
