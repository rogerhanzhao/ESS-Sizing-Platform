# MV / RMU Voltage Contract V1

## Decision

Phase 1 is corrected to **Option A**.

The system uses one authoritative MV-side voltage input:

- `POI / MV Voltage (kV)` from DC sizing

Current runtime field mapping:

- authoritative MV input -> `SldCanonicalInput.mv_voltage_kv`
- derived RMU rated voltage mirror -> `SldCanonicalInput.equipment_ratings.rmu.rated_kv`

## Rules

1. `POI / MV Voltage (kV)` is the single authoritative MV-side voltage for this workflow.
2. `RMU Rated voltage (kV)` is not a second editable business field on the SLD page.
3. When SLD data is built, `equipment_ratings.rmu.rated_kv` is forced to mirror the authoritative POI / MV voltage.
4. Stale session or draft RMU voltage values must be ignored.
5. Renderer must not infer missing RMU voltage on its own.

## Source Priority

For Phase 1 voltage handling:

- A. authoritative POI / MV voltage from runtime case input
- B. derived RMU rated voltage mirror written by the authoritative builder
- C. project settings / draft payload may carry other RMU ratings, but not a separate authoritative voltage
- D. all renderer-side inference forbidden

## Phase 1 Patch Scope

- UI shows RMU rated voltage as a derived value from `POI / MV Voltage (kV)`.
- RMU no longer has a separate manual override control on the SLD page.
- Builder forces `equipment_ratings.rmu.rated_kv` to the authoritative MV value.
- Divergent legacy RMU voltage payloads are ignored and normalized.
- Renderer compatibility paths now raise when `rmu.rated_kv` is missing.
