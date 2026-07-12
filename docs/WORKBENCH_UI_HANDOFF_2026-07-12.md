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

### 2026-07-12 — implementation in progress

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
    moved there; the focused test now passes `2 passed`.

## Verification plan

1. Run a focused Streamlit `AppTest` (or equivalent isolated render test) for
   the no-project state, and assert that the project form is present while
   no Case/Latest Run/Run Registry empty-state cards are emitted.
2. Run `python -m compileall -q app.py calb_sizing_tool calb_diagrams`.
3. Run `python -m pytest tests -q` (current expected suite size: 216 tests).
4. Start local Streamlit with `pwsh ./scripts/start_local_web.ps1` (or the
   equivalent documented port-8511 command) and verify HTTP 200 at
   `http://127.0.0.1:8511`.
5. Inspect the Workbench page in the local browser session.  Do not clear or
   mutate the production/server database merely to reproduce the empty state.

## Separate known issue — not in this UI change

The server `Product & Database → Cells` page can abort during rendering.  The
confirmed cause is duplicate automatic Streamlit widget IDs shared by the
edit form and the import/add form.  The later fix is to give every edit-form
widget an entity-and-record-specific explicit key and add a regression test.
Keep this separate from the Workbench UI commit unless explicitly resumed.
