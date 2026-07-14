# Workspace Boundary V1

This document freezes the current operator boundary for login and run management.

## Canonical Workspace Model

- `Project`: one physical opportunity, site, or customer job.
- `Case`: one technical option set under that project.
- `Run`: one persisted calculation snapshot for that case.

Formal chain:

`Login -> Workbench -> Select/Create Project -> Select/Create Case -> Run DC -> Continue to AC/SLD/Report`

## Data Isolation And Roles

- The application uses one shared database, not one physical database per user.
- `Project` is the tenant boundary. `Case`, `SizingRun`, input snapshots, output snapshots, and downstream artifacts belong to a Project directly or through its Case.
- A normal user can read a Project only when an `active` `project_member` row exists for that user. Case, Run History, Run restore, AC, SLD, layout, and report access inherit this Project check.
- A normal user who creates a Project becomes an active member of that new Project. A same-name Project creates a separate unique Project code; it must not attach the user to an existing Project.
- An administrator is identified by the `admin` role and can list and read all Projects, Cases, and Runs without a Project membership row. Administrator visibility does not automatically grant normal users access; membership assignment remains explicit.
- Inactive memberships are denied by the same access check and are excluded from normal-user project lists.

## Business Flow

1. `Project`: create the customer/site/opportunity workspace and assign the creator as an active member.
2. `Case`: create a named technical option under the active Project. The initial record holds identity and scenario metadata; the first DC sizing run writes the technical input set.
3. `Run`: execute DC sizing under the active Project and Case. Each successful Run stores an immutable input snapshot and output snapshot; the Case record is updated to the latest successful working input.
4. `Restore`: load a selected Run only after the Project membership check passes, set the active Project/Case/Run context, restore the saved DC inputs and results, and open DC Sizing. Restore never changes the historical Run snapshot.
5. `Continue`: AC sizing, SLD, layout, and report pages consume the restored active Run context and repeat the same Project access check when loading persisted data.

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
  - all persisted editable DC input fields used by the DC Sizing form
- Switching the active Project or Case clears prior DC widget state so inputs from another Case cannot be reused accidentally.
- A successful DC Run updates the active Case working input JSON; each Run keeps its own immutable input snapshot for history and audit.

## Navigation Rules

- Sidebar navigation should present `Workbench` first.
- Secondary list pages must be labeled as directories or registries to reduce overlap with the main workflow.
- Login success should redirect to `Workbench`.

## Out Of Scope

This V1 boundary does not redesign RBAC, database schema, or layout styling.
