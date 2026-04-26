# SLD Professional Electrical Template V1

## Scope

This patch changes the `engineering_v2` preview renderer from a block-style SLD
to a professional electrical single-line drawing template based on the uploaded
reference drawings.

It does not change:

```text
DC sizing math
AC sizing math
PCS/DC allocation logic
Layout page
login/RBAC
default production SLD mode
```

## Template Basis

The professional template now expresses:

1. MV ring-in and ring-out feeders with terminal arrows.
2. RMU / MV switchgear relationship without the old hanging-box busbar layout.
3. Transformer feeder with switching/protection/CT-style symbols.
4. Step-up transformer with delta/wye vector-group visual expression.
5. LV busbar feeding one vertical PCS feeder per PCS.
6. PCS converter symbols below the LV busbar.
7. DC isolator/fuse between PCS and BESS.
8. BESS/DC Block rectangles as battery symbols, not floating DC+ / DC- busbars.
9. A left-side engineering notes panel similar to the uploaded reference.

## Data Rules

PCS count, PCS rating, LV voltage, frequency, DC voltage, DC Block count, and DC
Block allocation all come from the resolved V2 graph/layout plan.

The renderer does not invent:

```text
PCS quantity
DC Block quantity
feeder allocation
MV voltage
LV voltage
DC voltage
transformer rating
```

If a professional drawing field is not present in authoritative SLD inputs, the
preview output marks it explicitly as `MISSING: ...` and records a warning in
metadata. Current examples include cable specifications and BESS cell
specification when they are not provided by the project settings or run data.

Supported professional note fields include:

```text
equipment_ratings.cables.mv_cable_spec
equipment_ratings.cables.lv_cable_spec
equipment_ratings.cables.dc_cable_spec
equipment_ratings.battery_cell_spec
```

The SLD formal settings / override form now exposes `BESS cell spec` so the
left-side professional notes can be completed from case-level engineering
settings instead of remaining a renderer-owned placeholder.

Transformer vector-group drawing is rendered with shape geometry for the delta
and wye symbols. It is not represented by a text glyph, which avoids font and
encoding drift in SVG/PNG output.

## Background Modes

The same template supports:

```text
dark
light
```

The UI already passes the selected theme through the SLD options. The preview
script can also generate either mode:

```text
python scripts/generate_sld_engineering_v2_preview.py --theme light
python scripts/generate_sld_engineering_v2_preview.py --theme dark
```

The preview script can also inject professional note specs for review:

```text
python scripts/generate_sld_engineering_v2_preview.py --theme light --mv-cable-spec MV-3x1C-240mm2 --lv-cable-spec LV-3P+PE-630mm2 --dc-cable-spec DC-1x240mm2 --battery-cell-spec "LFP 3.2V/314Ah"
```

## Multi-DC-Block Behavior

For `1 PCS : 1 DC Block`, the diagram renders:

```text
LV Busbar -> PCS -> DC Isolator/Fuse -> BESS/DC Block
```

For multiple DC Blocks under one PCS feeder, the diagram renders one feeder with
a local branch to the required number of BESS/DC Block symbols. It does not
return to the old floating `DC+ BUSBAR / DC- BUSBAR` expression.

## Current Boundary

`engineering_v2` remains a manual preview mode. The production default is not
changed in this patch.
