# SLD Server Baseline Comparison V1

## Scope

This document compares three SLD implementations:

1. Server stable version: `8568af4` on `/opt/calb-sizingtool/app`.
2. Repository HEAD: `f0f197b`.
3. Local working tree: `f0f197b` plus uncommitted SLD V3/V4 changes.

The purpose is to explain why the server-rendered SLD is stable while the repository/local refactored SLD remains visually and electrically unsatisfactory.

This document does not change Layout, login, RBAC, or DC sizing mathematics.

## Version Facts

### Server Stable Version

Server repo reported by the operator:

```text
/opt/calb-sizingtool/app
branch: ops/ubuntu-docker-coexist-20260311
commit: 8568af4 ops: add maintenance timer and cleanup flow
```

SLD files present at `8568af4`:

```text
calb_diagrams/sld_pro_renderer.py
calb_diagrams/specs.py
calb_sizing_tool/ui/single_line_diagram_view.py
calb_sizing_tool/ui/sld_inputs.py
```

Files not present in the server stable SLD path:

```text
calb_diagrams/sld_layout_engine.py
calb_diagrams/symbol_library.py
calb_sizing_tool/schemas/sld_topology.py
calb_sizing_tool/services/sld_pipeline_service.py
calb_sizing_tool/services/sld_topology_builder.py
calb_sizing_tool/plugins/sld_engineering_plugin.py
```

This means the server stable drawing is not produced by the new topology/layout/symbol pipeline.

### Repository HEAD

Local repository HEAD during this audit:

```text
branch: ops/ubuntu-docker-coexist-20260311
commit: f0f197b Finalize SLD runtime stabilization and cleanup
```

Major SLD changes from `8568af4` to `f0f197b`:

```text
calb_diagrams/sld_pro_renderer.py        101 insertions, 1651 deletions
calb_diagrams/sld_layout_engine.py       532 insertions, new file
calb_diagrams/symbol_library.py          168 insertions, new file
calb_sizing_tool/schemas/sld_topology.py 116 insertions, new file
calb_sizing_tool/services/sld_pipeline_service.py 239 insertions, new file
calb_sizing_tool/services/sld_topology_builder.py 589 insertions, new file
calb_sizing_tool/ui/single_line_diagram_view.py 343 insertions, 551 deletions
```

Line-count comparison:

```text
8568af4 calb_diagrams/sld_pro_renderer.py: 1476 lines
f0f197b/current calb_diagrams/sld_pro_renderer.py: 162 lines
current calb_diagrams/sld_layout_engine.py: 483 lines
current calb_diagrams/symbol_library.py: 220 lines
```

The renderer was not merely cleaned up. The original visual template was replaced by a new pipeline.

### Local Working Tree

The local working tree contains additional uncommitted SLD changes on top of `f0f197b`.

SLD-specific dirty files include:

```text
calb_diagrams/sld_layout_engine.py
calb_diagrams/specs.py
calb_diagrams/symbol_library.py
calb_sizing_tool/schemas/sld_render_input.py
calb_sizing_tool/schemas/sld_topology.py
calb_sizing_tool/services/sld_topology_builder.py
calb_sizing_tool/ui/single_line_diagram_view.py
calb_sizing_tool/ui/sld_inputs.py
tests/fixtures/sld_cases/case01_container_only_group1/*
tests/integration/test_sld_render_regression.py
tests/integration/test_sld_topology_regression.py
tests/unit/test_sld_layout_engine.py
tests/unit/test_symbol_library.py
```

These local changes attempted to move from `mv_bus/rmu/dc_busbar` toward `mv_ring_in/mv_switchgear/mv_transformer_feeder/mv_ring_out/dc_interface`. They improve naming and remove the floating DC busbar concept, but they still sit on top of the incomplete fixed-slot drawing model.

## Runtime Chain Comparison

### Server Stable Chain

At `8568af4`, the SLD runtime chain is:

```text
calb_sizing_tool/ui/single_line_diagram_view.py
  -> build_sld_group_spec(...)
  -> render_sld_pro_svg(...)
```

Important behavior:

```text
single_line_diagram_view.py imports build_sld_group_spec and render_sld_pro_svg directly.
style_id = "raw_v05"
diagram_inputs["style"] = "Raw V0.5 (Stable)"
```

Data sources are mostly Streamlit/session/project-state dictionaries:

```text
stage13_output = st.session_state.get("stage13_output") or dc_results.get("stage13_output") or {}
ac_output = st.session_state.get("ac_output") or ac_results or {}
diagram_inputs = project_state.get("diagram_inputs") or st.session_state.setdefault("diagram_inputs", {})
```

The server version is fallback-heavy but visually coherent because the same monolithic renderer controls:

```text
equipment list
MV/RMU drawing
transformer drawing
LV busbar drawing
PCS drawing
DC busbar/circuit drawing
label placement
theme
dimensions
```

### Repository HEAD Chain

At `f0f197b`, the SLD runtime chain became:

```text
single_line_diagram_view.py
  -> run_sld_pipeline_from_run_bundle(...)
  -> SldEngineeringPlugin
  -> SldCanonicalInput
  -> SldTopology
  -> build_sld_layout_plan(...)
  -> symbol_library
  -> render_sld_svg(...)
```

This is architecturally cleaner, but the drawing engine is not yet a complete engineering SLD engine.

Current model still lacks:

```text
explicit electrical terminals
explicit switchgear bays
source/target ports on edges
proper edge routing by port
collision-aware text placement
visual regression gates
human-accepted server baseline comparison
```

## Why The Server Version Looks More Stable

The server stable version is not more correct in data governance. It has real problems:

1. It mixes persisted/session/UI values.
2. It uses fallback logic in UI/spec/renderer.
3. It can map MV voltage to RMU class voltage inside display logic.
4. It allows renderer/spec to infer missing engineering values.

However, it has one practical advantage: the visual template is centralized and self-consistent.

The monolithic renderer makes one set of assumptions about the whole drawing. That is why the picture is stable even though the internals are not clean.

## Why The Repository And Local Versions Look Wrong

The refactor split the rendering system into topology, layout, symbol, and plugin layers before the engineering drawing model was complete.

The result is a hybrid:

```text
data architecture: closer to authoritative topology
drawing architecture: still fixed-coordinate symbolic slots
engineering semantics: incomplete
visual tests: insufficient
```

This creates the current failure mode:

1. The code has stricter field contracts.
2. The topology has better names.
3. The renderer still draws a template, not a real terminal/bay/port graph.
4. Tests pass because they check structure/text snapshots, not engineering readability.
5. The visual output remains conceptually awkward.

The local V4 changes reduce some wrong concepts, especially floating DC busbars, but they do not solve the deeper issue: edges do not attach to formal ports and switchgear bays.

## Specific Technical Mismatches

### 1. RMU/MV Area

Server stable renderer draws a fixed MV/RMU structure inside one renderer. It is visually consistent but conceptually old.

Repository/local refactor tries to express:

```text
Ring In
RMU / MV Switchgear
Transformer Feeder
Ring Out
```

But the model does not yet have real bay terminals:

```text
ring_in_port
transformer_feeder_in_port
transformer_feeder_out_port
ring_out_port
```

Without ports, the layout engine places symbols and routes lines by coordinates. This is why the drawing can look like a box diagram rather than a proper single-line diagram.

### 2. Transformer Feeder

The desired engineering logic is:

```text
RMU transformer feeder bay -> transformer HV terminal -> transformer LV terminal -> LV busbar
```

Current topology mostly says node-to-node:

```text
switchgear_to_transformer_feeder
transformer_feeder_to_transformer
transformer_to_lv_busbar
```

But it does not express HV/LV ports. Therefore the renderer cannot guarantee physically meaningful connection points.

### 3. LV Feeders

The desired structure is:

```text
LV busbar -> feeder F1 -> PCS-1
LV busbar -> feeder F2 -> PCS-2
...
```

Current local changes label feeders better, but the layout still treats feeder identity mostly as a label over a vertical connector. There is no explicit feeder equipment or port model.

### 4. DC Side

Server stable and older repo versions used local DC busbars and circuits:

```text
DC BUSBAR A
DC BUSBAR B
Circuit A
Circuit B
```

This looked like a mixture of a DC architecture diagram and an SLD.

The local V4 change moves toward:

```text
PCS -> DC interface -> DC Block
```

That is directionally correct for single-line view, but the symbol implementation still visually implies a local boxed device and does not fully model the terminal relationship.

### 5. Equipment List

Server stable equipment list is renderer-owned. It is visually aligned with the old renderer but can hide fallback values.

Repository/local equipment list is closer to authoritative input, but it still relies on the refactored chain being correct. When the drawing model is incomplete, the equipment list can be correct while the picture is still not engineering-readable.

## Conclusion

The core issue is not one bad line or one wrong symbol. The project replaced the server-stable monolithic SLD renderer with a new topology/layout/symbol pipeline before implementing a real engineering drawing model.

Therefore:

1. Do not continue patching the current local V4 renderer as the final solution.
2. Do not deploy the current repository/local SLD renderer over the stable server output.
3. Preserve the server renderer as the production visual baseline.
4. Build a new SLD V2 engine in parallel behind a renderer mode switch.

## Recommended Recovery Strategy

### Step 1: Preserve Server Stable Renderer As Baseline

Create a local baseline artifact from `8568af4`:

```text
SLD_SERVER_BASELINE_RENDERER = 8568af4:calb_diagrams/sld_pro_renderer.py
SLD_SERVER_BASELINE_SPEC = 8568af4:calb_diagrams/specs.py
SLD_SERVER_BASELINE_UI_CHAIN = 8568af4:calb_sizing_tool/ui/single_line_diagram_view.py
```

This baseline should be used only for comparison and controlled fallback, not as a reason to undo all platform refactoring.

### Step 2: Add Renderer Mode Isolation

Introduce an SLD renderer mode boundary:

```text
legacy_server
topology_v1
engineering_v2
```

Recommended behavior:

```text
Production default: legacy_server until V2 passes visual acceptance.
Development default: engineering_v2 only when explicitly selected.
Current topology_v1: kept only for regression comparison.
```

This prevents the unfinished refactored renderer from silently replacing the stable server drawing.

### Step 3: Build Engineering SLD V2 Model

V2 must model electrical topology with ports:

```text
node_id
node_type
ports[]
equipment_id
ratings
```

Edges must be terminal-to-terminal:

```text
source_node_id
source_port_id
target_node_id
target_port_id
edge_type
feeder_id
```

Minimum node model:

```text
mv_grid_ring_in
rmu_bay_ring_in
rmu_busbar
rmu_bay_transformer_feeder
rmu_bay_ring_out
transformer_hv_terminal
transformer_lv_terminal
lv_busbar
lv_feeder
pcs
dc_interface
dc_block
```

Minimum visible SLD chain:

```text
Ring In -> RMU Ring-In Bay -> RMU Busbar -> Transformer Feeder Bay
-> Transformer -> LV Busbar -> F1/F2/F3/F4 -> PCS
-> DC Isolator/Fuse -> DC Block
RMU Busbar -> Ring-Out Bay -> Ring Out
```

### Step 4: Separate Data Correctness From Drawing Correctness

Keep the already-corrected data rules:

```text
POI / MV Voltage and RMU Rated Voltage visible values must stay synchronized.
SLD must prefer persisted authoritative data.
Session/draft mode must be marked as draft.
Renderer must not infer PCS count, DC block count, voltage, or allocation.
```

But do not assume these rules make the drawing correct. Drawing correctness needs topology/port/layout validation.

### Step 5: Add Visual Acceptance Gates

Current tests are not enough. Add generated artifacts:

```text
server_8568_baseline.svg
repo_head_topology_v1.svg
local_engineering_v2_candidate.svg
```

Acceptance must check:

```text
MV ring-in / transformer feeder / ring-out are readable.
Transformer HV/LV relation is clear.
LV feeders F1/F2/F3/F4 are unambiguous.
PCS count and ratings come from authoritative input.
DC side is single-line PCS -> DC interface -> DC Block.
No floating DC+ / DC- busbar lines.
No renderer-side guessing.
```

Human visual review remains required before production switch.

## Immediate Next Work

The next implementation step should be narrow:

1. Add a renderer mode boundary without changing Layout/login/RBAC/DC sizing.
2. Wire the server-stable rendering path as `legacy_server` fallback.
3. Keep current topology renderer as `topology_v1`, not production default.
4. Start `engineering_v2` as a separate port-based engine.

Do not continue to mutate the current local V4 as the final renderer.

## Non-Goals

This recovery plan does not:

```text
change Layout
change login
change RBAC
change DC sizing mathematics
revert the whole platform
replace persisted data-source work
remove authoritative AC-to-SLD contracts
```

The target is only to stop SLD drawing regression and rebuild the drawing engine boundary correctly.
