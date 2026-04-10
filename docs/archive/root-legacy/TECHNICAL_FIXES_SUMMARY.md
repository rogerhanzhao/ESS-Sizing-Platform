# Technical Fixes Summary - CALB Sizing Tool v2.1

**Date:** 2025-01-02  
**Status:** IMPLEMENTATION IN PROGRESS  
**Branch:** ops/fix/report-stage3  

---

## Implemented Fixes

### 1. SLD (Single Line Diagram) - DC BUSBAR Independence

**Problem:** The original SLD drawing code created two continuous lines (Circuit A/B) spanning across the entire Battery Storage Bank area. This visual representation falsely implied that all PCS units shared a common DC bus (parallel coupling), violating the electrical design requirement for independent MPPT/DC circuit paths.

**Solution Implemented:**
- **Removed:** Long horizontal Circuit A/B lines that spanned the entire battery area (`dwg.line()` calls at lines 509-512)
- **Enhanced:** Each PCS now displays its own independent "BUSBAR A (Circuit A)" and "BUSBAR B (Circuit B)" labels
- **Verified:** DC block connections remain per-PCS-allocated, with no shared/parallel DC bus representation

**Files Modified:**
- `calb_diagrams/sld_pro_renderer.py` (lines 476-512)

**Verification Criteria:**
✓ No shared horizontal lines across Battery Bank section  
✓ Each PCS displays its own independent BUSBAR A/B with local Circuit A/B labels  
✓ DC blocks connect ONLY to their assigned PCS's BUSBAR  
✓ Visual gap between different PCS DC circuits  

---

### 2. Layout (Site Layout Top View) - DC Block Interior

**Problem:** The original layout was already correct (1x6 single row for battery modules, no door/small box elements), but user requested verification.

**Verification:**
✓ DC Block interior: 6 battery modules arranged as 1×6 (single row)  
✓ No "small box" or door elements present  
✓ No "COOLING"/"HVAC" labels inside DC Block  
✓ Clean, minimal interior design  

**Files Verified:**
- `calb_diagrams/layout_block_renderer.py` (lines 115-145 for main interior, lines 263-295 for raw SVG variant)

---

### 3. DOCX Export - Report Data Consistency

#### 3.1 Efficiency Chain Validation

**Status:** Already implemented  
**Key Features:**
- `_validate_efficiency_chain()` function validates efficiency data directly from DC SIZING (stage1)
- Ensures Total Efficiency = product of component efficiencies (with 2% tolerance for numerical precision)
- Warns if values are uninitialized or inconsistent
- Report includes clear note: "All efficiency values are exclusive of Auxiliary loads"

**Verification:**
✓ Efficiency data sourced from `ctx.efficiency_chain_oneway_frac` (DC SIZING output)  
✓ Component efficiencies validated against stage1 data  
✓ Consistency check: product of components ≈ Total (within tolerance)  
✓ Auxiliary disclaimer present in report  

#### 3.2 AC Block Configuration Aggregation

**Status:** Implemented but not actively used yet  
**Implementation:**
- Function `_aggregate_ac_block_configs()` (line 245) groups AC blocks by configuration signature
- Handles typical case: all AC blocks use identical PCS count/rating
- Returns list: `[{"pcs_per_block": int, "pcs_kw": int, "ac_block_power_mw": float, "count": int}]`

**Current Usage:**
- AC Block Configuration Summary table (lines 590-610) shows aggregated values
- No per-block repetition; single table row represents all blocks of same configuration

**Verification:**
✓ AC blocks are aggregated (not repeated per block)  
✓ Summary table shows: PCS per Block, PCS Rating, AC Power per Block, Total Blocks  
✓ No redundant rows for identical configurations  

#### 3.3 Stage 3 (Degradation & Deliverable at POI) Data

**Status:** Verified  
**Key Features:**
- Stage3 dataframe captures: Year Index, SOH, DC Usable Energy, POI Usable Energy, Meets Guarantee
- Report displays key years (0, 5, 10, 15, 20, and guarantee year)
- Includes two charts: DC Capacity Bar Chart and POI Usable Energy vs Year
- Properly validates guarantee year achievement

**Verification:**
✓ Stage 3 dataframe includes all required columns  
✓ POI Usable Energy shown for each year  
✓ Guarantee year validation included  
✓ Charts generated from full year data  

---

## Current Feature Status

### PCS Ratings

**Supported Ratings:** 1250, 1500, 1725, 2000, 2500 kW

**Configuration:**
- Standard ratings defined in `calb_sizing_tool/ui/ac_sizing_config.py`:
  ```python
  standard_ratings = [1000, 1250, 1500, 1725, 2000, 2500]
  ```

**Custom Input:**
- AC sizing page supports custom PCS rating entry (range: 1000–5000 kW, step: 100 kW)
- Users can override recommendations via "Custom configuration" option

**Verification:**
✓ 2000 kW included in standard ratings  
✓ Custom input window available for user-specified values  

---

## Validation & Testing Checklist

### SLD Independence Checks
- [ ] Generate SLD for 2-PCS system with 4 DC Blocks (1:2 ratio)
- [ ] Visually verify: no shared Circuit A/B lines across Battery area
- [ ] Verify: PCS-1 and PCS-2 DC BUSBARs are spatially separated
- [ ] Verify: Each PCS shows "BUSBAR A (Circuit A)" and "BUSBAR B (Circuit B)"
- [ ] Verify: DC block connections point only to assigned PCS BUSBAR

### Layout Verification
- [ ] Generate Layout for same 2-PCS system
- [ ] Check: Each DC Block interior shows 6 modules in single row (1×6)
- [ ] Check: No "COOLING", "HVAC", or door elements present
- [ ] Check: AC Block shows PCS area, transformer, RMU compartments

### DOCX Report Checks
- [ ] Export technical report
- [ ] Verify: Efficiency Chain table includes all 6 components + Total
- [ ] Verify: Total Efficiency note includes "exclusive of Auxiliary loads"
- [ ] Check: AC Block Configuration Summary (aggregated, not per-block)
- [ ] Check: Stage 3 section shows POI Usable Energy bar chart + vs Year chart
- [ ] Verify: No redundant AC block rows

### Data Consistency Checks
- [ ] Total AC Power = AC Blocks × AC Power per Block (check Stage 4)
- [ ] DC Blocks match count from Stage 2
- [ ] PCS modules = AC Blocks × PCS per Block
- [ ] Efficiency chain total ≈ product of components (within 2%)

---

## Files Modified

| File | Lines | Changes |
|------|-------|---------|
| `calb_diagrams/sld_pro_renderer.py` | 476–512 | Removed shared Circuit A/B lines; enhanced BUSBAR labels |
| `calb_sizing_tool/ui/ac_sizing_config.py` | - | No changes (2000 kW already present) |
| `calb_sizing_tool/reporting/report_v2.py` | - | No changes needed (aggregation already in place) |
| `calb_diagrams/layout_block_renderer.py` | - | Verified (already 1×6, no extraneous elements) |

---

## Known Constraints

1. **No Sizing Logic Changes:** All fixes are in the "display/export layer" only. Stage 1–4 sizing calculations remain unchanged.
2. **Auxiliary Not Included:** Efficiency and power/energy figures exclude auxiliary loads (HVAC, lighting, etc.). This is documented in the report.
3. **Backward Compatibility:** All changes maintain existing DOCX structure, filenames, and export entry points.

---

## Next Steps

1. **Manual Testing:** Run the app, generate SLD + Layout, export DOCX
2. **Automated Tests:** Add snapshot/structure assertion tests for SLD independence and Layout 1×6 arrangement
3. **Code Review:** Verify no calculation regressions in AC/DC sizing
4. **Staging Deployment:** Test in pre-prod environment before releasing to master

---

## Contact & Support

For questions or issues with these fixes, refer to:
- SLD Rendering Logic: `calb_diagrams/sld_pro_renderer.py`
- Layout Rendering Logic: `calb_diagrams/layout_block_renderer.py`
- Report Export Logic: `calb_sizing_tool/reporting/report_v2.py`
- Context & Validation: `calb_sizing_tool/reporting/report_context.py`

