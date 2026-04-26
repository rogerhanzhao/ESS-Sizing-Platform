# Project Logic Review During SLD Stage V1

## Scope

This document records the project-level logic review performed during the SLD
repair workstream. It is intentionally limited to data flow and SLD integration
boundaries.

No changes are made here to:

```text
DC sizing math
AC sizing math
Site Layout
login/RBAC
report export behavior
```

## Intended Runtime Chain

The project should operate with one physical project, one technical case, and
one calculation run snapshot at a time:

```text
Project
  -> Case
     -> Run
        -> DC sizing result
        -> AC sizing result
        -> persisted AC runtime snapshot
        -> SLD canonical input
        -> SLD topology
        -> renderer mode
        -> registered SVG/PNG/JSON artifacts
```

The important rule is that SLD must be downstream of DC sizing and AC sizing.
SLD may visualize the result, but it must not calculate or override sizing.

## DC Sizing Role

DC sizing owns the energy-side result:

```text
DC Block quantity
DC Block energy
container/cabinet scenario result
usable-energy basis
guarantee/degradation result
```

SLD only consumes these outputs through the run bundle and canonical snapshot.
SLD must not recalculate degradation, reserve, augmentation, or usable-energy
logic.

## AC Sizing Role

AC sizing owns the AC block recommendation and the PCS/DC allocation basis:

```text
AC block count
PCS count per AC block
PCS kW rating
transformer MVA basis
LV voltage
MV voltage
DC blocks per feeder
DC allocation plan
```

The current AC page persists `ac_runtime_snapshot_v1` after AC sizing. SLD
should prefer that persisted snapshot over session cache.

## SLD Role

SLD owns only the engineering drawing chain:

```text
persisted AC snapshot + run bundle + case SLD settings
  -> SldCanonicalInput
  -> SldTopology
  -> optional engineering_v2 graph/layout
  -> SVG/PNG artifacts
```

Renderer responsibilities are limited to drawing resolved data. Renderers must
not guess:

```text
PCS quantity
DC block quantity
DC allocation
MV/RMU voltage
transformer rating
LV busbar rating
```

## Current Reasonable Parts

1. SLD has a persisted-first AC data source.
2. MV voltage and RMU displayed voltage are contracted to the same visible value.
3. AC-to-SLD alias handling is centralized in the adapter.
4. SLD strict mode rejects missing critical topology fields.
5. `engineering_v2` separates graph, layout, validation, and renderer concerns.
6. `engineering_v2` now follows professional one-line drawing expression:
   RMU feeders, transformer, LV busbar, PCS feeders, DC fuse/interface, BESS.

## Current Unreasonable Or Unclosed Parts

1. The UI default renderer is the stable server baseline, but the schema default
   for `SldRenderOptions.renderer_mode` is still `topology_v1`. This is a
   controlled compatibility state, but it is not a clean final default policy.
2. `engineering_v2` is a manual preview mode. It is not yet the production
   default.
3. Professional note fields such as MV cable, LV cable, DC cable, and BESS cell
   spec are engineering settings. They are not produced by DC or AC sizing and
   must come from case/project input.
4. Site Layout and Report Export have not been moved into the same
   persisted-first/runtime-source discipline in this SLD stage.
5. AC view still writes both session state and persisted snapshots. SLD reads
   persisted first, but the overall app still has mixed runtime state.
6. Automatic professional SLD generation after AC sizing is not enabled yet.
   The current safe path is explicit SLD generation from the SLD page.
7. The current SLD regression fixture is a renderer/data-contract fixture, not
   a physically complete project case. It can show a small `dc_block_energy_mwh`
   from the minimal test Excel while the AC allocation is simplified to four
   feeders. That is acceptable for renderer regression only, but it must not be
   used as evidence of a real project sizing result.

## SLD Auto-Generation Readiness

The correct future trigger is after AC sizing successfully persists
`ac_runtime_snapshot_v1`, not inside the renderer.

Required conditions before enabling automatic SLD generation:

```text
active run_id exists
persisted AC runtime snapshot exists and matches run_id
AC allocation total is consistent with the DC run snapshot
case SLD engineering settings exist
strict SLD canonical input validates
selected renderer mode is explicitly approved
artifact registration succeeds
```

If those conditions are not met, the app may offer a draft preview, but it must
not register or display it as a formal engineering SLD.

## Current Stage Decision

Keep production/default behavior conservative:

```text
legacy_server remains the stable UI default
topology_v1 remains a comparison/regression path
engineering_v2 remains professional preview until visual and data-source review close
```

The next safe implementation step is not more renderer styling. It is to add a
small SLD generation policy service that decides whether a run is eligible for
automatic formal SLD generation.
