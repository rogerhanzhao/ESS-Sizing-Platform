# AC Sizing Unified Flow V2 (2026-07-27)

Status: **implemented and verified locally.**

This is the active owner-authorized direction for AC Sizing. It supersedes the
old UI design that exposed a separate `Governed Product` / `standard product
preset` branch. Historical governed outputs remain readable for traceability;
they are not a sizing path for new AC runs.

Cloud execution, unresolved risks and the cross-module acceptance test are in
`CLAUDE_CLOUD_AC_SIZING_SLD_EXECUTION_GUIDE_2026-07-28.md`.  That guide must
be read before changing this flow.

## 1. Single business flow

```text
DC sizing result + POI P/E
  -> choose generic DC-to-AC grouping (1:1 / 1:2 / 1:4 / 1:8)
  -> choose PCS count and unit rating for one AC Block
  -> explicitly confirm two- or three-winding transformer topology
  -> validate DC protected-output capacity and POI power / energy
  -> optionally bind an exactly matching catalogue product
  -> persist one AC output consumed by SLD, layout and report
```

No catalogue item may change grouping, PCS count, PCS rating, or calculated AC
Block quantity. Product binding only supplies verified nameplate, LV voltage,
cooling and vector-group data after the sizing selection is already made.

## 2. Grouping logic

| Choice | AC Block count | Meaning |
| --- | --- | --- |
| 1:1 | `ceil(DC / 1)` | one DC Block per AC Block |
| 1:2 | `ceil(DC / 2)` | up to two DC Blocks per AC Block |
| 1:4 | `ceil(DC / 4)` | up to four DC Blocks per AC Block |
| 1:8 | `ceil(DC / 8)` | up to eight DC Blocks per AC Block |

The allocation is an even distribution over that calculated number of AC
Blocks. A non-multiple is a real tail group, not an excuse to pad DC Blocks or
automatically create a separate product family.

## 3. PCS and product comparison policy

- The normal catalogue comparison preference is **2 x 2,500 kW PCS = 5 MW AC
  Block**.
- When the user selects **1:8**, the UI additionally offers **8 x 1,250 kW PCS
  = 10 MW** as a small-PCS sizing candidate.
- Both are selectable architectures, not mandatory products. A user may choose
  another valid PCS architecture or bind no catalogue product.
- Matching filters on the already selected PCS count, unit kW and, when
  declared, transformer topology. A product with incomplete engineering fields
  is marked partial; missing data is never invented.

## 4. Physical connection rule for tails

Each DC Block contributes its confirmed number of protected PCS output
circuits (currently default two). For every AC Block:

```text
minimum DC Blocks = ceil(PCS per AC Block / DC output circuits per DC Block)
```

The selected PCS architecture must be feasible for the smallest AC Block in
the grouping. Example: 202 DC Blocks at 1:8 are balanced as `20 x 8 DC + 6 x
7 DC`, not forced into a fixed 8-DC product head plus a small tail. The 8 x
1,250 kW architecture needs at least four DC Blocks with two outputs each, so
it is valid in that 202-DC example but correctly blocked for a small 1:8 group
of only three DC Blocks. A 2 x 2,500 kW architecture needs only one DC Block.
This rule is a connection-safety validation, not a new DC or AC sizing formula.

## 5. Downstream contract

Every new run persists the selected ratio, exact per-block DC allocation, PCS
count/rating, topology confirmation, LV-busbar topology and protected-output
count. SLD uses those explicit electrical fields; it must not infer transformer
topology from PCS quantity.

For an exact homogeneous `1:8 + 8 x 1,250 kW + three-winding` selection, the
run carries `central_40ft_bilateral_4plus4` as an **owner-confirmed concept
layout variant**. It is a routing condition for the already selected physical
architecture, not a product lock. Any tail group, a different PCS architecture
or a two-winding transformer remains on the generic layout path.

## 6. Deliberately removed UI seam

The removed checkbox previously opened a second governed engine that forced a
10 MW / 8 DC head and manufactured 8/4/2/1 tail products. It had its own POI
closure semantics and bypassed the normal grouping/PCS controls. That made a
catalogue preset act like a sizing rule and caused excessive AC power in normal
projects. The historical service is retained only so existing persisted runs
can still be opened; it is no longer exposed for new sizing.

## 7. Verification record and next handoff

Verified on 2026-07-27:

1. `python -m compileall -q app.py calb_sizing_tool calb_diagrams` and the
   full test suite passed: **477 passed**.
2. The live Streamlit page exposes four grouping buttons and no old governed
   product-preset switch. For selected 1:8, the optional 8 x 1,250 kW model is
   the visible first candidate; every other generic PCS candidate remains
   selectable.
3. A real Guest run was exercised end to end: 92 DC Blocks -> 12 AC Blocks at
   1:8 -> 8 x 1,250 kW -> confirmed three-winding -> optional Sineng
   `SINENG-EH-10000-HB-UD-10-33` binding -> Engineering V2 SLD. The resulting
   draft SLD rendered with two independent LV distribution sections, eight PCS
   feeders and eight DC Blocks for the selected full group.
4. Draft SLD input now uses the existing 1,500 V draft preset only when no
   project setting or explicit override exists. Strict/formal mode remains
   blocked until the owner saves engineering settings.
5. Guest SLD preview now deliberately avoids Artifact Registry and filesystem
   registration. It returns only session/download artifacts and states that
   boundary accurately in the UI.

Local catalogue status for the next maintainer: the active local database has
18 `ProductACBlock` records from `vendor_datasheet_2026-07-24`, including the
Sineng record above and `KEHUA-BCS10000K-C-HUD-T8`. Catalogue binding is still
optional and does not alter any sizing result.

Keep these validation cases when changing this flow:

1. unit tests for ratios, candidate visibility, tail feeder capacity and
   product-topology matching;
2. the full test suite and live Streamlit verification;
3. a 1:8 tail that is too small for its PCS feeder count must block with a
   clear physical connection message;
4. an exact homogeneous 1:8 / 8 x 1,250 kW / three-winding run must retain the
   bilateral concept-layout condition without becoming a product lock.

Related history: `GOVERNED_AC_BLOCK_10MW_8PCS_8DC_2026-07-24.md` and
`CLAUDE_HANDOFF_10MW_8PCS_8DC_2026-07-24.md` are historical context only. This
document takes precedence for new work.
