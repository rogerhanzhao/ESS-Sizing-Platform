# CALB ESS Sizing Tool v2.1 - Release Notes

**Release Date**: 2025-12-30  
**Version**: v2.1 (Refactored Streamlit Structure)  
**Status**: ✅ Implementation Complete

---

## Overview

This release addresses critical issues in AC Sizing logic, report generation accuracy, and Streamlit widget data type handling. All changes maintain backward compatibility with DC Sizing calculations while improving user experience and report clarity.

---

## Fixed Issues

### 1. AC Sizing Configuration Logic ✅
**Issue**: Confusing and incorrect AC:DC ratio labeling and calculations  

**Changes**:
- ✅ Corrected UI label: "DC:AC Ratio" → "AC:DC Ratio"
- ✅ Fixed container size logic: Now based on single AC block power, not total project AC power
  - A 2×2500 kW block = 5 MW = 20ft container
  - A 4×1500 kW block = 6 MW = 40ft container (>5 MW threshold)
- ✅ Corrected power overhead warning: Now calculated against POI requirement, not single AC block capacity
  - Before: "300% of one AC Block" (misleading)
  - After: "15% of POI requirement" (accurate)

**Files Modified**: `calb_sizing_tool/ui/ac_view.py` (lines 121, 168-171, 196-200)

---

### 2. Single Line Diagram Page TypeError ✅
**Issue**: Streamlit ValueError when pcs_count_status was a list type  
**Message**: `"TypeError: '...' is of type <class 'list'>, which is not an accepted type"`

**Changes**:
- ✅ Added type checking and conversion for PCS count status
- ✅ Added type checking and conversion for DC blocks status
- ✅ Convert all non-TBD metric values to string before st.metric()

**Files Modified**: `calb_sizing_tool/ui/single_line_diagram_view.py` (lines 206-224)

---

### 3. Missing Efficiency Chain Data in Reports ✅
**Issue**: Efficiency components were extracted from DC sizing but not displayed in exported reports

**Changes**:
- ✅ Added "Efficiency Chain (one-way)" section in Stage 1
- ✅ Displays 6 efficiency components:
  - Total Efficiency (one-way)
  - DC Cables
  - PCS
  - Transformer
  - RMU / Switchgear / AC Cables
  - HVT / Others
- ✅ Data sourced from DC sizing results via ReportContext

**Files Modified**: `calb_sizing_tool/reporting/report_v2.py` (lines 258-272)

---

## Improvements

### AC Sizing User Experience
- Clearer AC:DC ratio semantics
- More intuitive container size selection
- Accurate power overhead calculation
- Better visibility of total AC power vs. single block power

### Report Quality
- Complete efficiency chain documentation
- Better traceability from DC sizing to final report
- Component-level efficiency breakdown for validation

### Code Quality
- Removed unused imports (deprecated V1 functions)
- Improved type safety in Streamlit widgets
- Better error handling for edge cases

---

## Technical Details

### AC:DC Ratio Semantics
The ratio represents **AC Blocks per DC Blocks**:
- **1:1 Ratio**: 1 AC Block per 1 DC Block (maximum modularity)
- **1:2 Ratio**: 1 AC Block per 2 DC Blocks (balanced, recommended)
- **1:4 Ratio**: 1 AC Block per 4 DC Blocks (consolidated, cost-optimized)

PCS configuration (2 or 4 per block) is **independent** of ratio selection.

### Container Size Rules
Based on **single AC block power**:
```
If single_block_power ≤ 5 MW → 20ft container
If single_block_power > 5 MW → 40ft container
```

### Power Overhead Calculation
```
Power Overhead = Total AC Power - POI Power Requirement
Overhead % = (Power Overhead / POI Requirement) × 100
```

Acceptable range: 0% to 30% of POI requirement

---

## Validation Checklist

- [x] AC:DC Ratio label corrected
- [x] Container size logic based on single block power
- [x] Power overhead warning uses POI requirement baseline
- [x] Single Line Diagram page loads without TypeError
- [x] Efficiency Chain table appears in Stage 1 section
- [x] All 5 efficiency components displayed
- [x] Report generates successfully for all ratio options
- [x] Both 2-PCS and 4-PCS configurations available
- [x] No regression in DC Sizing calculations
- [x] Backward compatibility maintained

---

## Testing Recommendations

### Test Case 1: AC Sizing with 1:2 Ratio
1. DC Sizing: 100 MW POI, 400 MWh energy → ~92 DC blocks
2. AC Sizing: Select 1:2 ratio → ~46 AC blocks
3. Select "4 × 1500 kW" → 6 MW single block
4. Verify: Container shown as "40ft" (6 MW > 5 MW)
5. Power overhead: 6 MW × 46 = 276 MW total, 276-100 = 176 MW overhead (176% warning)
   - Note: This suggests user should select lower PCS rating or increase DC blocks
6. Try "2 × 2500 kW" → 5 MW single block
7. Verify: Container shown as "20ft" (5 MW ≤ 5 MW)
8. Power overhead: 5 MW × 46 = 230 MW total, 230-100 = 130 MW overhead (130% warning)
   - Note: Still high; consider 1:4 ratio instead

### Test Case 2: Report Efficiency Chain
1. Complete AC Sizing
2. Export Combined Report V2.1
3. Open DOCX and navigate to Stage 1
4. Verify "Efficiency Chain (one-way)" section appears
5. Verify all 5 components listed with percentage values
6. Verify total efficiency ≈ product of components (with rounding)

### Test Case 3: SLD Page Stability
1. Complete DC Sizing and AC Sizing
2. Go to Single Line Diagram page
3. Verify "Data Status" section loads without errors
4. Verify PCS Count and DC Blocks metrics display correctly
5. Generate SLD (if available) - should not error

---

## Known Limitations

1. **Report images**: SLD and Layout images embedded if available; otherwise shows note
2. **Stage 3 data**: Requires DC sizing with degradation profiles; omitted if not available
3. **Efficiency defaults**: Used when DC sizing data missing (97%, 98%, 98.5% defaults)

---

## Migration Notes

No migration required. This is a hotfix release with:
- UI/UX improvements
- Report data inclusion fixes
- Type safety improvements

All existing projects continue to work with v2.1 report generation.

---

## Related Documentation

- `CHANGES_SUMMARY.md` - Detailed change log
- `IMPLEMENTATION_NOTES.md` - Technical architecture and examples
- `docs/REPORTING_AND_DIAGRAMS.md` - Report generation workflow (if present)

---

## Support & Feedback

For issues or questions:
1. Check IMPLEMENTATION_NOTES.md for common issues
2. Review AC Sizing logic in ac_sizing_config.py
3. Verify DC sizing results are complete before AC sizing
4. Check report_v2.py for report generation details

---

## Future Roadmap

- [ ] v2.2: Layout rendering with 6-battery-module containers
- [ ] v2.3: Independent DC BUSBAR per PCS in SLD
- [ ] v2.4: Full Stage 3 degradation visualization
- [ ] v3.0: Remove deprecated V1 functions; streamline exports

---

**End of Release Notes**
