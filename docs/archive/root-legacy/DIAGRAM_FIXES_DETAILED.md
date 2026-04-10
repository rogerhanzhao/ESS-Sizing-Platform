# Detailed Analysis: SLD and Layout Diagram Rendering Fixes

## Executive Summary

Two critical graphical rendering issues were fixed in the CALB ESS Sizing Tool:

1. **SLD DC BUSBAR Topology**: Fixed incorrect electrical representation where DC circuits from different PCS units appeared coupled/shared
2. **Layout DC Block Interior**: Changed from 2×3 grid to 1×6 single-row layout, removed door indicators and cooling labels

Both fixes are **rendering-layer only** and do not affect any calculations, data, or business logic.

---

## Problem 1: SLD DC BUSBAR Coupling

### Issue Description
The Single Line Diagram displayed DC BUSBARs in a way that made it appear as if:
- Different PCS modules shared the same DC circuits
- DC BUSBAR A and B were global (not per-PCS)
- Multiple DC blocks could be in parallel on the same busbar

This was **electrically incorrect** and **misleading** because:
- Each PCS should have its own independent DC BUSBAR A and B
- DC blocks allocated to PCS-1 should NOT connect to PCS-2's busbar
- The visual representation should match the electrical independence of each PCS

### Root Cause Analysis

**File**: `calb_diagrams/sld_pro_renderer.py` (lines 514-557, original)

**Original Code Pattern**:
```python
# Global circuit definitions
circuit_x1 = battery_x + 60
circuit_x2 = battery_x + battery_w - 60

# All DC blocks connected to SHARED circuits
dwg.add(dwg.line((circuit_x1, dc_circuit_a_y), (circuit_x2, dc_circuit_a_y), class_="thin"))
dwg.add(dwg.text("Circuit A", insert=(circuit_x1, dc_circuit_a_y - 6), class_="small"))

# Then DC blocks connected upward
for pcs_idx in range(pcs_count):
    # ...
    mid_x = (line_x_a + line_x_b) / 2
    dwg.add(dwg.line((circuit_x1, dc_circuit_a_y), (mid_x, dc_circuit_a_y), class_="thin"))
    # This creates a SHARED circuit that all blocks connect to
```

**Problem**: The `circuit_x1` and `circuit_x2` variables created global circuit traces that spanned the entire battery area, and all DC blocks connected upward to these global circuits. This created the visual (and logical) impression of a shared circuit bus.

### Solution Implementation

**File**: `calb_diagrams/sld_pro_renderer.py`

**Key Changes**:

1. **Independent BUSBAR Drawing** (lines 476-500):
```python
# For each PCS, create its own independent BUSBAR A and B
for idx in range(pcs_count):
    pcs_x = pcs_start_x + idx * slot_w
    pcs_center_x = pcs_x + pcs_box_w / 2
    
    # DC BUSBAR A for THIS PCS ONLY
    busbar_a_x1 = pcs_center_x - 35
    busbar_a_x2 = pcs_center_x + 35
    dwg.add(dwg.line((busbar_a_x1, dc_bus_a_y), (busbar_a_x2, dc_bus_a_y), class_="thick"))
    dwg.add(dwg.text(f"BUSBAR A", insert=(busbar_a_x1 - 5, dc_bus_a_y - 8), class_="small"))
    
    # DC BUSBAR B for THIS PCS ONLY
    dwg.add(dwg.line((busbar_a_x1, dc_bus_b_y), (busbar_a_x2, dc_bus_b_y), class_="thick"))
    dwg.add(dwg.text(f"BUSBAR B", insert=(busbar_a_x1 - 5, dc_bus_b_y - 8), class_="small"))
```

Each PCS now has:
- Its own DC BUSBAR A (solid line at y=376)
- Its own DC BUSBAR B (solid line at y=398)
- Non-overlapping x-coordinate ranges (each ~70px wide)

2. **Independent DC Block Connections** (lines 514-557):
```python
# For each PCS, connect ONLY its allocated DC blocks
for pcs_idx in range(pcs_count):
    blocks_for_this_pcs = blocks_per_pcs + (1 if pcs_idx < remaining_blocks else 0)
    pcs_center_x = pcs_start_x + pcs_idx * slot_w + pcs_box_w / 2
    
    for block_num, b in enumerate(pcs_dc_blocks):
        # CRITICAL: Each connection goes DIRECTLY to THIS PCS's BUSBAR
        # Circuit A connection
        line_x_a = cell_x + dc_box_w * 0.35
        dwg.add(dwg.line((line_x_a, cell_y), (line_x_a, dc_bus_a_y), class_="thin"))
        dwg.add(dwg.line((line_x_a, dc_bus_a_y), (pcs_center_x, dc_bus_a_y), class_="thin"))
        
        # Circuit B connection  
        line_x_b = cell_x + dc_box_w * 0.65
        dwg.add(dwg.line((line_x_b, cell_y), (line_x_b, dc_bus_b_y), class_="thin"))
        dwg.add(dwg.line((line_x_b, dc_bus_b_y), (pcs_center_x, dc_bus_b_y), class_="thin"))
```

Each DC block now:
- Connects with TWO vertical lines (for circuits A and B)
- Connects horizontally to its assigned PCS's BUSBAR center
- Does NOT connect through any shared circuit trace
- Cannot accidentally couple with blocks assigned to other PCS

### Verification

**Electrical Correctness**:
- 4 PCS = 4 BUSBAR A segments + 4 BUSBAR B segments = 8 independent busbars
- Each BUSBAR has unique x-coordinate range (no overlap)
- Each DC block connects to exactly one PCS's busbar pair
- No shared circuit traces exist

**Visual Verification**:
```
PCS-1        PCS-2        PCS-3        PCS-4
  |            |            |            |
  |            |            |            |
[BUSBAR A1]  [BUSBAR A2]  [BUSBAR A3]  [BUSBAR A4]  ← Independent A busbars
[BUSBAR B1]  [BUSBAR B2]  [BUSBAR B3]  [BUSBAR B4]  ← Independent B busbars
  ↑            ↑            ↑            ↑
  |            |            |            |
DC Block 1  DC Block 2  DC Block 3  DC Block 4
(only connects to PCS-1)  (only to PCS-2)  etc.
```

---

## Problem 2: DC Block Interior Layout

### Issue Description
Each DC Block container showed 6 battery modules in a **2×3 grid** (2 columns, 3 rows) with:
- A door indicator on the left side
- "COOLING" and "LIQUID" text labels
- This did not match the required design showing 6 modules in a **single row** (1×6)

### Root Cause Analysis

**File**: `calb_diagrams/layout_block_renderer.py`

**Original Code** (lines 115-156):
```python
def _draw_dc_interior(dwg, x, y, w, h, mirrored: bool = False):
    # ... setup code ...
    
    # DOOR indicator - 15% of width
    door_w = max(8.0, w * 0.15)
    door_h = h * 0.4
    door_x = x + pad if not mirrored else x + w - door_w - pad
    door_y = y + h * 0.3
    dwg.add(dwg.rect(insert=(door_x, door_y), size=(door_w, door_h), class_="thin"))
    dwg.add(dwg.line((door_x + door_w * 0.8, door_y + door_h * 0.2), 
                     (door_x + door_w * 0.8, door_y + door_h * 0.8), class_="thin"))
    
    cols = 2  # ← HARDCODED 2 columns
    rows = 3  # ← HARDCODED 3 rows
    
    # Calculate module dimensions
    module_w = (grid_w - module_spacing * (cols - 1)) / cols
    module_h = (grid_h - module_spacing * (rows - 1)) / rows
    
    # Draw 6 battery modules in 2x3 grid
    for row in range(rows):
        for col in range(cols):
            # ...
```

The hard-coded 2×3 grid was inflexible and included unwanted door/cooling visual elements.

### Solution Implementation

**File**: `calb_diagrams/layout_block_renderer.py`

**Changes to `_draw_dc_interior()`** (lines 115-144):
```python
def _draw_dc_interior(dwg, x, y, w, h, mirrored: bool = False):
    """
    Draw DC Block (BESS) interior with 6 battery module racks.
    Clean design: 6 rectangles (1x6 single row) representing battery racks, 
    no text labels, no door.
    """
    pad = min(10.0, max(4.0, w * 0.06))
    
    # NO DOOR DRAWING - Removed entirely
    
    # Battery modules grid: 1 row x 6 columns = 6 modules
    grid_x_start = x + pad
    grid_y_start = y + pad
    grid_w = w - 2 * pad
    grid_h = h - 2 * pad
    
    cols = 6  # ← Changed to 6
    rows = 1  # ← Changed to 1
    
    # Calculate module dimensions
    module_spacing = max(2.0, min(grid_w, grid_h) * 0.03)
    module_w = (grid_w - module_spacing * (cols - 1)) / cols
    module_h = grid_h  # Full height for single row
    
    # Draw 6 battery modules in 1x6 layout
    for row in range(rows):
        for col in range(cols):
            mod_x = grid_x_start + col * (module_w + module_spacing)
            mod_y = grid_y_start + row * (module_h + module_spacing)
            
            # Draw module rectangle - clean, simple
            dwg.add(dwg.rect(insert=(mod_x, mod_y), size=(module_w, module_h), class_="thin"))
```

**Changes to `_draw_dc_interior_raw()`** (lines 272-298):
Same logic applied to the raw SVG code path for when svgwrite is unavailable.

### Visual Result

**Before**:
```
┌─────────────────┐
│Door│ Cooling    │
│    ├────────┐   │
│    │ Module│   │
│    │ 1     │   │
│    ├───┬───┤   │
│    │ 2 │ 3 │   │
│    ├───┼───┤   │
│    │ 4 │ 5 │   │
│    ├───┴───┤   │
│    │  6    │   │
│    └───────┘   │
└─────────────────┘
```

**After**:
```
┌──────────────────────────────────────┐
│  M1  │  M2  │  M3  │  M4  │  M5  │  M6  │
└──────────────────────────────────────┘
```

### Verification

**Layout Correctness**:
- 6 modules per DC block ✓
- Single row (1×6) arrangement ✓
- No door indicator ✓
- No cooling/liquid labels ✓
- Clean, professional appearance ✓

---

## Implementation Details

### Files Modified

```
calb_diagrams/
├── sld_pro_renderer.py
│   ├── Lines 476-500: Independent BUSBAR drawing
│   ├── Lines 514-557: Independent DC block connections
│   └── Line 559: Updated allocation note
│
└── layout_block_renderer.py
    ├── Lines 115-144: _draw_dc_interior() - 1×6 layout
    └── Lines 272-298: _draw_dc_interior_raw() - 1×6 layout
```

### Total Changes
- **SLD file**: ~30 lines modified
- **Layout file**: ~30 lines modified
- **Total**: ~60 lines changed across 2 files

### Backward Compatibility
- ✓ No changes to public API
- ✓ No changes to data structures
- ✓ No changes to configuration
- ✓ No changes to calculation logic
- ✓ Existing tests pass without modification

---

## Testing

### Unit Tests
All existing tests pass:
```bash
pytest tests/test_layout_block_smoke.py -v  # PASSED
pytest tests/test_sld_pro_smoke.py -v       # PASSED
```

### Comprehensive Verification Tests
Created custom tests to verify:
1. SLD has 4 independent BUSBAR A/B segments
2. Each DC block connects only to its assigned PCS
3. Layout has 6 modules per DC block
4. No door/cooling elements present
5. Scaling works with 2, 4, and 8 PCS configurations

All verification tests: **PASSED** ✓

---

## Code Examples

### How to Generate Diagrams with the Fixes

```python
from calb_diagrams.specs import SldGroupSpec, LayoutBlockSpec
from calb_diagrams.sld_pro_renderer import render_sld_pro_svg
from calb_diagrams.layout_block_renderer import render_layout_block_svg
from pathlib import Path

# SLD with independent BUSBARS
sld_spec = SldGroupSpec(
    group_index=1,
    pcs_count=4,
    pcs_rating_kw_list=[1250.0, 1250.0, 1250.0, 1250.0],
    dc_blocks_total_in_group=4,
    dc_blocks_per_feeder=[1, 1, 1, 1],
    # ... other parameters ...
)

svg_path, warning = render_sld_pro_svg(sld_spec, Path("sld.svg"), Path("sld.png"))
# Result: 4 independent BUSBAR A/B segments, each with its own DC blocks

# Layout with 1×6 DC blocks
layout_spec = LayoutBlockSpec(
    block_indices_to_render=[1, 2, 3, 4],
    dc_blocks_per_block=4,
    # ... other parameters ...
)

svg_path, warning = render_layout_block_svg(layout_spec, Path("layout.svg"), Path("layout.png"))
# Result: DC blocks with 6 modules in single row, no door/cooling elements
```

---

## Electrical and Physical Accuracy

### Electrical Topology (SLD)
The SLD now correctly represents:
- Each PCS has 2 independent DC BUSBARs (A and B)
- DC blocks are allocated to specific PCS units
- No cross-coupling between PCS units
- Each circuit carries power in one direction only

### Physical Layout (Layout Diagram)
The layout now correctly shows:
- DC Block as a rectangular container with 6 battery racks
- Racks arranged horizontally in a single row
- Container without door representation (simplified view)
- Container without HVAC/cooling implications

This matches the reference design specifications provided.

---

## Future Enhancements (Not in Scope)

These changes enable future work:
1. Add detailed battery module parameters to layout
2. Add thermal management system representations
3. Add structural support information
4. Enhance transformer and RMU details in layout
5. Add cable routing visualization

---

## Sign-Off

✓ All fixes implemented and tested
✓ No regressions in existing functionality  
✓ Electrical and physical correctness verified
✓ Code follows existing patterns and conventions
✓ Documentation complete
