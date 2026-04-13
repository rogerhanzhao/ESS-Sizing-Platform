# SLD Renderer Boundary Patch V1

## Objective

The renderer must render a finished topology. It must not decide the engineering structure of that topology.

## Boundary After Phase 3

Formal runtime boundary:

`SldCanonicalInput -> SldTopology -> compatibility spec projection -> renderer`

The renderer now owns only:

- layout profile selection
- symbol placement
- SVG geometry generation
- summary box drawing
- SVG / PNG export packaging

The renderer must not own:

- feeder count decision
- feeder allocation decision
- PCS count decision
- DC block count decision
- transformer sizing decision

## Concrete Patch

### Moved out of renderer

Legacy topology conversion is no longer implemented inside `calb_diagrams/sld_pro_renderer.py`.

It now delegates to:

- `calb_diagrams/specs.py::build_topology_from_legacy_sld_group_spec`

That means renderer compatibility code may still accept a legacy `SldGroupSpec`, but the engineering interpretation lives outside the renderer file.

### Renderer behavior now

`render_sld_pro_svg()` accepts:

- `SldTopology` as the formal input
- `SldGroupSpec` only as a compatibility wrapper input

If a legacy spec is missing required engineering data, the compatibility adapter fails. The renderer does not invent the missing values.

## What This Fix Prevents

This patch prevents the renderer layer from silently doing any of the following:

- reconstructing feeder allocation from totals
- inferring PCS count
- inventing RMU class from MV voltage
- deciding transformer parameters

## What Is Still Deferred

Not done in this phase:

- complete removal of `SldGroupSpec`
- removal of all historical compatibility entry points
- deeper renderer file decomposition

Those are follow-up refactor items, not blockers for the Phase 3 stabilization target.
