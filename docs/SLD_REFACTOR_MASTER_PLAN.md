# SLD Refactor Master Plan

This plan starts after Phase 0 audit. The goal is to separate SLD input, topology/rule derivation, and renderer responsibilities without changing sizing math.

## Guiding Rule

Refactor order must be strict. The SLD renderer cannot be cleaned safely until the input contract is frozen. Runtime truth cannot be switched safely until canonical input and topology boundaries exist.

## Phase Sequence

### Phase 1: Canonical Input And Strict Validation

- Boundary:
  - define the single canonical SLD input object
  - add strict validation and rejection of missing/ambiguous fields
  - do not rewrite renderer layout logic
- Deliverables:
  - `SldCanonicalInput` schema
  - mapper from current `run_bundle + ac_snapshot + options` into canonical input
  - validation errors for guessed or missing engineering fields
  - contract tests
- Verification:
  - unit tests for required fields and invalid combinations
  - current page still renders through compatibility adapter
- Stop condition:
  - renderer still consumes compatibility spec, but input ambiguity is explicit

### Phase 2: Topology And Rule Builder Extraction

- Boundary:
  - move feeder allocation, block grouping, equipment schedule derivation, and display policy out of renderer
  - do not yet replace the drawing engine completely
- Deliverables:
  - topology builder
  - rule builder
  - resolved drawing model separate from raw canonical input
- Verification:
  - unit tests for topology/rule outputs
  - compatibility comparison against frozen current examples
- Stop condition:
  - renderer receives resolved topology/rule data instead of deriving them itself

### Phase 3: Renderer Boundary Cleanup

- Boundary:
  - make renderer a pure drawing layer
  - remove hidden business defaults from renderer
  - preserve visual output during transition
- Deliverables:
  - cleaned renderer API
  - renderer-only tests
  - migration notes for removed renderer-side guesses
- Verification:
  - SVG/spec regression comparisons against frozen cases
  - no business calculations remain in renderer except geometry/layout math
- Stop condition:
  - renderer no longer infers equipment text, topology, or sizing policy

### Phase 4: Runtime Source Of Truth Switch For SLD

- Boundary:
  - remove SLD dependence on session-derived AC output
  - bind SLD generation to persisted runtime snapshot(s)
  - do not start layout/plugin platform expansion here
- Deliverables:
  - DB-backed SLD input loading path
  - persisted SLD input snapshot or equivalent resolved contract record
  - page restore by `run_id`
- Verification:
  - integration test from persisted run to SLD render without session AC data
  - manual refresh/reload validation
- Stop condition:
  - SLD page renders from persisted runtime truth, not session cache

### Phase 5: Regression Freeze And Rollout

- Boundary:
  - freeze SLD outputs and contracts
  - add acceptance coverage
  - no major architecture shift here
- Deliverables:
  - golden SLD cases
  - spec regression baselines
  - SVG regression baselines or normalized snapshot baselines
  - release checklist
- Verification:
  - regression suite green
  - manual acceptance on representative projects
- Stop condition:
  - SLD behavior is reproducible and safe to evolve

## Non-Parallel Constraints

The following phases must not run in parallel:

- Phase 1 and Phase 2:
  - topology extraction before input freeze will calcify the wrong contract
- Phase 2 and Phase 3:
  - renderer cleanup before topology/rule extraction will mix refactors and break auditability
- Phase 3 and Phase 4:
  - runtime truth switch before renderer boundary cleanup will preserve hidden renderer guesses
- Phase 5 with any earlier phase:
  - regression freeze must be last, otherwise baselines will be invalidated during active refactor

## Validation Matrix

| Phase | Primary validation | Secondary validation |
| --- | --- | --- |
| 1 | contract/unit tests | current page no-regression smoke |
| 2 | topology/rule unit tests | compatibility comparison to Phase 0 frozen examples |
| 3 | renderer regression tests | visual/manual spot checks |
| 4 | integration tests from persisted run | refresh/restore manual tests |
| 5 | golden regression suite | release checklist |

## Immediate Next Step

Next stage only:

- Phase 1: establish SLD canonical input and strong validation

Not allowed next:

- renderer large rewrite
- topology rewrite before canonical input
- DB main-chain switch for SLD before canonical input and topology separation
- layout work
- plugin platform expansion
