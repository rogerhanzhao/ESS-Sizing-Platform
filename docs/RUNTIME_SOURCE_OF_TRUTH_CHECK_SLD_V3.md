# SLD Runtime Source Of Truth Check V3

Scope: Phase 2 SLD page source-of-truth fix. No Layout, renderer template, login/RBAC, or DC sizing math changes are included.

## Runtime Priority

The SLD page resolves AC runtime data through `resolve_preferred_ac_snapshot()` in this order:

1. persisted run output snapshot: `ac_runtime_snapshot_v1`
2. compatibility adapter from project/shared state
3. session cache

Only priority 1 is considered authoritative persisted mode for formal SLD output.

## Page Mode Contract

The SLD page now classifies the resolved source as one of:

| Source | Page Mode | Formal Output Allowed |
| --- | --- | --- |
| `persisted_run_snapshot` | `authoritative_persisted` | yes |
| `compatibility_adapter` | `draft_session` | no, forced draft |
| `session_cache` | `draft_session` | no, forced draft |
| `none` | `unavailable` | no generation |

If no persisted AC runtime snapshot exists for the selected run, the page displays draft/session mode and forces SLD generation into draft mode.

## Why This Matters

Before this phase, a compatibility or session AC result could still pass through the formal pipeline path and appear as a formal/strict output if the user did not explicitly enable override mode.

After this phase:

- persisted run AC snapshot remains first priority
- compatibility/session sources remain available for draft continuity
- session-derived SLD output cannot be silently labeled as formal
- generated preview metadata records:
  - `ac_runtime_source`
  - `runtime_source_mode`
  - `forced_draft_by_source`

## User-Facing Behavior

When the AC source is persisted:

```text
SLD runtime data source: authoritative persisted mode (persisted run AC snapshot).
```

When the AC source is compatibility/session:

```text
SLD runtime data source: draft/session mode (...)
```

If the user has not enabled Engineering Override Mode but the AC source is not persisted, the page warns that formal/strict generation is disabled and SLD generation will be forced to draft/session mode.

## Implementation Boundary

The fix is intentionally located at the SLD page runtime boundary:

- `_resolve_sld_runtime_source_status()` classifies the resolved AC source.
- `_build_sld_render_options()` forces `override_mode=True` when source mode requires draft.
- `run_sld_pipeline_from_run_bundle()` remains the only execution path from the page.

No renderer allocation logic, drawing template, or DC sizing calculation was changed.

## Tests

Phase 2 coverage is in:

- `tests/integration/test_sld_prefers_persisted_data_over_session.py`
- `tests/integration/test_page_runtime_data_source_priority.py`

The tests confirm:

- persisted run AC snapshots win over session/project-state values
- compatibility adapter wins over session cache when no persisted snapshot exists
- compatibility/session sources are marked `draft_session`
- compatibility/session sources force draft render options
- persisted sources do not force draft render options
