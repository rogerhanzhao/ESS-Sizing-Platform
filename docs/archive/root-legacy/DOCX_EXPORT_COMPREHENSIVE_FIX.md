# DOCX Export Comprehensive Fix Plan

## Issues Identified

### A. Efficiency Chain Data Source Mismatch
**Problem**: The Efficiency Chain table in the exported report shows values that do not match the DC SIZING page output. Values like "97.00%" vs "0.00%" appear, indicating wrong data sources.

**Root Cause**: 
- Report may be reading from wrong dict keys or fallback defaults
- DC SIZING page stores efficiencies in specific stage1 output keys
- Report generation may not be using the same source

**Solution**:
- Verify all efficiency components come from `ctx.stage1` (DC SIZING output)
- Use exact key names that DC SIZING page writes: `eff_dc_cables_frac`, `eff_pcs_frac`, `eff_mvt_frac`, `eff_ac_cables_sw_rmu_frac`, `eff_hvt_others_frac`
- Add validation to ensure Total efficiency matches product of components (with tolerance)
- Add clear note: "Efficiency chain values do not include Auxiliary losses"

### B. AC Sizing Configuration Display Issue
**Problem**: Report shows multiple identical AC Block configurations as separate entries instead of aggregating them.

**Example**: 
- Should show: "23 AC Blocks: 2 × 2500 kW"
- Currently shows: 23 separate rows with identical config

**Root Cause**: 
- Report code iterates through all blocks and displays each one
- No aggregation logic by configuration signature

**Solution**:
- Implement `_aggregate_ac_block_configs()` function
- Group blocks by: PCS count, PCS rating (kW), AC Block power (MW), Transformer rating
- Output summary like: `"23 AC Blocks, all with 2 PCS @ 2500 kW each = 5.00 MW per block"`
- No detailed per-block table in report (only aggregated summary)

### C. SLD/Layout Diagram Issues
**Problem 1**: DC BUSBAR appears to be shared/parallel between PCS units instead of independent per-PCS
**Problem 2**: DC Block internal layout shows 2×3 instead of required 1×6 single row
**Problem 3**: DC Block left-side "small box" should be removed

**Solution**:
- In SLD renderer: Ensure each PCS has completely independent DC BUSBAR (no visual parallel connection to shared bus)
- In Layout renderer: Change DC Block internal battery representation to 1×6 single row, remove left-side box
- Note: Do NOT change sizing logic or DC Block allocation logic - only change drawing representation

### D. Report Consistency Validation
**Problem**: Report may contain inconsistencies (e.g., power values that don't add up, efficiency values > 100%)

**Solution**:
- Add `_validate_report_consistency()` function
- Check: Total AC Power = AC Blocks × AC Power per Block
- Check: Efficiency values are 0-100% (or 0-1.2 for fractions)
- Check: DC/AC block counts are consistent
- Log warnings for manual review (do not block export, but flag issues)

## Implementation Steps

### 1. Fix Efficiency Chain Data Source (CRITICAL)
- File: `calb_sizing_tool/reporting/report_v2.py`
- Function: `export_report_v2_1()` - Efficiency Chain section (lines ~430-444)
- Verify data comes from `ctx.stage1` via `ctx.efficiency_components_frac` dict
- Add validation function `_validate_efficiency_chain()` to check consistency
- Ensure all 5 components + total are present and self-consistent

### 2. Fix AC Sizing Display (HIGH PRIORITY)
- File: `calb_sizing_tool/reporting/report_v2.py`
- Function: `_aggregate_ac_block_configs()` - already exists, verify usage
- Function: Stage 4 AC Block Sizing section (lines ~565-631)
- Change from per-block detailed list to aggregated summary
- Remove any "per-block" configuration table
- Show only: "N AC Blocks, each with M PCS @ K kW, = L MW per block, Total P MW"

### 3. Fix SLD DC BUSBAR Independence (DIAGRAM LAYER)
- File: `calb_diagrams/sld_pro_renderer.py`
- Ensure DC BUSBAR drawing logic creates independent buses per PCS
- Do NOT connect multiple PCS DC BUSBARs to same visual node
- Each PCS should have visually separated DC BUSBAR entry points

### 4. Fix Layout DC Block Internal Layout (DIAGRAM LAYER)
- File: `calb_diagrams/layout_block_renderer.py`
- Change DC Block battery representation from 2×3 grid to 1×6 single row
- Remove left-side "small box" element
- Keep all other layout features (dimensions, labels, spacing)

### 5. Add Report Validation & QC Checks
- File: `calb_sizing_tool/reporting/report_v2.py`
- Function: `_validate_efficiency_chain()` - verify all components present and consistent
- Function: `_validate_report_consistency()` - check overall report data integrity
- Add these to QC/Warnings section at end of report

## Data Source Verification

### DC SIZING Page Output Keys (stage1/stage13_output)
```python
"eff_dc_cables_frac": float         # e.g., 0.97
"eff_pcs_frac": float              # e.g., 0.97
"eff_mvt_frac": float              # e.g., 0.985
"eff_ac_cables_sw_rmu_frac": float # e.g., 0.98
"eff_hvt_others_frac": float       # e.g., 0.98
"eff_dc_to_poi_frac": float        # Total one-way = product of above
```

### Report Context Mapping
```python
# From report_context.py build_report_context():
eff_chain = float(stage1.get("eff_dc_to_poi_frac", 0.0) or 0.0)

efficiency_components = {
    "eff_dc_cables_frac": eff_dc_cables,
    "eff_pcs_frac": eff_pcs,
    "eff_mvt_frac": eff_mvt,
    "eff_ac_cables_sw_rmu_frac": eff_ac_cables_sw_rmu,
    "eff_hvt_others_frac": eff_hvt_others,
}
```

### What MUST NOT Change
1. sizing calculation logic (Stages 1-4)
2. File export format/naming (still DOCX, same naming convention)
3. User-confirmed configuration values
4. DC/AC block allocation algorithm
5. Report chapter structure (same headings/sections)

## Acceptance Criteria

- [ ] Efficiency Chain table in exported report uses DC SIZING page values exactly
- [ ] Total efficiency matches product of components (within 1% tolerance)
- [ ] AC Sizing shows aggregated summary (not per-block list)
- [ ] SLD shows independent DC BUSBAR per PCS (no visual parallel connection)
- [ ] Layout DC Block shows 1×6 battery layout (not 2×3) and no left-side box
- [ ] Report validation function flags (but does not block) inconsistencies
- [ ] All 5 efficiency components are shown in table (not missing any)
- [ ] Report still exports as DOCX with same file naming
- [ ] Sizing calculation logic unchanged (confirmed by running DC/AC sizing)
- [ ] Unit consistency maintained throughout report (MW/MWh/kW/kWh/%)
