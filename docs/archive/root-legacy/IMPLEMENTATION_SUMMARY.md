# CALB ESS Sizing Tool - Report & Diagram Implementation Summary

## Overview
This document summarizes the implementation of DOCX report generation with proper data plumbing, SLD/Layout diagram fixes, and AC Sizing enhancements for the CALB ESS Sizing Tool.

## 1. Report Generation (V2.1 Only)

### 1.1 Efficiency Chain Fix
**Issue**: Report showed "0.00%" for all efficiency components except Total
**Root Cause**: Components not being loaded from DC SIZING stage1 output
**Solution**: 
- Efficiency values are read from `stage1` (DC SIZING output) in `build_report_context()`
- Fields extracted: `eff_dc_cables_frac`, `eff_pcs_frac`, `eff_mvt_frac`, `eff_ac_cables_sw_rmu_frac`, `eff_hvt_others_frac`, `eff_dc_to_poi_frac`
- Report includes disclaimer: "Efficiencies do not include Auxiliary losses"
- Validation ensures all values are present and within bounds

**Code Location**: 
- `calb_sizing_tool/reporting/report_context.py` lines 210-224
- `calb_sizing_tool/reporting/report_v2.py` lines 382-390

**Test Coverage**: `tests/test_report_v2_fixes.py::test_efficiency_chain_uses_dc_sizing_values`

### 1.2 AC Block Configuration Aggregation
**Issue**: Report might show repetitive per-block configurations
**Solution**:
- Implemented `_aggregate_ac_block_configs()` function
- Identical configurations are merged with block count
- Format: "N × M PCS @ Ppower MW"
- AC Sizing Section shows summary (not detailed per-block list)

**Code Location**: `calb_sizing_tool/reporting/report_v2.py` lines 222-256

**Test Coverage**: `tests/test_report_v2_fixes.py::test_ac_block_config_not_verbose`

### 1.3 Stage 3 Degradation Data Inclusion
**Issue**: POI Usable Energy chart not showing full year-by-year degradation
**Solution**:
- Chart generation uses full `stage3_df` with all year indices
- Data plotted with blue bars and red POI guarantee line
- X-axis shows years 0 to project life
- Y-axis shows POI Usable Energy in MWh

**Code Location**: `calb_sizing_tool/reporting/report_v2.py` lines 71-96, 430-445

### 1.4 Report Data Consistency Validation
**Issue**: No validation to prevent mixing DC and AC sizing data
**Solution**:
- Implemented `_validate_report_consistency()` function
- Checks power/energy balance, efficiency chain completeness, PCS count consistency
- Returns warnings (non-blocking) for user review
- All data sources come from single ReportContext

**Code Location**: `calb_sizing_tool/reporting/report_v2.py` lines 258-281

**Test Coverage**: `tests/test_report_v2_fixes.py::test_report_consistency_validation`

## 2. AC Sizing Configuration

### 2.1 Container Type Logic
**Requirement**: Container type determined by single AC Block size, not total
**Implementation**:
```python
single_block_ac_power = pcs_per_ac * pcs_kw / 1000  # MW per block
auto_container = "40ft" if single_block_ac_power > 5 else "20ft"
```
- Used in AC Sizing UI to inform user before calculation
- Also used in final configuration summary

**Code Location**: `calb_sizing_tool/ui/ac_view.py` lines 169-171

### 2.2 AC:DC Ratio Selection
**Configuration Options**:
- 1:1 = 1 AC Block per 1 DC Block (maximum flexibility)
- 1:2 = 1 AC Block per 2 DC Blocks (balanced approach)
- 1:4 = 1 AC Block per 4 DC Blocks (compact design)

**User Guidance**:
- Auto-recommendation based on DC Block count
- Help text explains the ratio meaning
- Power overhead warning based on total POI requirement (not single block)

**Code Location**: `calb_sizing_tool/ui/ac_view.py` lines 90-200

### 2.3 PCS Configuration Options
**Available PCS Ratings**: 1250 kW, 1500 kW, 1725 kW, 2000 kW, 2500 kW
**PCS per AC Block**: 2 or 4 (no 3-module combinations)
**Container Sizing**:
- 20ft: Single block ≤ 5 MW
- 40ft: Single block > 5 MW
- Example: 4 × 1250 kW = 5 MW → 20ft

## 3. SLD (Single Line Diagram) Improvements

### 3.1 DC BUSBAR Independence
**Requirement**: Each PCS must have independent DC BUSBAR (no sharing)
**Implementation**:
- Per-PCS DC BUSBAR A and DC BUSBAR B drawn separately
- Each DC Block connects ONLY to its allocated PCS's BUSBAR
- No cross-PCS connections at DC level

**Code Location**: `calb_diagrams/sld_pro_renderer.py` lines 476-572
- Line 476-490: Individual BUSBAR drawing per PCS
- Line 514-572: DC Block allocation to independent BUSBARS

**Key Code**:
```python
# DC BUSBAR A for this PCS (independent for each PCS)
busbar_a_x1 = pcs_center_x - 35
busbar_a_x2 = pcs_center_x + 35
dwg.add(dwg.line((busbar_a_x1, dc_bus_a_y), (busbar_a_x2, dc_bus_a_y), class_="thick"))

# Connect DC Block ONLY to this PCS's BUSBAR
line_x_a = cell_x + dc_box_w * 0.35
dwg.add(dwg.line((line_x_a, cell_y), (line_x_a, dc_bus_a_y), class_="thin"))
dwg.add(dwg.line((line_x_a, dc_bus_a_y), (pcs_center_x, dc_bus_a_y), class_="thin"))
```

### 3.2 AC Side Topology
**Components**:
- LV BUSBAR: Single horizontal bus for all PCS AC outputs
- Transformer: Step-up to MV voltage
- RMU/Switchgear: MV connections to grid
- Circuit A/B separation maintained in DC domain

**Code Location**: `calb_diagrams/sld_pro_renderer.py` lines 250-420

### 3.3 Electrical Accuracy
**DC Side**:
- Each PCS module has independent DC BUSBAR A & B
- Fuse symbols between PCS and BUSBAR
- Circuit labels (A/B) shown
- DC Blocks explicitly connect to BUSBAR, not to Battery Bank

**AC Side**:
- LV output from each PCS to common LV BUSBAR
- PCS modules grouped (typically 2 or 4 per AC Block)
- Voltage specifications noted (e.g., "690 V")

## 4. Layout Rendering

### 4.1 DC Block Interior Design
**Specification**:
- 6 battery modules in 1×6 single row configuration
- No "Cooling" or "Battery" text labels (as per requirements)
- Simple rectangles with consistent spacing
- Module width = (total_width - padding - gaps) / 6

**Code Location**: `calb_diagrams/layout_block_renderer.py`
- Lines 115-144: `_draw_dc_interior()` (svgwrite version)
- Lines 261-291: `_draw_dc_interior_raw()` (raw SVG string version)

**Key Code**:
```python
cols = 6  # Always 6 columns
rows = 1  # Single row
module_spacing = max(2.0, min(grid_w, grid_h) * 0.03)
module_w = (grid_w - module_spacing * (cols - 1)) / cols
module_h = grid_h

for row in range(rows):
    for col in range(cols):
        mod_x = grid_x_start + col * (module_w + module_spacing)
        mod_y = grid_y_start + row * (module_h + module_spacing)
        dwg.add(dwg.rect(insert=(mod_x, mod_y), size=(module_w, module_h), class_="thin"))
```

### 4.2 AC Block (PCS&MVT SKID) Design
**Interior Divisions**:
- PCS Unit area (~55% width): Shows 2×2 grid of PCS modules
- Transformer area (~30% width): Transformer symbol
- RMU area (~15% width): RMU/switchgear symbol
- Labels and voltage specs included

**Code Location**: `calb_diagrams/layout_block_renderer.py` lines 147-202

## 5. Report Context Data Model

### 5.1 ReportContext Class
**Purpose**: Single source of truth for all report data
**Key Fields**:
- Input parameters: `poi_power_requirement_mw`, `poi_energy_requirement_mwh`, `poi_energy_guarantee_mwh`
- DC Configuration: `dc_blocks_total`, `dc_block_unit_mwh`, `dc_total_energy_mwh`
- AC Configuration: `ac_blocks_total`, `pcs_per_block`, `ac_block_size_mw`
- Efficiency: `efficiency_chain_oneway_frac`, `efficiency_components_frac` (dict)
- Stage Data: `stage1`, `stage2`, `stage3_df`, `stage3_meta`

**Code Location**: `calb_sizing_tool/reporting/report_context.py` lines 13-58

### 5.2 Report Context Building
**Function**: `build_report_context()` in `report_context.py`
**Process**:
1. Extract stage13_output (DC SIZING result)
2. Read efficiency components from stage1
3. Load AC output configuration
4. Process Stage 3 degradation data
5. Validate and construct ReportContext

## 6. Testing & Validation

### 6.1 Test Suite
All tests in `tests/test_report_v2_fixes.py` (3/3 passing):

1. **test_efficiency_chain_uses_dc_sizing_values**
   - Verifies efficiency chain reads from DC SIZING
   - Checks all components are populated
   - Validates report text includes efficiency disclaimer

2. **test_ac_block_config_not_verbose**
   - Ensures AC configs are aggregated (not repeated per-block)
   - Checks summary format is concise

3. **test_report_consistency_validation**
   - Validates power/energy consistency checks
   - Ensures no data source mixing

### 6.2 Test Execution
```bash
cd /opt/calb/prod/CALB_SIZINGTOOL
source .venv/bin/activate
python -m pytest tests/test_report_v2_fixes.py -v
```

## 7. Version Notes

### V2.1 Only
- V1 report generation code has been removed
- All exports use V2.1 format
- Report filename: `<ProjectName>_Combined_V2_1_<timestamp>.docx`

### Auxiliary Loss Handling
- **NO** auxiliary losses are included in any calculations
- Efficiency values represent core losses only (cables, PCS, transformer, RMU, HVT)
- Report explicitly states this in efficiency section

## 8. Deployment Checklist

- [x] DC SIZING stage1 includes all efficiency components
- [x] AC Sizing properly calculates container size
- [x] SLD drawing creates independent DC BUSBARs per PCS
- [x] Layout rendering shows 6 modules in 1×6 configuration
- [x] Report aggregates identical AC configurations
- [x] Report includes Stage 3 degradation data
- [x] All tests pass
- [x] No V1 report code present
- [x] Efficiency disclaimer included in reports
- [x] ReportContext properly validated

## 9. Known Limitations

1. **Complex PCS Allocations**: 
   - Recommended to use uniform PCS counts across AC Blocks
   - Edge cases with highly uneven distributions may need manual review

2. **Very Large Projects**:
   - Projects with >100 AC Blocks may have rendering performance considerations
   - SLD focuses on single AC Block group visualization

3. **Missing SLD/Layout**:
   - If user exports without generating SLD/Layout, report notes their absence
   - This is not an error, just informational

## 10. File Locations Reference

### Core Report Generation
- `calb_sizing_tool/reporting/report_v2.py` - Main export function `export_report_v2_1()`
- `calb_sizing_tool/reporting/report_context.py` - `build_report_context()`
- `calb_sizing_tool/reporting/export_docx.py` - DOCX builder utilities
- `calb_sizing_tool/reporting/formatter.py` - Value formatting functions

### Diagrams
- `calb_diagrams/sld_pro_renderer.py` - SLD generation
- `calb_diagrams/layout_block_renderer.py` - Layout generation
- `calb_diagrams/specs.py` - Diagram specifications and utilities

### UI Views
- `calb_sizing_tool/ui/ac_view.py` - AC Sizing page
- `calb_sizing_tool/ui/report_export_view.py` - Report export page
- `calb_sizing_tool/ui/single_line_diagram_view.py` - SLD generation UI

### Tests
- `tests/test_report_v2_fixes.py` - Report generation tests
- `tests/test_report_v2_stage3_inclusion.py` - Stage 3 data tests
- `tests/test_sld_*.py` - Various SLD tests

---

**Last Updated**: 2025-12-31
**Branch**: ops/fix/report-stage3
**Status**: Ready for deployment ✅
