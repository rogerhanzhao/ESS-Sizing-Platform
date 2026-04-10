# Report Export Fix Implementation Plan

## Issues to Fix

### A. Efficiency Chain (ONE-WAY) ISSUE
**Current Problem:**
- Report may show efficiency components that don't align with DC SIZING stage1 output
- Missing disclaimer that efficiency values exclude Auxiliary losses
- Derived fields (DC Power Required, etc.) may be computed from wrong efficiency sources

**Solution:**
1. Use ONLY DC SIZING stage1 output (`ctx.stage1`) as source of truth:
   - `eff_dc_cables_frac` ← `stage1.get("eff_dc_cables_frac")`
   - `eff_pcs_frac` ← `stage1.get("eff_pcs_frac")`
   - `eff_mvt_frac` ← `stage1.get("eff_mvt_frac")`
   - `eff_ac_cables_sw_rmu_frac` ← `stage1.get("eff_ac_cables_sw_rmu_frac")`
   - `eff_hvt_others_frac` ← `stage1.get("eff_hvt_others_frac")`
   - `eff_chain_oneway_frac` ← `stage1.get("eff_dc_to_poi_frac")`

2. Add validation that Total = Product(components) or match DC SIZING (with tolerance)
3. Add explicit disclaimer paragraph in report: "Efficiency chain values do not include Auxiliary losses."

### B. AC Sizing Configuration - Deduplication & Aggregation
**Current Problem:**
- May output each AC Block configuration separately if identical
- Doesn't aggregate by "configuration signature"
- Creates verbose, repetitive tables

**Solution:**
1. Implement `_aggregate_ac_block_configs()` to group identical AC Block configs
2. Output single summary row: "Config signature | Count"
3. Only list exception rows if configurations differ
4. Keep implementation in `report_v2.py` (already started in code)

### C. SLD Electrical Topology
**Current Problem:**
- DC BUSBARs from different PCS may appear connected/shared in diagram
- Violates electrical independence requirement

**Solution:**
- This is a DIAGRAM RENDERING issue, NOT a report data issue
- Modify SLD renderer to draw independent DC BUSBAR for each PCS
- Ensure PCS-1, PCS-2, etc. show SEPARATE DC connection paths (no parallel return to common busbar)

### D. Layout DC Block Internal Structure
**Current Problem:**
- 2×3 grid of battery modules inside DC Block (should be 1×6)
- Left-side "small box" should be removed

**Solution:**
- Modify layout renderer to draw 6 modules in single row (1×6)
- Remove left-side element

## Modules to Modify

### report_context.py
- ✓ Already correct (uses `stage1` as source)
- Ensure efficiency_chain_oneway_frac comes from stage1["eff_dc_to_poi_frac"]

### report_v2.py
**Functions to update:**
1. `_validate_efficiency_chain()` → enhance validation
2. `_aggregate_ac_block_configs()` → already started, needs completion
3. `export_report_v2_1()` → ensure efficiency disclaimer included

**Key Changes:**
- Add efficiency disclaimer paragraph
- Use aggregated AC Block config instead of verbose listing
- Ensure all efficiency values come from ctx.stage1

### SLD Renderer (e.g., sld_pro_renderer.py)
- Draw independent DC BUSBAR per PCS
- Allocate DC Blocks to specific PCS independently
- No shared DC return path between PCS units

### Layout Renderer (e.g., layout_block_renderer.py)
- Change DC Block internal module grid from 2×3 to 1×6
- Remove left-side small box element

## Files Modified

1. `/opt/calb/prod/CALB_SIZINGTOOL/calb_sizing_tool/reporting/report_v2.py` - MAIN
2. `/opt/calb/prod/CALB_SIZINGTOOL/calb_sizing_tool/reporting/report_context.py` - VALIDATION
3. `/opt/calb/prod/CALB_SIZINGTOOL/calb_diagrams/sld_pro_renderer.py` - SLD TOPOLOGY
4. `/opt/calb/prod/CALB_SIZINGTOOL/calb_diagrams/layout_block_renderer.py` - LAYOUT DC BLOCK

## Testing Strategy

1. **Efficiency Chain Validation Test**
   - Verify ctx.efficiency_chain_oneway_frac matches stage1["eff_dc_to_poi_frac"]
   - Verify all components present in ctx.efficiency_components_frac
   - Check report contains "do not include Auxiliary losses"

2. **AC Block Aggregation Test**
   - Count rows in AC configuration section
   - Verify no duplicate identical configs
   - Verify "Block Count" or similar appears if present

3. **SLD Topology Test**
   - Parse SLD SVG/PNG output
   - Verify distinct DC BUSBAR per PCS (no shared wires)
   - Check PCS labels are separate

4. **Layout Test**
   - Parse layout PNG
   - Count module boxes inside DC Block (should be 6)
   - Verify no left-side element

5. **Smoke Test**
   - Export complete report with sample sizing data
   - Verify no crashes, all sections present
   - Check file format is valid DOCX

## Non-Breaking Guarantees

- ✓ No changes to file name/location/format (still DOCX)
- ✓ No changes to export entry point signature
- ✓ No changes to sizing calculation logic
- ✓ No removal of already-confirmed user details
- ✓ No "Auxiliary" assumptions added to report
- ✓ Existing chapter structure/titles preserved
- ✓ All numeric results unchanged (only text/layout/deduplication fixed)
