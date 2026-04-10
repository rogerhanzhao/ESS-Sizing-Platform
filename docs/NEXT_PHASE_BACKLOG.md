# Next Phase Backlog

This backlog captures post-Phase F work items. Items are grouped by priority.

## High Priority

- Add admin UI for user management and project membership assignment.
- Add run history filters, pagination, and summary exports.
- Extend AC sizing to read directly from run snapshots where applicable.
- Introduce CI pipeline for migrations and regression tests.

## Medium Priority

- Artifact registry viewer with diff and version tracking.
- Parameter governance UI with publish/retire workflow.
- Report generation refactor to use run snapshots only.
- Add DB indexes for run history queries and artifact lookups.

## Low Priority

- Packaging for desktop/offline usage.
- Internationalization infrastructure (if needed).
- Additional diagram themes and export formats.

## Risks To Track

- Snapshot drift between DC and AC if AC stays partially session-driven.
- Large SQLite files in local dev without archival rotation.
