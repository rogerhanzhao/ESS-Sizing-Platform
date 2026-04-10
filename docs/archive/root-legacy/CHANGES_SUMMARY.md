# Implementation Summary: CALB Sizing Tool Fixes

**Date**: 2025-12-30  
**Version**: v2.1 (Refactored)  
**Focus**: AC Sizing Logic, Report Generation, and Data Type Fixes

---

## Changes Made

### 1. AC Sizing Page (ac_view.py)

#### 1.1 AC:DC Ratio Label Correction
- **File**: `calb_sizing_tool/ui/ac_view.py` (line 121)
- **Change**: Corrected UI label from "DC:AC Ratio" to "AC:DC Ratio"
- **Reason**: The ratio represents AC:DC (AC Blocks per DC Blocks), not DC per AC
- **Help Text**: Updated to clarify "Select the ratio of AC Blocks per DC Blocks (1:1, 1:2, or 1:4)"

#### 1.2 Container Size Calculation
- **File**: `calb_sizing_tool/ui/ac_view.py` (lines 168-171)
- **Change**: Container size now based on SINGLE AC Block power, not total project AC power
- **Old Logic**: `auto_container = "40ft" if total_ac_power > 5 else "20ft"`
- **New Logic**: `auto_container = "40ft" if single_block_ac_power > 5 else "20ft"`
- **Reason**: PCS&MV SKID container size (20ft/40ft) depends on individual block power, not aggregate project power
- **Display**: Shows both single block and total AC power for clarity

#### 1.3 Power Overhead Warning Baseline
- **File**: `calb_sizing_tool/ui/ac_view.py` (lines 196-200)
- **Change**: Power overhead calculation now based on POI requirement, not single AC block
- **Old Logic**: `overhead/block_size_mw * 100` (comparing to one AC block)
- **New Logic**: `overhead/target_mw * 100` (comparing to total POI requirement)
- **Reason**: 30% overhead tolerance should be evaluated against the total POI requirement, not individual block capacity
- **Example**: With 100 MW POI requirement and 115 MW total AC, overhead is 15% of POI (acceptable), not 300% of a 5 MW block

#### 1.4 Removed Unused Import
- **File**: `calb_sizing_tool/ui/ac_view.py` (line 14)
- **Change**: Removed unused `create_combined_report` import from V1 export_docx
- **Reason**: Only V2.1 report generation is used; V1 functions are deprecated

---

### 2. Single Line Diagram Page (single_line_diagram_view.py)

#### 2.1 PCS Count and DC Blocks Status Type Handling
- **File**: `calb_sizing_tool/ui/single_line_diagram_view.py` (lines 204-224)
- **Issue**: st.metric() was receiving lists instead of scalars, causing Streamlit ValueError
- **Fix**: Added type checking and conversion for both `pcs_count_status` and `dc_blocks_status`
- **Logic**:
  - If `pcs_count_status[0]` is a list/tuple, sum its values
  - If `dc_blocks_status` is a list/tuple, sum all numeric values or use length as fallback
  - Convert all non-TBD values to string before passing to st.metric()
- **Reason**: `_resolve_pcs_count_by_block()` returns a list of counts per block; we need the first element, but handle cases where even the first element is a list

---

### 3. Report V2.1 Enhancement (report_v2.py)

#### 3.1 Efficiency Chain Table Addition
- **File**: `calb_sizing_tool/reporting/report_v2.py` (lines 258-272)
- **Change**: Added efficiency breakdown table after Stage 1 section
- **Efficiency Components**:
  - Total Efficiency (one-way)
  - DC Cables
  - PCS
  - Transformer
  - RMU / Switchgear / AC Cables
  - HVT / Others
- **Data Source**: From `ReportContext.efficiency_components_frac` (populated from stage1 DC sizing results)
- **Format**: Uses `format_percent()` helper to display as percentages with fraction notation
- **Reason**: Efficiency chain data was being extracted but not displayed in the report. Users need visibility into component-level efficiency losses for validation and documentation

#### 3.2 Imports Verified
- Confirmed `format_percent` and `format_value` are imported (line 11)
- ReportContext has `efficiency_components_frac: Dict[str, float]` field (report_context.py:39)
- Efficiency components extracted from stage1 data in `build_report_context()` (report_context.py:206-212)

---

## Architecture Notes

### AC Sizing Configuration
- **File**: `calb_sizing_tool/ui/ac_sizing_config.py`
- PCS count (2 or 4 per block) is **independent** of DC:AC ratio
- DC:AC ratio only determines how DC blocks are allocated across AC blocks
- Both 2-PCS and 4-PCS configurations are available for all three ratio options (1:1, 1:2, 1:4)
- This allows flexible PCS sizing without being constrained by DC block allocation strategy

### Report Context Chain
1. **Input**: DC sizing results (stage1, stage2, stage3_df) + AC results + diagram artifacts
2. **Processing**: `build_report_context()` in report_context.py extracts and normalizes data
3. **Validation**: ReportContext dataclass ensures all required fields are present
4. **Output**: `export_report_v2_1()` in report_v2.py generates DOCX with complete sections

### Session State Usage
- DC results stored in: `st.session_state["dc_results"]` → `dc_result_summary`, `stage13_output`
- AC results stored in: `st.session_state["ac_results"]` → combined with ac_output dict
- Diagram results: `st.session_state["diagram_results"]`, `st.session_state["layout_results"]`
- Report uses selective reads to avoid overwriting working session state

---

## Testing Checklist

- [ ] AC Sizing page displays correct "AC:DC Ratio" label
- [ ] Container size shows "40ft" only when single block > 5 MW
- [ ] Power overhead warning shows as % of POI requirement
- [ ] Single Line Diagram page loads without TypeError for pcs_count_status
- [ ] Technical report includes Efficiency Chain table with all 5 components
- [ ] Efficiency values match DC sizing page (dc_view.py:1125-1130)
- [ ] Report generates successfully for all ratio options (1:1, 1:2, 1:4)
- [ ] Both 2-PCS and 4-PCS configurations available for each ratio

---

## Future Considerations

1. **Stage 3 Data Integration**: Full implementation of degradation curves in SLD visualization
2. **Layout Rendering**: Update to show 6 battery modules per DC block (per design spec)
3. **SLD Electrical Semantics**: Implement independent DC BUSBAR per PCS module
4. **Report Validation**: Add consistency checks between stages (e.g., POI usable energy vs. guarantee)
5. **V1 Deprecation**: Remove `create_combined_report()` and related V1 functions from export_docx.py after v2.1 stabilization

---

## Files Modified

| File | Lines | Change Type | Status |
|------|-------|------------|--------|
| ac_view.py | 12-14, 121, 168-171, 196-200 | Logic + Label | ✅ Complete |
| ac_sizing_config.py | None | Reference only | ✓ No change needed |
| single_line_diagram_view.py | 206-207, 223-224 | Type handling | ✅ Complete |
| report_v2.py | 258-272 | Data display | ✅ Complete |
| report_context.py | None | Reference only | ✓ Already correct |

