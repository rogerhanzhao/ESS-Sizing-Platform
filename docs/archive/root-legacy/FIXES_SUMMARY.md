# SLD and Layout Rendering Fixes - Summary

## Overview
Fixed critical issues with Single Line Diagram (SLD) and Layout rendering to ensure:
1. **SLD electrical independence**: Each PCS has completely independent DC BUSBAR (A & B) with independent DC Block connections
2. **Layout visual clarity**: DC Block internal layout shows 6 modules in a single row (1×6) without door indicators or cooling labels

## Issues Fixed

### Issue 1: SLD DC BUSBAR Coupling
**Problem**: DC BUSBARs from different PCS units appeared to share connections or couple together, creating an incorrect electrical topology where DC Blocks were allocated but visually appeared to be in parallel/shared configuration.

**Root Cause**: 
- Line 514-557 in `sld_pro_renderer.py` had DC block connection logic that used shared circuit traces (Circuit A/B) for multiple PCS
- The `circuit_x1`/`circuit_x2` variables defined global circuit lines that all DC blocks connected to, creating the illusion of coupling

**Solution**:
- Modified DC block connection logic (lines 514-557) to connect each block directly and independently to its assigned PCS's DC BUSBAR A or B
- Each PCS now has its own dedicated DC BUSBAR A and B (lines 476-500)
- DC blocks connect only to their assigned PCS, with separate connection lines for each circuit
- Each connection from a DC block goes directly up to the PCS's independent BUSBAR, not through shared circuit traces

**Verification**:
- SLD now contains exactly 4 independent BUSBAR A segments and 4 independent BUSBAR B segments (for 4 PCS)
- Each BUSBAR segment has a distinct x-coordinate range (no overlap)
- 8 independent BUSBAR segments total = 4 PCS × 2 BUSBARs per PCS

### Issue 2: DC Block Interior Layout - 2×3 to 1×6
**Problem**: DC Block internal layout was a 2×3 grid (2 columns × 3 rows) with a door indicator on the left side and cooling labels, which didn't match the required 1×6 single-row layout.

**Root Cause**:
- `_draw_dc_interior()` function (lines 115-156) and `_draw_dc_interior_raw()` (lines 272-313) used hardcoded 2-column, 3-row layout
- Included a door rectangle and handle line
- Had "COOLING" and "LIQUID" text elements

**Solution**:
- Changed grid layout from 2 columns × 3 rows to 6 columns × 1 row (single row)
- Removed door indicator rectangle and handle line
- Removed any cooling-related text labels
- Simplified module sizing calculations to work with single-row layout

**Files Modified**:
1. `calb_diagrams/layout_block_renderer.py`:
   - `_draw_dc_interior()` (lines 115-144): Changed `cols = 6, rows = 1`, removed door drawing
   - `_draw_dc_interior_raw()` (lines 272-298): Same changes for raw SVG path

2. `calb_diagrams/sld_pro_renderer.py`:
   - Lines 476-500: Rewrote DC BUSBAR drawing to create independent BUSBAR A/B for each PCS
   - Lines 514-557: Rewrote DC block connection logic to connect each block independently to its assigned PCS's BUSBAR

## Testing

All tests pass:
- ✓ SLD Independent BUSBARS: 4 PCS with 4 separate BUSBAR A/B pairs each
- ✓ Layout 1×6 Interior: 6 module rectangles per DC Block, no door/cooling elements
- ✓ Scaling Test: Configurations with 2, 4, and 8 PCS/Blocks render correctly

### Test Command:
```bash
cd /opt/calb/prod/CALB_SIZINGTOOL && .venv/bin/python /tmp/comprehensive_test.py
```

## Electrical Correctness

The fixes ensure that:
1. **DC-side topology is electrically correct**: Each PCS module has its own two independent DC BUSBARs (A and B) that receive power from DC Blocks allocated to that specific PCS
2. **No coupling**: DC circuits from different PCS units do not share any conductor or appear coupled
3. **Visual representation matches electrical schematic**: The SLD now correctly shows each PCS with dedicated BUSBARs and independent connections

## Physical Layout Correctness

The Layout diagram now correctly shows:
1. **DC Block interior**: 6 battery module racks arranged in a single row (1×6)
2. **Clean design**: No door indicators, no cooling system labels
3. **Professional appearance**: Matches the reference design specifications

## Backward Compatibility

These changes are **display/rendering only** and do not affect:
- Any sizing calculations or algorithms
- AC/DC configuration results
- Session state structure
- Data flow or business logic
- Report generation (only the SVG drawing changes)

The fixes are purely cosmetic/display-layer improvements to correct the graphical representation.

## Files Changed

1. `/opt/calb/prod/CALB_SIZINGTOOL/calb_diagrams/sld_pro_renderer.py`
   - Lines 476-500: Independent DC BUSBAR drawing
   - Lines 514-557: Independent DC block connection logic
   - Line 559: Updated allocation note

2. `/opt/calb/prod/CALB_SIZINGTOOL/calb_diagrams/layout_block_renderer.py`
   - Lines 115-144: `_draw_dc_interior()` - 1×6 layout
   - Lines 272-298: `_draw_dc_interior_raw()` - 1×6 layout

Total lines changed: ~30 lines across 2 files
