# SLD Current Issue Root Cause

## Scope

This document records the actual root cause addressed in Phase 3 of the SLD stabilization work.

Covered scope:

- one authoritative SLD input path
- AC -> SLD field contract unification
- strict-mode fallback removal
- renderer boundary reduction
- regression baseline setup

Out of scope:

- Layout redesign
- DB takeover of all pages
- DC sizing math changes
- AC sizing math rewrite
- login / RBAC

## Root Cause Summary

The SLD stack had already started migrating to a formal path, but the old compatibility path was still able to infer key engineering data. That left the runtime with two behaviors at once:

1. formal path:
   `AcSnapshot -> SldCanonicalInput -> SldTopology -> render`
2. legacy compatibility path:
   raw AC dict / SLD dict / legacy spec -> guessed topology -> render

Because both paths still existed, the system could produce a diagram even when the authoritative runtime data was incomplete. In that state, the picture could be drawable, but the engineering structure was no longer guaranteed to match the upstream AC result.

## Concrete Failure Modes Before Phase 3

The main failure modes were:

- `pcs_count` could be guessed instead of read from authoritative AC data.
- `dc_blocks_per_feeder` could be evenly distributed by fallback logic.
- transformer rating could be re-derived from `block_size_mw / 0.9`.
- legacy equipment defaults could fill RMU / CT / cable / fuse data in paths that looked formal.
- renderer compatibility code still contained topology-building logic.
- `snapshot_single_unit.py` and `ac_block_group.py` still behaved like partial builders instead of pure compatibility projections.

## What Phase 3 Changed

### 1. One formal build path

The formal path is now:

`AcSnapshot -> normalize_ac_output_for_sld() -> SldCanonicalInput -> SldTopology -> compatibility spec projection -> renderer`

Only this path is allowed to decide:

- feeder count
- PCS count
- PCS rating list
- DC block allocation
- transformer MVA

### 2. Compatibility path downgraded

Legacy helpers are still present only for compatibility, but they no longer act as engineering decision makers.

- `snapshot_single_unit.py` now projects from resolved group data.
- `ac_block_group.py` now projects from resolved topology summary.
- legacy `SldGroupSpec -> SldTopology` conversion moved out of the renderer and now requires explicit engineering fields.

### 3. Strict mode is actually strict

In `validation_mode="strict"`, missing critical engineering inputs now fail fast instead of silently falling back.

The important removed guesses are:

- default `pcs_count = 4`
- auto-even feeder allocation
- `transformer_mva = block_size_mw / 0.9`
- default engineering equipment preset for formal generation

## Remaining Limits After Phase 3

Phase 3 stabilizes the SLD engine, but it does not solve every upstream workflow gap.

Known remaining limits:

- formal SLD engineering settings still need a proper user-maintained source or page
- some compatibility wrappers still exist for legacy callers
- `SldGroupSpec` remains as a compatibility view, not the formal engineering truth

## Acceptance Result

Phase 3 is considered complete when the following are true:

- formal SLD uses one authoritative input path
- AC -> SLD contract is normalized in one adapter
- strict mode no longer guesses missing engineering structure
- renderer no longer decides feeder / PCS / DC topology
- regression tests lock topology and render output
