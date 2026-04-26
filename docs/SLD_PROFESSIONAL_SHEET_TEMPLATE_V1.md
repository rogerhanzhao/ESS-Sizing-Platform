# SLD Professional Sheet Template V1

This patch reorganizes the `engineering_v2` renderer around an explicit
professional sheet/template layer.

## Scope

Changed files:

- `calb_diagrams/sld_professional_sheet.py`
- `calb_diagrams/sld_engineering_v2_renderer.py`
- `tests/unit/test_sld_professional_sheet.py`
- `tests/unit/test_sld_engineering_v2_renderer.py`

No sizing calculation logic was changed.

## Boundary

The new template layer consumes only a resolved
`SldV2LayoutPlan`.

It owns:

- left-side equipment/note panel sections
- reference-style MV/RMU geometry
- LV busbar span
- PCS/DC vertical drawing cadence
- professional template id: `professional_sheet_v1`

The renderer now owns only drawing primitives:

- lines
- disconnector/breaker/earth/CT symbols
- transformer vector symbols
- PCS converter symbols
- DC isolator/fuse symbols
- BESS/DC block symbols

## Drawing Adjustments

The first template pass also changes the `engineering_v2` candidate output:

- feeder identities are shown as `F1/F2/...` at LV and DC interfaces
- repeated visible `DC Isolator/Fuse` text is removed from the drawing body and
  retained only as hidden SVG text for regression/searchability
- multi-DC-block feeders use wider local spacing so BESS/DC block symbols do not
  overlap

## Why This Was Needed

Before this step, `engineering_v2` had the correct direction but still mixed
three responsibilities in one renderer file:

- page template
- engineering note composition
- SVG drawing primitives

That made every visual correction risky because changing one symbol could also
silently change topology spacing or the note panel.

## Current Result

The output image is intentionally not promoted to production default yet.

The current goal is structural: the professional sheet can now be reviewed and
iterated as a first-class object before switching the application default away
from `legacy_server`.

## Remaining Work

- Improve the professional symbols against the uploaded electrical references.
- Tune the RMU feeder drawing proportions and switchgear device placement.
- Improve multi-DC-block feeder branching.
- Add final visual acceptance before making `engineering_v2` production default.
- Keep the formal readiness gate in front of any official SLD export.
