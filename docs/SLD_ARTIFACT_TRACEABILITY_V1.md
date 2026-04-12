# SLD Artifact Traceability V1

## Scope

This document freezes the traceability contract for formal SLD outputs after the Phase 5 refactor. It applies to the SLD pipeline only. Layout is explicitly out of scope.

## Registry Binding

Every persisted SLD artifact is written through the existing `artifact_registry` table and is always bound to a `run_id` via `artifact_registry.sizing_run_id`.

The SLD pipeline writes these artifact kinds:

- `sld_svg`
- `sld_png`
- `sld_topology_json`
- `sld_render_spec_json`

Each registry row stores:

- `sizing_run_id`
- `artifact_kind`
- `file_name`
- `file_path`
- `media_type`
- `content_hash`
- `created_at`
- `version_tag`
- `metadata_json`

## Metadata Contract

`metadata_json` for every SLD artifact must include:

- `run_id`
- `scenario_id`
- `group_index`
- `validation_mode`
- `artifact_mode`
- `renderer_version`
- `input_hash`
- `topology_hash`
- `render_spec_hash`
- `actor`
- `plugin_id`
- `plugin_version`

## Mode Separation

Two output modes are supported:

- `official`
- `draft_override`

Rules:

- `official` artifacts only come from strict mode.
- `draft_override` artifacts are generated only when engineering override mode is enabled.
- Draft artifacts must never overwrite formal files. Draft file names therefore carry a `.draft` suffix.
- Draft and official artifacts may coexist under the same `run_id`, but they remain distinguishable through both file names and `metadata_json.artifact_mode`.
- A missing `run_id` blocks registry persistence.

## Hash Strategy

The SLD pipeline records these hashes:

- `input_hash`: SHA-256 of canonical `SldCanonicalInput`
- `topology_hash`: SHA-256 of normalized `SldTopology`
- `render_spec_hash`: SHA-256 of renderer-facing spec JSON
- `content_hash`: SHA-256 of each persisted artifact payload, stored in the registry row and mirrored in artifact metadata

This provides a stable chain:

`run_id -> canonical input hash -> topology hash -> render spec hash -> artifact content hash`

## UI Traceability Display

The SLD page surfaces:

- `run_id`
- `renderer_version`
- `artifact_mode`
- `input_hash`
- `topology_hash`
- per-artifact `content_hash`

This is a read-only traceability view. The page does not mutate registry records after artifact creation.
