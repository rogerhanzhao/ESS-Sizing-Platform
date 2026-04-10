# AC Sizing & Report Implementation - Quick Reference

## What Was Fixed

### AC Sizing Page Issues
1. **Label Correction**: "DC:AC Ratio" → "AC:DC Ratio" (clearer semantics)
2. **Container Size Logic**: Now based on single AC block power (>5 MW = 40ft)
3. **Power Overhead Warning**: Now compared against total POI requirement, not single AC block
4. **Type Safety**: Fixed Streamlit metric errors when displaying PCS counts and DC blocks

### Report Generation Enhancements
1. **Added Efficiency Chain Table**: Shows component-level efficiency breakdown
   - Total Efficiency (one-way)
   - DC Cables (default 97%)
   - PCS (default 97%)
   - Transformer (default 98.5%)
   - RMU / Switchgear / AC Cables (default 98%)
   - HVT / Others (default 98%)

## Key Architecture Points

### PCS Configuration Independence
- PCS count (2 or 4 per block) is **independent** of DC:AC ratio
- All combinations available: 2×{1250, 1500, 1725, 2500} and 4×{1250, 1500, 1725, 2500}
- Ratio selection only affects DC block allocation strategy, not PCS options

### Container Size Rules
| Single Block Power | Container | Example |
|-------------------|-----------|---------|
| ≤ 5 MW | 20ft | 2×2500kW = 5.0 MW |
| > 5 MW | 40ft | 4×1500kW = 6.0 MW |

### AC:DC Ratio Options
| Ratio | AC Blocks | DC Allocation | Use Case |
|-------|-----------|---|----------|
| 1:1 | Same as DC count | 1 DC/AC | Max flexibility (small systems) |
| 1:2 | Half of DC count | 2 DC/AC | Balanced (recommended) |
| 1:4 | Quarter of DC count | 4 DC/AC | Consolidated (large systems) |

## Data Flow in Report

```
DC Sizing Results
    ↓
  Stage 1: Energy Requirement (POI → DC capacity)
    ├─ Efficiency Chain Components
    ├─ SC Loss, DoD, DC RTE parameters
    └─ DC Energy/Power Required
    ↓
  Stage 2: DC Configuration (block selection & oversize)
    ├─ Block config table
    ├─ Total DC nameplate @BOL
    └─ Oversize margin
    ↓
  Stage 3: Degradation & Deliverable at POI (lifetime analysis)
    ├─ POI Usable Energy vs Year chart
    ├─ SOH and RTE tracking
    └─ Guarantee year validation
    ↓
  AC Sizing Results
    └─ Stage 4: AC Block Sizing (PCS config & capacity)
```

## Report Sections in V2.1

1. **Cover Page**: Project name and date
2. **Executive Summary**: Key metrics (POI, DC blocks, AC blocks, PCS modules)
3. **Inputs & Assumptions**: Site/POI parameters, grid voltage, PF
4. **Stage 1: Energy Requirement**
   - Energy calculation formula
   - **NEW: Efficiency Chain (one-way) breakdown**
   - DC energy/power required
5. **Stage 2: DC Configuration**
   - Block config table
   - DC total nameplate and oversize margin
6. **Stage 3: Degradation & Deliverable at POI**
   - RTE and SOH degradation
   - Lifetime POI usable energy vs year chart
   - Guarantee year validation
7. **Stage 4: AC Block Sizing**
   - AC ratio selection
   - PCS per block configuration
   - Transformer and MV equipment specs
8. **SLD & Layout Diagrams** (if generated)

## Validation Rules

### Power Validation
- ✅ Total AC power ≥ 95% of POI requirement
- ⚠️ Power overhead ≤ 30% of POI requirement (warning if exceeded)

### Energy Validation
- ✅ Total DC energy ≥ 95% of POI energy requirement
- ⚠️ Excess energy ≥ 105% of POI requirement (warning)

## Testing the Implementation

### Quick Test: AC Sizing Page
1. Go to DC Sizing → enter 100 MW POI, 400 MWh requirement
2. Complete DC sizing (should result in ~92 DC blocks)
3. Go to AC Sizing
4. Verify label shows "AC:DC Ratio"
5. Select 1:2 ratio
6. Choose "4 × 1500kW = 6000kW" configuration
7. Verify: Container shows "40ft" (single block 6 MW > 5 MW)
8. Power overhead should show ~8% (8 MW / 100 MW), not 300%

### Quick Test: Report Export
1. Complete AC Sizing
2. Go to Report Export → Download Combined Report V2.1
3. Open DOCX file
4. Verify in Stage 1 section: "Efficiency Chain (one-way)" table present
5. Check all 5 components listed with percentages
6. Verify total efficiency ~96.74% (product of components)

## Common Issues & Fixes

### Issue: "TypeError: '...' is of type <class 'list'>, which is not an accepted type"
**Cause**: st.metric() receiving list instead of scalar  
**Fix**: Type checking converts lists to sum or TBD string (already implemented)

### Issue: Container shows "20ft" when AC block > 5 MW
**Cause**: Total project AC power being checked instead of single block  
**Fix**: Now checks single block power threshold (already implemented)

### Issue: Efficiency table missing in report
**Cause**: Efficiency components extracted but not displayed  
**Fix**: Added Efficiency Chain section after Stage 1 (already implemented)

## Next Steps (Future Work)

- [ ] Implement 6-module layout for DC Block containers
- [ ] Add independent DC BUSBAR per PCS in SLD
- [ ] Full Stage 3 degradation curve visualization
- [ ] Add consistency validation between report stages
- [ ] Remove V1 deprecated functions (create_combined_report, etc.)
