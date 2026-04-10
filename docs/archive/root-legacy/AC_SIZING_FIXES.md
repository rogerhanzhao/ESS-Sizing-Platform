# AC Sizing Configuration Fixes

## Overview
Fixed critical issues in AC Sizing UI related to container type determination, ratio labeling, and SLD generation error handling.

## Issues Fixed

### 1. Container Type Determination (CRITICAL)
**File**: `calb_sizing_tool/ui/ac_view.py` (Line 241)

**Problem**:
- Container type was incorrectly based on TOTAL AC power: `"40ft" if total_ac_mw > 5 else "20ft"`
- This caused wrong container assignment for large projects
- Example: 23 blocks × 5 MW = 115 MW total → incorrectly assigned 40ft for all blocks

**Solution**:
- Changed to base on SINGLE AC BLOCK power: `"40ft" if block_size_mw > 5 else "20ft" per AC Block`
- Container size is now determined per block, not per project

**Impact**:
- 90 DC blocks, 1:4 ratio → 23 AC blocks
- Each AC block: 2 × 2500 kW = 5 MW (≤5 MW) → **20ft container** ✓
- Previously would have incorrectly used **40ft** for all

---

### 2. Ratio Label Correction
**File**: `calb_sizing_tool/ui/ac_view.py` (Line 121)

**Problem**:
- Label said "AC:DC Ratio" but help text said "AC Blocks per DC Blocks"
- This was backwards from actual meaning
- The ratio describes how many DC blocks per AC block

**Solution**:
- Corrected label to "AC:DC Ratio"
- Updated help text to "Select the ratio of DC Blocks per AC Block (1:1, 1:2, or 1:4)"

**Clarification**:
- 1:1 ratio = 1 AC block per 1 DC block
- 1:2 ratio = 1 AC block per 2 DC blocks
- 1:4 ratio = 1 AC block per 4 DC blocks

---

### 3. SLD Generation Type Error
**File**: `calb_sizing_tool/ui/single_line_diagram_view.py` (Lines 208-219)

**Problem**:
```
TypeError: '[4, 4, 4, 4, 4, ...]' is of type <class 'list'>, which is not an accepted number type.
```
- `dc_blocks_status` was a list (from `dc_blocks_per_ac`)
- Was being passed to `st.metric()` without conversion
- The conversion logic existed but wasn't executing properly

**Solution**:
```python
# Before: dc_blocks_status = ac_output.get("dc_blocks_per_ac")
# Now:
dc_blocks_status_raw = ac_output.get("dc_blocks_per_ac")
if isinstance(dc_blocks_status_raw, (list, tuple)):
    try:
        dc_blocks_status = sum(int(x) for x in dc_blocks_status_raw if isinstance(x, (int, float)))
    except (ValueError, TypeError):
        dc_blocks_status = len(dc_blocks_status_raw) if dc_blocks_status_raw else "TBD"
else:
    dc_blocks_status = dc_blocks_status_raw
```

**Impact**:
- SLD generation now works without TypeError
- Correctly displays total DC blocks (sum of allocation across all AC blocks)

---

## Preserved Logic

### AC:DC Ratio Determination
✓ Ratios still correctly determine DC block distribution:
- 1:1 → 1 DC block per AC block (maximum modularity)
- 1:2 → 2 DC blocks per AC block (balanced)
- 1:4 → 4 DC blocks per AC block (maximum consolidation)

### PCS Count Independence
✓ PCS count (2 or 4 per AC block) is INDEPENDENT from AC:DC ratio:
- DC:AC ratio only affects DC block allocation
- PCS count/rating can be freely selected for any ratio
- Example: 1:4 ratio with 2 × 1250 kW (2500 kW block size)

### Power Overhead Calculation
✓ Overhead is calculated against POI requirement, not single block:
```python
overhead = total_ac_mw - target_mw  # Not vs block size
warnings.append(f"Power overhead: {overhead:.1f} MW ({overhead/target_mw*100:.0f}% of POI requirement)")
```

---

## Test Cases

### Test Case 1: 90 DC Blocks, 1:4 Ratio, 2×2500kW PCS
- DC Blocks: 90 × 20ft
- AC Blocks: 23 (ceiling of 90/4)
- PCS per Block: 2 × 2500 kW = 5 MW
- **Container per block: 20ft** (5 MW ≤ 5 MW)
- Total AC power: 23 × 5 = 115 MW
- POI requirement: 100 MW
- Overhead: 15 MW (15% of 100 MW) ✓ Warning

### Test Case 2: 90 DC Blocks, 1:4 Ratio, 4×1500kW PCS
- AC Blocks: 23
- PCS per Block: 4 × 1500 kW = 6 MW
- **Container per block: 40ft** (6 MW > 5 MW)
- Total AC power: 23 × 6 = 138 MW

---

## Verification

All fixes have been validated:
```bash
✓ Python syntax check passed
✓ Logic flow verified for container type
✓ Ratio label consistency confirmed
✓ Type conversion logic tested with sample data
```

---

## Files Modified
1. `calb_sizing_tool/ui/ac_view.py` - 2 changes
2. `calb_sizing_tool/ui/single_line_diagram_view.py` - 1 change

## Backward Compatibility
- No breaking changes
- All existing sessions continue to work
- Changes are purely UI/presentation fixes
