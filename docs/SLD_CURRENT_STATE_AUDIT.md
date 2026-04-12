# SLD Current State Audit

Branch: `ops/ubuntu-docker-coexist-20260311`

Scope: Phase 0 audit only. This document records the current SLD input chain, render chain, repeated builders, fallback risks, and renderer/business coupling. It does not change current SLD behavior.

## Files Audited

- `calb_sizing_tool/ui/single_line_diagram_view.py`
- `calb_diagrams/specs.py`
- `calb_diagrams/sld_pro_renderer.py`
- `calb_sizing_tool/sld/snapshot_single_unit.py`
- `calb_sizing_tool/sld/ac_block_group.py`
- `calb_sizing_tool/ui/sld_inputs.py`

Additional evidence read to resolve the real runtime chain:

- `calb_sizing_tool/services/diagram_service.py`
- `calb_sizing_tool/plugins/sld_engineering_plugin.py`
- `calb_sizing_tool/sld/snapshot_builder_v2.py`
- existing SLD-related tests under `tests/`

## Executive Conclusion

The current production SLD page does not render from `single_unit_snapshot`. The current runtime chain is:

1. `single_line_diagram_view.py` reads `run_id` from UI and AC data from session-backed state.
2. `diagram_service.render_sld_from_run_bundle()` calls `SldEngineeringPlugin`.
3. `SldEngineeringPlugin` rebuilds legacy compatibility payloads:
   - `stage13_output` from `run_bundle`
   - `dc_summary` from `run_bundle`
   - `sld_inputs` from `SldRenderOptions`
   - `ac_output` from `AcSnapshot.output`
4. `calb_diagrams.specs.build_sld_group_spec()` converts those mixed inputs into `SldGroupSpec`.
5. `calb_diagrams.sld_pro_renderer.render_sld_pro_svg()` consumes `SldGroupSpec`.

Current final renderer-consumed input is `SldGroupSpec`.

That means the current SLD "truth" is not a single canonical object. It is a mixed compatibility assembly:

- DC side: reconstructed from DB-backed `run_bundle`
- AC side: still session-derived `ac_output`
- diagram options: UI defaults mapped into `sld_inputs`
- final drawing contract: `SldGroupSpec`

## Direct Answer: What Is The Real SLD Input Source?

| Candidate | Current role | Is it the final renderer input? | Audit conclusion |
| --- | --- | --- | --- |
| `session_state` | Supplies `ac_output`, `dc_last_run_id`, and cached SLD artifacts in the current page | No | It is a source for AC-side data and UI cache, but not the direct renderer contract |
| `stage13_output` | Rebuilt inside `SldEngineeringPlugin` from `run_bundle` via compatibility adapter | No | Intermediate legacy DTO, not final renderer input |
| `ac_output` | Comes from `AcSnapshot.output`, which is currently built from `session_state` or project-state cache | No | Critical upstream source, but still intermediate |
| `single_unit_snapshot` | Used by legacy raw/pro chains and legacy tests | No | Not used by current `single_line_diagram_view.py` runtime path |
| `sld_group_spec` / `SldGroupSpec` | Built in `build_sld_group_spec()` and passed into `render_sld_pro_svg()` | Yes | This is the actual final input consumed by the current renderer |

## Current SLD Data Flow

### Current UI main path

1. `single_line_diagram_view._build_ac_snapshot()` reads:
   - `st.session_state["ac_output"]`
   - or `project_state["ac_results"]`
   - or `state.ac_results`
2. User enters or reuses `run_id`.
3. `AccessControlService.load_dc_run_bundle(run_id)` loads DC run data from DB.
4. `render_sld_from_run_bundle()` creates plugin input.
5. `SldEngineeringPlugin.render()` reconstructs `stage13_output`, `dc_summary`, and `sld_inputs`.
6. `build_sld_group_spec()` resolves counts, ratings, labels, and layout params.
7. `render_sld_pro_svg()` draws SVG/PNG and artifact metadata.

### Legacy path still present in repo

1. UI-style `sld_inputs` dictionary.
2. `build_ac_block_group_spec()`
3. `build_single_unit_snapshot()`
4. legacy snapshot validators / legacy renderers

This chain still exists in code and tests, but it is not the current page main path.

## Current SLD Rendering Flow

1. `SldEngineeringPlugin._build_stage13_output()`
2. `SldEngineeringPlugin._build_sld_inputs()`
3. `build_dc_result_summary()`
4. `build_sld_group_spec()`
5. `render_sld_pro_svg()`
6. artifact persistence

The renderer therefore depends on:

- DB-backed DC run bundle
- session-backed AC output
- UI option defaults
- multiple compatibility adapters

## File Responsibilities And Problems

| File | Current responsibility | Main problem |
| --- | --- | --- |
| `calb_sizing_tool/ui/single_line_diagram_view.py` | Collect `run_id`, read AC data from session-backed state, call diagram service, preview/download artifacts | UI is thin, but still depends on session-derived AC data instead of a canonical SLD input |
| `calb_diagrams/specs.py` | Define `SldGroupSpec` and build it from `stage13_output + ac_output + dc_summary + sld_inputs` | Builder contains heavy inference/default logic and acts as hidden business-rule layer |
| `calb_diagrams/sld_pro_renderer.py` | Draw professional SLD SVG/PNG from `SldGroupSpec` | Renderer contains topology/rule derivation, engineering text defaults, and equipment inference that should not live in drawing code |
| `calb_sizing_tool/sld/snapshot_single_unit.py` | Build legacy single-unit SLD snapshot and validate its schema | Repeats upstream inference/allocation logic already present elsewhere; not current page source of truth |
| `calb_sizing_tool/sld/ac_block_group.py` | Build `AcBlockGroupSpec` from mixed AC/DC/UI input | Duplicates the same count/rating/default inference later repeated by `build_sld_group_spec()` |
| `calb_sizing_tool/ui/sld_inputs.py` | Render manual SLD electrical input widgets for RMU/transformer/busbar/cables/fuse | Currently has no runtime caller; dangling UI contract still defines another possible input dialect |

## Repeated Builders And Duplicate Responsibilities

### Core duplicate builders

| Builder | Current role | Repeated logic |
| --- | --- | --- |
| `build_ac_block_group_spec()` | Build intermediate AC group object | PCS count resolution, transformer sizing fallback, DC block allocation fallback, DC block energy fallback |
| `build_single_unit_snapshot()` | Wrap group info into legacy snapshot | feeder generation, DC block allocation, site/group total inference, label injection |
| `build_sld_group_spec()` | Build current renderer spec | Repeats PCS count, transformer sizing, DC allocation, equipment defaults, layout params |

### Additional duplicate path discovered

| Builder | Current role | Audit note |
| --- | --- | --- |
| `build_sld_chain_snapshot_v2()` | Alternative legacy/pro chain snapshot builder | Another parallel snapshot dialect; not in current page flow, but increases maintenance drift |

### UI-side duplication

- `ui/sld_inputs.py` defines another SLD electrical input schema for:
  - RMU
  - transformer
  - LV busbar
  - cables
  - DC fuse
- The current page does not call it, so repository-level SLD inputs are already split across:
  - plugin `SldRenderOptions`
  - legacy `sld_inputs` dict
  - `AcSnapshot.output`
  - `run_bundle`

## Fallback / Guess / Silent Default Risks

### Count inference

- AC block count:
  - `build_sld_group_spec()` uses `num_blocks` or `ac_blocks_total`.
  - If missing, it tries `total_pcs // pcs_per_block`.
  - If still missing, it silently forces `1`.
- PCS count per group:
  - `_resolve_pcs_count_by_block()` falls back to `total_pcs` distribution.
  - If still missing and only one AC block exists, it silently defaults to `[4]`.
- DC blocks per feeder:
  - may come from `sld_inputs`
  - or `ac_output["dc_block_allocation"]`
  - or `ac_output["dc_blocks_per_feeder_by_block"]`
  - or `dc_blocks_total_by_block`
  - or site total even distribution
  - or fallback to `group_spec.pcs_count` in legacy snapshot path

### Rating inference

- PCS rating:
  - `sld_inputs["pcs_rating_each_kw"]`
  - or `sld_inputs["pcs_rating_each_kva"]`
  - or `ac_output["pcs_power_kw"]`
  - or `block_size_mw * 1000 / pcs_count`
  - or hard default `1250.0`
- Transformer rating:
  - `sld_inputs["transformer_rating_mva"]`
  - or `ac_output["transformer_mva"]`
  - or `transformer_kva / 1000`
  - or `block_size_mw / 0.9`
  - or hard default `5.0`
- DC block energy:
  - `sld_inputs["dc_block_energy_mwh"]`
  - or `dc_summary.dc_block.capacity_mwh`
  - or hard default `5.106` / standard container MWh

### Electrical detail defaults

`ui/sld_inputs.py` silently defaults to:

- RMU rated voltage `24.0 kV`
- RMU rated current `630 A`
- RMU short-circuit `25.0 kA/3s`
- CT ratio `200/1`
- CT class `5P20`
- CT burden `10 VA`
- transformer vector group `Dyn11`
- transformer `Uk=7.0%`
- tap range `+/-2x2.5%`
- cooling `ONAN`
- LV busbar `2500 A`, `25 kA`
- cable specs `TBD`
- fuse spec `TBD`

These are reasonable placeholders for UI prototyping, but they are silent engineering assumptions if the data is not explicitly managed.

### Display and theme defaults

- `SldRenderOptions.theme` defaults to `dark`.
- `build_sld_group_spec()` defaults theme to `light` when `sld_inputs` is absent.
- `render_sld_pro_svg()` defaults `draw_summary` to `not dark_mode` only when the field is absent.
- Current plugin always injects `draw_summary`, so renderer default behavior is already bypassed by adapter behavior.

### Renderer-side derivation that can drift

- MV cable text defaults to `XLPE/Cu-{mv_kv}`
- DC cable text defaults to `XLPE/Cu-DC-{dc_voltage}`
- RMU rated voltage is guessed from MV class via `_rmu_class_kv()`
- LV busbar current is derived from transformer MVA if missing
- PCS breaker current is derived from PCS rating and LV voltage
- DC switch / fuse text falls back to `TBD` or `DC{voltage}, TBD`
- `compact_mode` caps displayed block stacks to `2` per feeder
- non-compact mode collapses block rendering when `dc_blocks_total > 6`

These are no longer just styling defaults; they change what the engineering drawing appears to claim.

## Business / Topology Logic Mixed Into Renderer

The following responsibilities should not remain inside `sld_pro_renderer.py`:

- equipment schedule synthesis:
  - RMU, CT, transformer, LV busbar, cable, fuse text generation
- electrical sizing derivation:
  - LV current estimation from transformer MVA
  - PCS breaker current estimation from PCS rating and LV voltage
  - DC switch / fuse labeling
- topology decisions:
  - PCS grouping split
  - local busbar logic
  - `lv_bus_split` behavior
  - `show_individual_blocks` threshold (`dc_blocks_total <= 6`)
  - compact-mode block cap (`max_blocks <= 2`)
- render policy defaults:
  - dark/light theme behavior
  - summary visibility policy

In the current implementation, topology, rule, and drawing concerns are interleaved.

## Current Test Situation

Current tests exist, but they are not true SLD regression tests.

### What exists

- smoke tests for legacy snapshot/raw renderers
- smoke tests for `build_sld_group_spec() + render_sld_pro_svg()`
- page no-crash tests
- plugin integration tests that render from `run_bundle`
- artifact registry tests

### What is missing

- no golden SLD contract test that freezes `SldGroupSpec` for real project scenarios
- no golden SVG regression test for current runtime path
- no strict canonical input contract test
- no dedicated topology/rule builder regression test because topology is still buried in builder/renderer code

Conclusion: current SLD tests prove the chain does not crash and emits artifacts, but they do not freeze engineering output behavior.

## Highest-Risk Problems

1. AC-side data for SLD still comes from session-backed `ac_output`, while DC-side data comes from DB `run_bundle`. This creates mixed-source drift.
2. Business inference is duplicated across multiple builders, so the same scenario can resolve counts/ratings differently depending on which chain is used.
3. Renderer owns engineering defaults and topology decisions, so visual output can change when drawing code is edited, even if business intent was not meant to change.

## Recommended Next Layer To Change

Next layer must be the SLD canonical input contract and validation layer.

Reason:

- It is the smallest safe cut that does not rewrite renderer behavior.
- It lets us freeze current mixed inputs into one explicit contract.
- It creates a stable boundary before touching topology extraction or renderer cleanup.

## Phase 0 Freeze Statement

Phase 0 conclusion:

- current renderer output has not been modified
- current SLD page behavior has not been modified
- no plugin rewrite or layout work has been started here

Next stage can only establish canonical SLD input and strict validation.
