# Compatibility Notes V1

## Purpose

Document the non-breaking compatibility rules for the Phase 1 refactor so later changes do not silently shift calculation meaning, output schemas, or operating workflows.

## Preserved Behavior

- Stage 1 to Stage 3 mathematical behavior is frozen by golden cases.
- The legacy `dc_view` public helpers still work:
  - `load_data`
  - `run_stage1`
  - `run_stage3`
  - `size_with_guarantee`
- Current report and export code paths can continue calling the legacy UI-layer interface while the real computation lives in `calb_sizing_tool/services/`.
- Excel remains the active import source for defaults, DC block templates, SOH curves, and RTE curves.

## Service Extraction Mapping

| Legacy entry point | New implementation owner |
| --- | --- |
| `calb_sizing_tool.ui.dc_view.run_stage1` | `calb_sizing_tool.services.stage1_service.run_stage1` |
| `calb_sizing_tool.ui.dc_view.build_config_*` | `calb_sizing_tool.services.stage2_service.*` |
| `calb_sizing_tool.ui.dc_view.run_stage3` | `calb_sizing_tool.services.stage3_service.run_stage3` |
| `calb_sizing_tool.ui.dc_view.size_with_guarantee` | `calb_sizing_tool.services.dc_pipeline_service.size_with_guarantee` |

## Output Compatibility

The following outputs remain compatible with the legacy reporting and downstream flow:

- Stage 1 legacy dict keys
- Stage 2 legacy dict keys including `block_config_table`
- Stage 3 legacy dataframe column names
- Guarantee loop return tuple:
  - `stage2_dict`
  - `stage3_dataframe`
  - `stage3_meta_dict`
  - `iteration_count`
  - `poi_usable_energy_at_guarantee_year`
  - `converged`

## Current Transitional Constraints

- Database tables exist, but runtime DC sizing still reads master data from Excel bundles in Phase 1.
- Imported master data stores canonical promoted fields plus `raw_row_json`; not every Excel column is a first-class relational column yet.
- `Is_Default_Option` is still consumed from the in-memory Excel dataframe for Stage 2 block picking.
- AC sizing, SLD, and layout logic were intentionally not migrated in this phase except for future snapshot-read readiness.

## Change-Control Rule

Any future change to:

- formulas
- field names
- output table columns
- guarantee loop behavior
- profile selection logic

must update both:

- [BASELINE_FREEZE_PLAN_V1.md](d:/CALB_SizingTool/docs/BASELINE_FREEZE_PLAN_V1.md)
- [DATA_MODEL_MAP_V1.md](d:/CALB_SizingTool/docs/DATA_MODEL_MAP_V1.md)

and must regenerate the golden cases if the change is deliberate.
