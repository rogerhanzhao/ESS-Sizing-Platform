# SLD Engineering V2 Plugin Mode V1

## Scope

This step wires `engineering_v2` into the existing SLD plugin mode selector.

It does not make `engineering_v2` the default. Production comparison still defaults to:

```text
legacy_server
```

No Layout, login, RBAC, or DC sizing mathematics are changed.

## Runtime Modes

Available modes:

```text
legacy_server
topology_v1
engineering_v2
```

Defaults remain:

```text
SldRenderOptions default: topology_v1
SLD page default: legacy_server
```

## Engineering V2 Plugin Flow

When `renderer_mode == "engineering_v2"`:

```text
SldTopology
-> build_sld_engineering_v2_graph(...)
-> build_sld_engineering_v2_layout_plan(...)
-> render_sld_engineering_v2_svg(...)
-> existing SLD artifact persistence
```

The plugin still stores the existing artifact kinds:

```text
sld_render_spec_json
sld_topology_json
sld_svg
sld_png
```

This avoids changing artifact registry contracts in this step.

## Metadata Added For Engineering V2

Engineering V2 artifacts include:

```text
renderer_mode = engineering_v2
renderer_lineage = port_bay_engineering_v2_preview
engineering_v2_graph_hash
engineering_v2_layout_hash
engineering_v2_node_count
engineering_v2_edge_count
engineering_v2_connector_count
```

These fields make V2 previews traceable without changing the sizing logic.

## UI Behavior

The SLD page now lists `engineering_v2` in `SLD Renderer Mode`.

The page still defaults to `legacy_server`. Selecting `engineering_v2` shows a warning that the mode is a preview and requires human visual review before production use.

## Current Boundary

`engineering_v2` is now runnable through the plugin, but it is not the production default.

Do not remove `legacy_server` until:

1. Visual acceptance passes.
2. Report export expectations are checked.
3. Artifact review confirms V2 output is acceptable for customer-facing use.
4. Multi-feeder and multi-DC-block cases have regression coverage.
