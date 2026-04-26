# SLD Renderer Version Gap Analysis V2

## Scope

This review compares the currently available SLD renderer modes against the
professional electrical reference drawings provided by the user.

No Layout, login/RBAC, DC sizing math, or AC sizing math changes are included.

## Generated Review Outputs

The following outputs were regenerated for this review:

```text
outputs/sld_renderer_mode_comparison/case01_container_only_group1/legacy_server/sld.png
outputs/sld_renderer_mode_comparison/case01_container_only_group1/topology_v1/sld.png
outputs/sld_renderer_mode_comparison/case01_container_only_group1/engineering_v2/sld.png
outputs/sld_engineering_v2_preview/review_light/sld_engineering_v2.png
outputs/sld_engineering_v2_preview/review_dark/sld_engineering_v2.png
outputs/sld_engineering_v2_preview/review_multi_dc_light/sld_engineering_v2.png
```

## Reference Drawing Requirements

The reference drawings imply the following professional SLD rules:

```text
1. MV section must read as an RMU/switchgear one-line, not a generic block.
2. Ring In, transformer feeder, and Ring Out must be electrically distinct.
3. Transformer feeder must show recognizable switching/protection/CT/cable symbols.
4. Transformer must be shown with recognizable delta/wye vector-group expression.
5. LV busbar must be a clean one-line busbar with one feeder per PCS.
6. Each PCS feeder is a single-line feeder.
7. DC side should be PCS -> DC isolator/fuse/interface -> BESS/DC block.
8. Do not draw floating DC+ / DC- busbars for a one-line diagram.
9. Left note panel must list professional equipment/cable/BESS information.
10. Quantities and ratings must come from authoritative sizing/settings data.
```

## Version Comparison

| Renderer | Strength | Blocking Problems |
|---|---|---|
| `legacy_server` | Stable on the running server; has old one-line symbols. | Uses stale monolithic assumptions; still shows `BUSBAR A/B`, `2 circuits (A/B)`, `TBD`; DC side reads like coupled busbars; equipment notes are renderer-owned; cannot be trusted as a modern authoritative template. |
| `topology_v1` | Uses the newer topology/data contract and avoids shared DC+/- busbars. | Still reads as a block diagram, not a professional electrical SLD; RMU is a rectangular conceptual box; transformer feeder symbols are weak; DC interface floats text around a line; sections dominate the drawing; not close enough to the reference. |
| `engineering_v2` | Closest to the reference; has left note panel, RMU ring shape, transformer symbol, LV busbar, PCS, DC fuse, BESS symbols. | Still not production-grade: hardcoded drawing proportions; left panel is too literal and not tied to final project notes; BESS/DC block capacity can expose bad fixture/source granularity; multi-DC block branch drawing is visually awkward; RMU feeder symbols are approximate; no formal auto-generation policy; still manual preview. |

## Why All Current Versions Feel Bad

The issue is not browser cache.

There are three separate problems:

```text
1. Runtime selection:
   The Streamlit page still defaults to legacy_server.

2. Preview state:
   The page keeps the last generated SVG/PNG in st.session_state["sld_artifacts"].
   If the user does not clear or regenerate, the old picture remains visible.

3. Template maturity:
   None of the three renderers is currently a complete professional engineering
   drawing template. engineering_v2 is only the closest candidate.
```

## Data Issue Found During Visual Review

The review fixture currently renders:

```text
1~4 BESS (0.836 MWh*4)
```

This is not acceptable as evidence of a real project drawing. It likely comes
from the minimal regression Excel/run fixture and represents a test granularity,
not necessarily the final container/DC Block energy basis used in a real project.

This does not mean DC sizing math should be changed. It means SLD must reject or
warn on physically inconsistent drawing inputs before producing a formal drawing.

The formal SLD gate must compare:

```text
DC run snapshot total block quantity/energy
AC allocation total block quantity
SLD canonical dc_block_energy_mwh
rendered BESS/DC Block note quantity
```

If these do not match the active project/run, formal SLD must not be generated.

## Root Causes By Layer

### UI Layer

Current default:

```text
SLD page default renderer mode = legacy_server
```

This explains why the app still shows the old style after startup.

### Session Layer

Current preview artifact state is session-scoped:

```text
st.session_state["sld_artifacts"]
st.session_state["sld_pipeline_meta"]
```

Changing renderer mode or theme does not by itself guarantee a newly generated
diagram is displayed unless the user regenerates or clears preview.

### Renderer Layer

`engineering_v2` is closer to the reference but it is still a renderer patch
around a manually arranged page. It does not yet have a true drafting template
object that owns:

```text
sheet frame
professional note panel
RMU symbol composition
feeder symbol stack
busbar/feeder spacing rules
single-vs-multiple DC block branch rules
print/export-safe text sizing
```

### Data Contract Layer

PCS count and DC block allocation now come from the canonical path, but the SLD
still needs one more formal consistency check before promotion:

```text
AC allocation must reconcile with DC run snapshot.
BESS/DC Block energy shown on the drawing must come from the correct DC Block
unit basis for the selected scenario.
```

## Correction Direction

Do not continue patching `legacy_server` or `topology_v1` as the final solution.

Do not immediately promote current `engineering_v2` as production default.

The correct next implementation is a new professional template layer under the
existing `engineering_v2` mode:

```text
SldProfessionalSheet
SldProfessionalNotePanel
SldProfessionalRmuTemplate
SldProfessionalLvDcTemplate
SldFormalReadinessGate
```

The renderer should then become:

```text
canonical input
  -> topology
  -> engineering_v2 graph
  -> formal readiness gate
  -> professional sheet layout
  -> SVG/PNG
```

## Immediate Fix Plan

1. Add a formal SLD readiness gate.
   - Check persisted AC snapshot exists.
   - Check AC allocation matches DC run snapshot.
   - Check project SLD engineering settings are complete.
   - Check professional note fields are not missing in formal mode.

2. Replace the current `engineering_v2` drawing layout with a proper professional
   sheet template, not another block layout patch.

3. Keep renderer mode visible until acceptance closes.
   - Do not silently show `legacy_server` when the user expects the new template.
   - Clear preview automatically when renderer mode/theme/run/group/plugin changes.
   - Display the generated renderer mode above the preview.

4. Only after the readiness gate and professional sheet template pass visual
   review, switch the default from `legacy_server` to the approved professional
   mode.

## Current Decision

Current renderer status:

```text
legacy_server: keep only as running-server baseline/reference
topology_v1: keep only as data-contract regression path
engineering_v2: keep as candidate, but rebuild its sheet/template layer
```

None of the three current visual outputs should be called final engineering SLD.

## Implemented In This Review Step

The UI now stores a preview-control signature:

```text
run_id
group_index
theme
compact_mode
draw_summary
renderer_mode
plugin_id
```

When this signature changes, cached `sld_artifacts` and `sld_pipeline_meta` are
cleared before the next preview is shown. This removes the misleading
session-cache effect where an old SLD remains visible after changing renderer
mode or theme.

The first formal readiness gate is also now implemented:

```text
docs/SLD_FORMAL_READINESS_GATE_V1.md
calb_sizing_tool/services/sld_formal_readiness_service.py
```

It exposes whether the prepared SLD is formally usable before the renderer is
promoted as the project drawing output.

The first professional sheet/template layer is now implemented:

```text
docs/SLD_PROFESSIONAL_SHEET_TEMPLATE_V1.md
calb_diagrams/sld_professional_sheet.py
```

`engineering_v2` now builds a `professional_sheet_v1` object from the resolved
layout plan before rendering. This does not make the visual output final, but it
removes the previous renderer-only hardcoding and gives the RMU, note panel, LV,
PCS, and DC drawing regions a single template contract for the next visual pass.
