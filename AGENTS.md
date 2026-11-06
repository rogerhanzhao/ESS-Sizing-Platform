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
5. Production operations (log inspection, issue triage, deploy) follow the
   local-only runbooks under `docs/ops-local/` (untracked by design). When the
   user asks for a "server log inspection" / "巡检", read
   `docs/ops-local/DAILY_OPS_LOOP_V1.md` first and follow it exactly.

## Environment

- Windows, Python 3.10, Streamlit on port 8511 (`.\scripts\start_local_web.ps1`).
- DB: SQLite at `var/calb_sizing.db`, Alembic migrations (`python -m alembic upgrade head`).

## Incremental maintenance (owner instruction, 2026-11-07)

- Start from the current diff and the reported issue; inspect only affected domains.
- Make bounded changes in the existing UI and workflow. Do not redesign or rescan
  the repository unless evidence shows a cross-domain defect.
- During iteration, run affected tests and immediate interface checks. Reuse
  recorded passing results for unchanged code instead of rerunning the full suite.
- Run a full regression for a release candidate or changes to shared contracts,
  persistence, dependencies, or multiple domains. Do not repeat it solely for
  documentation, whitespace, or test-timeout changes; run affected tests instead.
- Record what changed, checks run, existing evidence reused, and deployment status.

## Release validation

```powershell
python -m compileall -q app.py calb_sizing_tool calb_diagrams
python -m pytest tests -q     # current suite must pass; see reuse rule above
```

- Active branch: `ops/ubuntu-docker-coexist-20260311` (main branch: `master`).
