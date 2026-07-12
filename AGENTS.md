# Agent Instructions (Codex / Claude / any coding agent)

## Start here — do not scan the whole repository

1. Read `docs/CURRENT_STATUS_2026-07-12.md` first. It contains the current
   milestone, deferred items, the module map (domain → packages → size →
   change frequency) and the maintenance decomposition plan.
2. State which domains your task touches, then read only those packages.
3. Business sizing logic is FROZEN — no edits to DC/AC formulas, scenario
   semantics, `K_MAX_FIXED`, SOH/RTE handling (`docs/SIZING_LOGIC_CANON_V1.md`).
   `git diff` before commit must show no changes to frozen modules.
4. If your change moves responsibility between domains, update the module map
   in the status doc in the same commit.

## Environment

- Windows, Python 3.10, Streamlit on port 8511 (`.\scripts\start_local_web.ps1`).
- DB: SQLite at `var/calb_sizing.db`, Alembic migrations (`python -m alembic upgrade head`).

## Before every commit

```powershell
python -m compileall -q app.py calb_sizing_tool calb_diagrams
python -m pytest tests -q     # all 215 must pass
```

- Active branch: `ops/ubuntu-docker-coexist-20260311` (main branch: `master`).
- `lark-im-resources/` is unrelated local material — never stage it.
