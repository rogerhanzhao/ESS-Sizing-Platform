# Claude Handoff — 10 MW / 8 PCS / 8 DC Block AC Block Upgrade

Date: 2026-07-24
Workspace: `D:\CALB_SizingTool`
Branch: `ops/ubuntu-docker-coexist-20260311`
HEAD at handoff: `f53bce5` — `docs(ops): record L2 deployment 8aaa663; mark L2 done, next is L3/P2`
Recovery status: invalid 1:8 draft removed; verified L2 baseline ready for publication

## 0. Claude: read this before taking action

This is an analysis and implementation handoff, not a completed 1:8 feature.

- The invalid 1:8 working-tree draft described below has been removed.
- Start from the recovered branch state; do not reconstruct or reuse the
  removed linear eight-DC implementation.
- The preserved L2 changes are the verified Site Array grouping/fire-road and
  report-integration work listed below.
- Sizing business logic remains frozen. The requested change is a governed
  AC Block product/configuration and physical topology upgrade, not permission
  to change DC sizing, SOH/RTE, scenario semantics, or capacity formulas.

The owner has authorized publishing this recovered baseline so the work can
continue in a Claude cloud task. The cloud task must honor the confirmed
geometry and preserve the open engineering decisions as settings or explicit
gates rather than inventing product data.

## 1. Owner-confirmed new requirement

Add a 10 MW, 40 ft AC Block configuration using:

- 8 PCS in one AC Block;
- 8 DC Blocks in one AC Block;
- nominal equal PCS basis: `8 × 1,250 kW = 10 MW`;
- existing DC product basis: `8 × 5.015 MWh = 40.12 MWh` nameplate;
- the 40 ft AC Block / PCS-MV station placed vertically at the center;
- four DC Blocks on the left and four DC Blocks on the right;
- each side is a 2×2 field made from two mirrored back-to-back DC pairs;
- the two mirrored pairs on each side are shoulder-to-shoulder, forming a
  `田`-shaped four-container field;
- left and right DC fields are mirror images.

The confirmed physical concept is **not** eight DC Blocks in one long row.

Conceptual plan:

```text
                              North

         West 4-DC field                         East 4-DC field
    ┌──────────┬──────────┐                 ┌──────────┬──────────┐
    │   DC-1   │   DC-2   │                 │   DC-5   │   DC-6   │
    │ mirrored back-to-back pair            mirrored back-to-back pair
    ├──────────┼──────────┤  3.0 m  ┌────┐  3.0 m  ├──────────┼──────────┤
    │   DC-3   │   DC-4   │  aisle  │40ft│  aisle  │   DC-7   │   DC-8   │
    │ mirrored back-to-back pair     │ AC │         mirrored back-to-back pair
    └──────────┴──────────┘          │vert│         └──────────┴──────────┘
            pair-to-pair             └────┘                pair-to-pair
```

The numbering is conceptual. Final numbering must follow cable-entry,
maintenance-door, and SLD conventions consistently.

## 2. Concept geometry recorded for discussion

Using the current product knowledge and US/NFPA concept rule profile:

- DC container: `6.058 × 2.438 m`;
- mirrored back-to-back gap: `0.30 m`;
- pair-to-pair gap: provisionally `0.90 m`;
- DC field to oil-filled PCS/MVT station aisle: provisionally `3.00 m`;
- nominal 40 ft station: `12.192 × 2.438 m`.

One four-DC `田` field:

```text
width  = 2 × 2.438 + 0.30 = 5.176 m
length = 2 × 6.058 + 0.90 = 13.016 m
```

Whole equipment-only AC Block envelope:

```text
east-west = 5.176 + 3.000 + 2.438 + 3.000 + 5.176 = 18.790 m
north-south = max(13.016, 12.192) = 13.016 m
```

Recorded concept envelope: approximately **18.79 m × 13.02 m**.

This excludes perimeter fire roads, external maintenance roads, fence
clearance, turning radii, project boundary, and by-others zones. The 0.90 m
and 3.00 m values remain rule-profile assumptions until the owner confirms
them for this exact 40 ft product.

## 3. Recommended electrical interpretation

The clean conceptual mapping is:

```text
West DC-1..DC-4  -> PCS-1..PCS-4 -> LV-A
East DC-5..DC-8  -> PCS-5..PCS-8 -> LV-B
LV-A + LV-B      -> one three-winding step-up transformer -> MV/RMU
```

The existing SLD topology builders already use even feeder distribution across
LV windings. Eight PCS with two LV secondaries therefore yields `4 + 4`
feeders without changing sizing formulas.

Important distinction:

- `one DC Block mapped to one PCS feeder` is a connection policy;
- `DC Block has one or two protected physical outputs` is a product property.

Do not force the DC product to `single-output` merely because this configuration
uses a one-to-one DC-to-PCS mapping. Transformer MVA, vector group, Uk%, LV
voltage, cooling class, and physical DC output capability are not yet
owner-confirmed.

## 4. Root cause in the current architecture

The current AC workflow treats two independent choices as a free cross-product:

1. choose global DC Blocks per AC Block (`1:1`, `1:2`, `1:4`);
2. independently choose a PCS/AC Block model.

That is insufficient for a fixed product configuration. A generic `1:8`
ratio could be combined with an incompatible 5 MW model.

The existing grouping also uses `ceil` plus `evenly_distribute`. For example:

- 9 DC Blocks under a generic 1:8 option become groups `[5, 4]`;
- 188 DC Blocks become a mix of 8- and 7-DC groups;
- neither result represents a fixed `8 DC / 8 PCS / 10 MW` product.

Therefore the target must be a governed configuration, not an isolated ratio.

Recommended configuration identity:

`ACBLK-10MW-8PCS-8DC-40FT-BILATERAL`

Minimum typed configuration fields:

| Field | Recorded concept value |
| --- | --- |
| `configuration_code` | `ACBLK-10MW-8PCS-8DC-40FT-BILATERAL` |
| `ac_power_mw` | `10.0` |
| `pcs_count` | `8` |
| `pcs_rating_kw` | `1250` |
| `dc_block_count` | `8` |
| `dc_block_model` | `CALB_5MWh_20FT_12R` |
| `ac_container_type` | `40ft` |
| `layout_variant` | `central_40ft_bilateral_4plus4` |
| `dc_field_split` | `[4, 4]` |
| `dc_connection_policy` | `dedicated_dc_to_pcs` |
| `transformer_topology` | `three_winding` — pending confirmation |
| `lv_winding_count` | `2` — pending confirmation |
| `pcs_per_lv_winding` | `[4, 4]` — pending confirmation |
| `status` | `concept_confirmed_partial` |

The repository already has a `ProductACBlock` database model, but AC sizing
still uses a simplified dropdown and the governed AC product table is currently
not the runtime source. Critical configuration fields should eventually become
typed/governed fields; low-frequency drawing metadata may remain versioned
metadata.

## 5. Recommended implementation boundary

### Phase A — homogeneous 1:8 configuration

Only allow this configuration when every generated AC Block has exactly eight
DC Blocks. The safest initial gate is:

```text
dc_blocks_total % 8 == 0
```

Selecting the configuration should bind, as one atomic choice:

- 8 DC Blocks;
- 8 PCS;
- 1,250 kW per PCS;
- 10 MW AC Block;
- 40 ft central station;
- `central_40ft_bilateral_4plus4` layout variant;
- explicit DC-to-PCS connection plan.

Do not expose `1:8` as a globally compatible ratio.

### Phase B — mixed tail configurations

If a project needs, for example, 188 DC Blocks:

```text
23 × 8 DC = 184 DC
remaining 4 DC -> a smaller governed AC Block configuration
```

That requires heterogeneous `ACBlockInstance[]` data. The current SLD V1
authoritative schema requires uniform PCS count and rating across all AC
Blocks, so mixed tails are a separate contract upgrade, not a small extension.

Recommended delivery: Phase A first, Phase B only after explicit owner approval.

## 6. Layout engine target

Do not extend the current linear layout with only a longer MV station.

Route by explicit layout variant:

```text
linear_end_station
├─ existing 2 DC + 20 ft station
└─ existing 4 DC + 20 ft station

central_40ft_bilateral_4plus4
└─ new west 4 DC + central vertical 40 ft station + east 4 DC
```

The new variant should output equipment placements, not only one envelope:

- equipment ID and type;
- x/y coordinate;
- width, height, and rotation;
- side (`west`, `center`, `east`);
- mirrored-pair ID;
- door/service orientation;
- cable-trench route;
- internal aisle polygons;
- equipment-only envelope;
- rule profile and concept-status provenance.

Report and site-array code must consume this same geometry result. They must
not reconstruct the unit from average `dc_blocks_total / ac_blocks_total`.

## 7. SLD and report target

SLD regression case:

- one AC Block;
- eight 1,250 kW PCS feeders;
- two LV secondary groups, four feeders per group;
- eight DC Block nodes;
- explicit DC-1..8 to PCS-1..8 mapping;
- no symbol, label, or wire collision;
- layout-side numbering consistent with SLD numbering.

The official transformer schedule must use governed product or Engineering
Settings values. Do not silently turn `10 MW / 0.9 = 11.11 MVA` into an
approved transformer nameplate.

Report Section 8 should render the bilateral 4+4 unit. Site-array/report
context must carry `configuration_code` and `layout_variant` directly instead
of inferring the drawing from the average DC-per-AC value.

## 8. Current execution state

### Verified baseline before the bad 1:8 draft

The interrupted Claude L2 task was recovered and completed locally on
2026-07-23. Before any 1:8 draft was applied:

- `python -m compileall -q app.py calb_sizing_tool calb_diagrams` passed;
- full `python -m pytest tests -q` passed: **326 passed**;
- no commit, stage, push, or deployment was made;
- the verified L2 worktree contained exactly:
  - `calb_diagrams/site_array_concept.py`
  - `calb_sizing_tool/reporting/report_v2.py`
  - `tests/unit/test_site_array_concept.py`

### Recovered publication state (2026-07-24)

The later invalid 1:8 hunks were surgically removed. The recovered functional
scope is again exactly the verified L2 set:

```text
calb_diagrams/site_array_concept.py
calb_sizing_tool/reporting/report_v2.py
tests/unit/test_site_array_concept.py
```

Publication also includes this handoff and the Current Status pointer.

Verification after recovery:

- `python -m compileall -q app.py calb_sizing_tool calb_diagrams` passed;
- targeted L2 tests passed: **23 passed**;
- full `python -m pytest tests -q` passed: **326 passed**;
- frozen AC/DC sizing modules have no remaining diff;
- no 1:8 feature implementation is present in the recovered code.

## 9. Recovery completed; cloud implementation boundary

The recovery sequence is complete. Claude cloud must now:

1. read `docs/CURRENT_STATUS_2026-07-12.md` and this handoff in full;
2. confirm its checkout is based on
   `ops/ubuntu-docker-coexist-20260311`, not `main`/`master`;
3. treat the bilateral 4+4 geometry as the confirmed physical requirement;
4. implement a governed configuration rather than a generic unrestricted
   `1:8` ratio;
5. keep unresolved transformer/product values configurable and clearly marked;
6. run targeted tests, `compileall`, and the full test suite;
7. do not merge or deploy automatically.

## 10. Open decisions for the owner

1. Confirm `DC-1 -> PCS-1` through `DC-8 -> PCS-8` as the connection policy.
2. Confirm one three-winding transformer with two LV secondaries, four PCS on
   each secondary.
3. Confirm whether both DC-field-to-AC-station aisles are 3.0 m.
4. Confirm whether the first delivery supports only totals divisible by eight,
   with mixed 8/4/2/1 tail configurations deferred.
5. Confirm actual 40 ft station dimensions if they differ from nominal ISO
   `12.192 × 2.438 m`.
6. Confirm transformer nameplate, vector group, Uk%, LV voltage, cooling, and
   DC Block protected-output capability separately; none is inferred here.

## 11. Files to read for the eventual implementation

Read only the touched domains:

- AC configuration authority:
  `calb_sizing_tool/services/ac_sizing_service.py`
- AC UI:
  `calb_sizing_tool/ui/ac_view.py`
- governed AC product model:
  `calb_sizing_tool/infra/db/models/product_ac_block.py`
- physical DC-to-PCS contract:
  `calb_sizing_tool/schemas/ac_electrical_topology.py`
- AC-to-SLD adapter:
  `calb_sizing_tool/adapters/ac_to_sld_adapter.py`
- SLD authoritative schema:
  `calb_sizing_tool/schemas/sld_authoritative_input.py`
- SLD topology grouping:
  `calb_sizing_tool/services/sld_topology_builder.py`
  and `calb_sizing_tool/services/sld_engineering_v2_builder.py`
- unit arrangement:
  `calb_diagrams/ac_block_arrangement_v2.py`
- site-array concept:
  `calb_diagrams/site_array_concept.py`
- report context/render:
  `calb_sizing_tool/reporting/report_context.py`
  and `calb_sizing_tool/reporting/report_v2.py`
- product/layout knowledge:
  `docs/AC_BLOCK_PRODUCT_KNOWLEDGE_2026-07-18.md`
- frozen boundary:
  `docs/SIZING_LOGIC_CANON_V1.md`

Do not scan the whole repository.
