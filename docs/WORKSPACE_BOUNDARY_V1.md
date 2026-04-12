# Workspace Boundary V1

This document freezes the current operator boundary for login and run management.

## Canonical Workspace Model

- `Project`: one physical opportunity, site, or customer job.
- `Case`: one technical option set under that project.
- `Run`: one persisted calculation snapshot for that case.

Formal chain:

`Login -> Workbench -> Select/Create Project -> Select/Create Case -> Run DC -> Continue to AC/SLD/Report`

## UI Boundary Rules

- The primary entry page after login is `Workbench`.
- `Workbench` is the only page that should be treated as the daily operating hub.
- `Project Directory`, `Case Directory`, and `Run Registry` are secondary detail pages, not the primary workflow.
- AC sizing, SLD, and report export should consume the active workspace context instead of asking the user to rebuild context manually.

## Session Context

The active workspace context is:

- `active_project_id / code / name`
- `active_case_id / code / name`
- `active_run_id`

Any page that restores a run must update that same context.

## Restore And Persist Rules

- `restore_run_bundle_to_session()` is the runtime authority for restoring a persisted run back into session state.
- After DC persistence succeeds, the page should reload the run bundle and restore through that same helper.
- Restoring a run must update:
  - active project
  - active case
  - active run
  - DC summary
  - stage13 output

## Navigation Rules

- Sidebar navigation should present `Workbench` first.
- Secondary list pages must be labeled as directories or registries to reduce overlap with the main workflow.
- Login success should redirect to `Workbench`.

## Out Of Scope

This V1 boundary does not redesign RBAC, database schema, or layout styling.
