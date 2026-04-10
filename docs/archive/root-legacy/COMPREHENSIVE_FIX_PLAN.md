# Comprehensive Fix Plan: Report Export & Diagram Generation

## Executive Summary
This document outlines the complete fix plan for:
1. **DOCX Report Export**: Data consistency, AC Block aggregation, efficiency chain validation
2. **SLD Diagram**: Verify DC BUSBAR independence (already implemented)
3. **Layout Diagram**: Verify DC Block 1x6 layout (already implemented)
4. **Regression Testing**: Compare master vs refactor vs current branch
5. **2000 kW PCS Support**: Already implemented, verify in UI

## Phase 1: Code Audit & Current State Assessment

### 1.1 Report Generation Modules
- **File**: `calb_sizing_tool/reporting/report_v2.py`
- **Status**: Has aggregation logic for AC blocks (`_aggregate_ac_block_configs`)
- **Issue**: Need to verify data sources and consistency

### 1.2 SLD Diagram
- **Files**: `calb_diagrams/sld_pro_renderer.py`, `calb_sizing_tool/sld/generator.py`
- **Status**: Already implements independent DC BUSBAR per PCS
- **Need**: Verify no shared Circuit A/B lines across blocks

### 1.3 Layout Diagram  
- **Files**: `calb_diagrams/layout_block_renderer.py`
- **Status**: Already implements 1x6 DC Block layout (see lines 122-144)
- **Need**: Verify liquid cooling is minimal; no small box elements

### 1.4 AC View (2000 kW PCS)
- **Files**: `calb_sizing_tool/ui/ac_sizing_config.py`, `calb_sizing_tool/ui/ac_view.py`
- **Status**: 2000 kW already in PCS configs; custom option available
- **Need**: Verify UI displays correctly

## Phase 2: Data Flow & Session State Mapping

### Inputs (Dashboard)
- `st.session_state["poi_power_mw"]` → POI Power Requirement (MW)
- `st.session_state["poi_energy_mwh"]` → POI Energy Requirement (MWh)
- `st.session_state["poi_energy_guarantee_mwh"]` → Guaranteed POI Energy (MWh)

### DC Sizing Output
- `st.session_state["dc_results"]` (dict):
  - `total_dc_mwh` → DC Nameplate @BOL (MWh)
  - `poi_usable_mwh_at_guarantee_year` → POI Usable @ Guarantee Year
  - `efficiency_components` → Efficiency chain (fractions)
  - `efficiency_chain_oneway` → Total one-way efficiency

### AC Sizing Output
- `st.session_state["ac_results"]` (dict):
  - `ac_blocks_total` → Number of AC Blocks
  - `pcs_per_block` → PCS modules per AC Block
  - `ac_block_size_mw` → Power per AC Block (MW)
  - `pcs_rating_kw` → Individual PCS power (kW)

### Diagrams
- `st.session_state["sld_svg"]` → SLD SVG bytes
- `st.session_state["layout_svg"]` → Layout SVG bytes

## Phase 3: Fixes to Implement

### Fix 3.1: Report Data Mapping (report_v2.py)
**Problem**: Report may reference wrong session_state keys or calculate incorrect values

**Solution**:
- Verify `ReportContext` initialization uses correct field mapping
- Ensure efficiency chain comes directly from DC SIZING output
- Validate AC block configuration aggregation includes all necessary fields
- Add explicit "No Auxiliary" notation in efficiency section

**Files Modified**:
- `calb_sizing_tool/reporting/report_v2.py` (lines ~400-650)
- `calb_sizing_tool/reporting/report_context.py` (field validation)

### Fix 3.2: Report Template Structure
**Problem**: File naming, chapter structure, or field consistency issues

**Solution**:
- Standardize file naming: `CALB_<ProjectName>_BESS_Proposal_<YYYYMMDD>_V2.1.docx`
- Ensure Executive Summary shows both:
  - Requested POI Power/Energy (inputs)
  - Guaranteed POI Usable @ Guarantee Year (DC results)
- Add Chapter 6 & 7 for SLD/Layout with auto-generation fallback
- Remove any debug text ("aa")

**Files Modified**:
- `calb_sizing_tool/ui/report_export_view.py` (file naming, export flow)
- `calb_sizing_tool/reporting/report_v2.py` (template structure)

### Fix 3.3: AC Block Aggregation
**Problem**: Report might list every AC Block separately even if configs are identical

**Solution**:
- `_aggregate_ac_block_configs()` function already exists (line 245)
- Verify it's used in report table generation
- Ensure "Block Count" column shows aggregated count
- Handle edge cases (mixed configurations)

**Files Modified**:
- `calb_sizing_tool/reporting/report_v2.py` (lines 245-280, table generation)

### Fix 3.4: Efficiency Chain Validation
**Problem**: Total efficiency might not match product of components; source unclear

**Solution**:
- `_validate_efficiency_chain()` already exists (line 177)
- Ensure warnings are logged (not silently ignored)
- Make sure data source is explicitly DC SIZING output
- Add "Exclude Auxiliary" note to report table

**Files Modified**:
- `calb_sizing_tool/reporting/report_v2.py` (lines 177-242)

### Fix 3.5: SLD Diagram Verification
**Problem**: Potential shared DC BUSBAR across PCS

**Solution**:
- Review `sld_pro_renderer.py` lines 270-510 (already refactored)
- Verify each PCS has completely independent DC BUSBAR A/B
- Confirm no horizontal Circuit A/B lines cross multiple PCS
- Test with multi-PCS scenario

**Files to Verify**:
- `calb_diagrams/sld_pro_renderer.py` (DC BUSBAR drawing logic)
- `calb_sizing_tool/sld/generator.py` (PCS/DC Block allocation)

### Fix 3.6: Layout Diagram Verification
**Problem**: DC Block might show 2x3 or have unwanted elements

**Solution**:
- Verify `layout_block_renderer.py` lines 122-144 (1x6 grid layout)
- Confirm all 6 modules drawn as single row, properly spaced
- Verify "Liquid Cooling" (if present) occupies minimal space
- Confirm no spurious "small box" on left side

**Files to Verify**:
- `calb_diagrams/layout_block_renderer.py` (DC Block interior)

### Fix 3.7: Streamlit Widget Issues
**Problem**: First-click error on Single Line Diagram page

**Solution**:
- Check `single_line_diagram_view.py` for data_editor keys
- Use `st.session_state.setdefault()` before widget creation
- Avoid re-assigning to widget keys after instantiation

**Files to Check**:
- `calb_sizing_tool/ui/single_line_diagram_view.py`

## Phase 4: Regression Testing

### Test Cases
1. **Input Set A**: 100 MW, 400 MWh → verify DC/AC sizing output
2. **Input Set B**: 75 MW, 300 MWh → verify guarantee year logic
3. **Input Set C**: 50 MW, 200 MWh → verify scaling consistency

### Comparison
- Master branch (baseline)
- refactor/streamlit-structure-v1 (target)
- Current ops branch (in-progress)

### Validation
- Sizing outputs within 0.1% tolerance
- Efficiency chain matches product of components
- File naming and report structure consistent

## Phase 5: Testing & Validation

### Unit Tests
- Test `_aggregate_ac_block_configs()` with various block counts
- Test `_validate_efficiency_chain()` with correct and incorrect data
- Test report file naming with various project names

### Integration Tests
- Run full sizing flow (DC → AC → Export)
- Verify report contains all expected tables and figures
- Verify SLD/Layout embed correctly in DOCX

### Manual Tests
- Export a report and verify file naming
- Check Executive Summary for data consistency
- Verify AC block table shows aggregated counts
- Verify efficiency chain table includes "No Auxiliary" note

## Phase 6: Documentation

### Update Files
- `docs/REPORTING_AND_DIAGRAMS.md` - How to generate and export
- `docs/N1_RUNBOOK.md` - Troubleshooting and operation
- `REPORT_FIX_SUMMARY.md` - Detailed change log

## Timeline & Deliverables

| Phase | Task | Status |
|-------|------|--------|
| 1 | Audit & Assessment | IN PROGRESS |
| 2 | Data Flow Mapping | PENDING |
| 3.1-3.7 | Code Fixes | PENDING |
| 4 | Regression Testing | PENDING |
| 5 | Testing & Validation | PENDING |
| 6 | Documentation | PENDING |

## Success Criteria

✅ Report exports with correct data sources
✅ AC block table aggregates identical configurations
✅ Efficiency chain includes "No Auxiliary" disclaimer
✅ SLD shows independent DC BUSBAR per PCS
✅ Layout shows 1x6 DC block interior
✅ File naming follows standard: `CALB_<ProjectName>_BESS_Proposal_<YYYYMMDD>_V2.1.docx`
✅ All session_state widget key issues resolved
✅ Regression tests pass (sizing output consistency)
✅ 2000 kW PCS option visible and selectable in UI
✅ Custom PCS input field available

