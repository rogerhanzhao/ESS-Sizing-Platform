# Workbench UI Refactor Handoff — 2026-07-12

## Purpose and scope

This handoff records the redesign of the **Workbench** project-creation flow.
It touches only the Web UI domain, principally
`calb_sizing_tool/ui/workbench_view.py`.  It must not change the frozen
sizing core, database schema, master-data migration content, or AC/DC sizing
formulas.

## User-observed problem

The initial Workbench state has no projects.  The page currently shows:

1. a wide `Workspace Setup` area with a `No projects yet` message;
2. a separate `Case` panel saying `Select a project first`;
3. a separate wide `Latest Run` panel saying `Select a case to see the latest run`;
4. the actual `New Project` form below only the left-most panel.

This fragments one physical workflow into three disconnected status boxes and
leaves a large empty area beside the actual action.  It was highlighted in the
user screenshot dated 2026-07-12.

## Target interaction model

The page should follow the real sequence **Project → Case → Run**:

- Empty workspace: show a compact three-step progress indicator, one focused
  `Create your first project` card, and the project form immediately inside it.
  Do not show an empty Case, Latest Run, or Run Registry panel.
- Project exists but no case: show the selected project and a focused `Create
  your first case` card.  State that the sizing run becomes available after
  the case is created; do not show empty run dashboards.
- Case exists: retain the existing normal operational layout (project/case
  selection, latest run, and run registry).

The redesign is a presentation-only change: project and case creation must
keep using the existing repositories, access checks, active-workspace updates,
and `st.rerun()` behaviour.

## Work log

### 2026-07-12 — baseline captured

- Read `AGENTS.md` and `docs/CURRENT_STATUS_2026-07-12.md`.
- Confirmed branch: `ops/ubuntu-docker-coexist-20260311`.
- Confirmed unrelated local material: `?? lark-im-resources/`; do not stage it.
- Located the issue in `calb_sizing_tool/ui/workbench_view.py`, especially
  `_render_project_picker`, `_render_case_picker`, `_render_latest_run`,
  `_render_run_registry`, and `show`.

### 2026-07-12 — implementation and verification complete

- Added a compact, responsive three-step visual guide: Project → Case → Run.
  It shows the active step, completed steps, and future locked steps without
  using full-width empty-state alerts.
- Extracted the existing project/case selector and creation routines into
  reusable helpers.  Their repository calls, role assignment/access check,
  workspace-state updates, and rerun behaviour are unchanged.
- Added explicit onboarding renderers:
  - no project: focused first-project form plus only a concise next-step note;
  - project but no case: selected-project context plus focused first-case form;
  - case but no run: selected project/case context plus a clear DC Sizing
    action.
- `show()` now returns after the relevant onboarding renderer.  Therefore
  `Latest Run` and `Run Registry` do not appear until a real run exists.
- Added `tests/test_workbench_onboarding.py`.
  - A direct renderer test asserts that first-project onboarding exposes only
    the project form and no empty data panels.
  - An end-to-end isolated `show()` test patches the project loader to an
    empty workspace and asserts that deferred Case/Run panels are absent.
  - First test attempt exposed the expected `AppTest.from_function` isolation
    rule: module imports must be inside the rendered function.  Imports were
  moved there; the focused test passes `2 passed`.
- Full verification completed successfully:
  - `python -m compileall -q app.py calb_sizing_tool calb_diagrams`
  - `python -m pytest tests -q` → **218 passed** in 80.61 s.
  - `pwsh ./scripts/start_local_web.ps1 -Port 8511` → Alembic migrations
    completed; Streamlit PID 19796; `http://127.0.0.1:8511` returned HTTP 200.
  - Browser visual check confirmed the normal populated Workbench renders
    correctly with project/case/run data.  The intentionally empty-workspace
    layout is covered by the isolated AppTest; no production data was deleted
    merely to recreate that state.

### 2026-07-13 — release rule requested by user

- Release path is strictly **local verification → GitHub commit/push → server
  `git pull` → service restart/HTTP check**.
- Do not use a local Git bundle, `scp`, or any direct local-to-server source
  transfer for application-version deployment.  This rule does not change the
  existing persistent server database or its imported master data.
- GitHub remote is `https://github.com/rogerhanzhao/ESS-Sizing-Platform.git`.
  The current branch was pushed successfully as
  `ops/ubuntu-docker-coexist-20260311` at `7d3ec1f98e949422b146673ccd61bc0541e30f85`.
  The Workbench implementation itself is in the already-pushed commit
  `81de881` (`Workbench onboarding: staged Project -> Case -> Run guidance`).
- Server deployment is currently pending network recovery.  The configured
  target resolves to `guoxia@172.16.1.141:22`, but on 2026-07-13 the host did
  not respond to ICMP or TCP/22 from source address `172.20.11.205`; an HTTP
  probe to port 18511 also timed out.  No direct-transfer fallback was used.
- Later on 2026-07-13, SSH connectivity recovered.  The server application
  checkout was reachable and confirmed at commit
  `ebd03c04f8e0427443f8ca0af5f48919facb00eb`.  The direct GitHub path remains
  blocked on the server: a prior `git pull --ff-only` did not return within
  64 seconds, and a non-interactive, server-side
  `timeout 25s git ls-remote --heads origin ops/ubuntu-docker-coexist-20260311`
  ended without output.  This is an outbound GitHub reachability/egress issue
  on the server, not an SSH or repository working-tree conflict.
- A final release-gate rerun after the latest branch updates completed:
  `python -m compileall -q app.py calb_sizing_tool calb_diagrams` clean and
  `python -m pytest tests -q` → **222 passed** in 63.91 s.  The higher count
  supersedes the earlier 218-test baseline because subsequent already-merged
  regression coverage is present on this branch.

### Server recovery command

Once `ssh calb-server` is reachable, run this command from the server only:

```bash
cd /opt/calb-sizingtool/app \
  && sudo git -c safe.directory=/opt/calb-sizingtool/app pull --ff-only origin ops/ubuntu-docker-coexist-20260311 \
  && sudo bash deploy/docker/calb-serverctl.sh restart
```

Then verify `http://127.0.0.1:18511/` from the server.  The expected release
commit is `7d3ec1f98e949422b146673ccd61bc0541e30f85` or a later documented
commit on the same branch.  Do not reset, reinitialize, or replace the
persistent database.

Before retrying the pull, restore the server's HTTPS access to GitHub (DNS,
route, firewall, proxy, or TLS trust as applicable).  Do not work around that
condition by copying the repository or a Git bundle from the local machine.

## Verification plan

1. Run a focused Streamlit `AppTest` (or equivalent isolated render test) for
   the no-project state, and assert that the project form is present while
   no Case/Latest Run/Run Registry empty-state cards are emitted.
2. Run `python -m compileall -q app.py calb_sizing_tool calb_diagrams`.
3. Run `python -m pytest tests -q` (current expected suite size: 222 tests).
4. Start local Streamlit with `pwsh ./scripts/start_local_web.ps1` (or the
   equivalent documented port-8511 command) and verify HTTP 200 at
   `http://127.0.0.1:8511`.
5. Inspect the Workbench page in the local browser session.  Do not clear or
   mutate the production/server database merely to reproduce the empty state.

## Separate known issue — RESOLVED (2026-07-13)

The server `Product & Database → Cells` page could abort during rendering.  The
confirmed cause was duplicate automatic Streamlit widget IDs shared by the
edit form and the import/add form.

**Fixed in commit `819aa8d`** ("Fix Cells page abort: explicit entity+record
keys on edit-form widgets"): every edit-form widget now carries an
entity-and-record-specific explicit key, with a regression test
(`tests/test_admin_edit_form_widget_keys.py`).  On 2026-07-13 the real
`_section_cell_products` page was rendered via Streamlit `AppTest` and produced
no `DuplicateWidgetID` / abort.  The fix is deployed on the server (release
`ebd03c0`, which includes `819aa8d`).  No further action required.
