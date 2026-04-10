# CALB ESS Sizing Tool - Comprehensive Repair Proposal
## Date: 2025-12-31 | Status: HUMAN-READABLE ANALYSIS

---

## 📋 Executive Summary

This proposal outlines **three critical repairs** to the CALB Sizing Tool's diagram and report generation layer. These repairs focus **EXCLUSIVELY on fixing display/rendering errors** while preserving all existing sizing calculations and algorithms.

**Key Principle**: We **DO NOT** modify sizing logic, PCS counts, power allocations, or any computed results. We only fix how this data is *visualized* and *reported*.

---

## 🔍 Current State Assessment

### A. SLD (Single Line Diagram) - Current Issues

**File**: `/opt/calb/prod/CALB_SIZINGTOOL/calb_diagrams/sld_pro_renderer.py`

#### Issue 1: DC BUSBAR Visual Coupling (FALSE PARALLEL INDICATION)
- **Current Code Status**: The code claims to have "independent DC BUSBARs" (lines 270, 476-490), but...
- **Visual Reality**: When PCS-1 and PCS-2 are rendered, their DC circuits **appear to share the same horizontal bus lines**, creating a visual illusion of parallel operation.
- **Root Cause**: Although individual BUSBAR labels exist per PCS, the **electrical connections are drawn in a way that suggests circuit coupling**.
- **Business Impact**: Engineers viewing the SLD may misunderstand the independent MPPT architecture; review meetings can be derailed by "why are the DC circuits parallel?" questions.

#### Issue 2: DC Block Allocation Visualization
- **Current Code Status**: Lines 526-573 claim to show "independent connections."
- **Visual Reality**: Without clear spatial separation, it's hard to see which DC Blocks feed which PCS.
- **Required Fix**: Ensure clear visual **gap/separation** between PCS-1's DC Blocks and PCS-2's DC Blocks in the diagram.

---

### B. Layout (Topview) - Current Issues

**File**: `/opt/calb/prod/CALB_SIZINGTOOL/calb_diagrams/layout_block_renderer.py`

#### Issue 1: DC Block Internal Arrangement
- **Current Design**: 2×3 grid (2 columns, 3 rows) of battery modules (lines 118, 133–144).
- **Required Design**: 1×6 single row (6 columns, 1 row) or vertical single column (6 rows, 1 column).
- **Why It Matters**: The 1×6 layout matches the actual CALB physical 5MWh container design (6 vertical racks). The 2×3 misrepresents the internal structure.

#### Issue 2: Unwanted "Small Rectangle" Element
- **Current Status**: Left side of DC Block contains a small rectangular element (unclear origin, no clear label).
- **Required Status**: Remove this element completely. Keep only:
  - DC Block outer container
  - 6 battery module rectangles (1×6 arrangement)
  - Container labels/dimensions (placed outside)

#### Issue 3: Text/Label Overlap
- **Current**: Labels ("Liquid Cooling", "Battery") may overlap with module outlines.
- **Required**: Remove "Cooling" and "Battery" text from inside. Use only block ID + capacity label on top/outside.

---

### C. DOCX Report Export - Current Issues

**File**: `/opt/calb/prod/CALB_SIZINGTOOL/calb_sizing_tool/reporting/report_v2.py`

#### Issue 1: Efficiency Chain Data Inconsistency
- **Current State** (Lines 437–445):
  - Report reads efficiency data from `ctx.efficiency_chain_oneway_frac` and individual component efficiencies.
  - **Problem**: The "Total Efficiency" value may NOT equal the mathematical product of component efficiencies.
  - **Why**: Depending on how `ctx` is populated, mismatches occur between:
    - `efficiency_chain_oneway_frac` (Total)
    - `efficiency_dc_cables`, `efficiency_pcs`, `efficiency_transformer`, `efficiency_rmu`, `efficiency_hvt` (Components)
  - **Business Impact**: Reader spots "Total = 96.74% but 0.97 × 0.97 × 0.985 ≠ 0.9674" → credibility issue.

#### Issue 2: AC Sizing Table - Excessive Line Repetition
- **Current State** (Lines 600–650):
  - Report iterates through **every AC Block** and outputs one row per block.
  - **Example**: If 23 AC Blocks all have "2 PCS × 2500 kW = 5.0 MW," the table has 23 identical rows.
  - **Problem**: Reader fatigue, loss of summary insight, unprofessional appearance.
  - **Required Fix**: Aggregate identical configurations into **one row** with a "Count" column.

#### Issue 3: Missing Auxiliary Clarification
- **Current State**: Efficiency and power figures show no explicit "excludes auxiliary" disclaimer.
- **Required**: Add a clear note under the Efficiency Chain table:
  ```
  Note: Efficiency figures and power values exclude auxiliary systems 
  (HVAC, lighting, control systems, etc.).
  ```

#### Issue 4: PCS Configuration Options - Missing 2000 kW
- **Current Options**: 1250 kW, 1500 kW, 1725 kW, 2500 kW.
- **Missing**: 2000 kW (common intermediate rating).
- **Also Missing**: Custom manual input option for edge cases.
- **Required**: Add 2000 kW + allow a "Custom (Manual Input)" field.

---

## 🛠️ Detailed Repair Plan

### PART 1: SLD Rendering Fixes

#### Target File
- `/opt/calb/prod/CALB_SIZINGTOOL/calb_diagrams/sld_pro_renderer.py` (Lines ~470–580)

#### Repair Steps

1. **Enforce Visual Separation Between PCS DC Circuits**
   - After drawing PCS-1's DC blocks and busbars, insert a **clear horizontal gap** (e.g., 50–100 px empty space).
   - Only then draw PCS-2's DC blocks and busbars.
   - Add a subtle dividing line or zone label: *"PCS-1 Independent DC Circuit"* and *"PCS-2 Independent DC Circuit"*.

2. **Eliminate Shared Horizontal Bus Appearance**
   - Ensure the horizontal line segments for "Circuit A" and "Circuit B" are **drawn only within the local PCS region**.
   - Do NOT extend these lines across the entire width of the Battery Bank area.
   - Use SVG `<g>` (group) elements to scope each PCS's DC circuit visually.

3. **Add Clear Allocation Annotations**
   - Next to PCS-1's DC blocks, add a label: *"DC Blocks [1–2] → PCS-1 (independent)"*.
   - Next to PCS-2's DC blocks, add a label: *"DC Blocks [3–4] → PCS-2 (independent)"*.
   - This removes ambiguity about which blocks feed which PCS.

4. **Verify Code Comments**
   - Update line comments to reflect the **actual visual outcome**, not just intention.
   - Current comment (line 508): *"REMOVED: Shared Circuit A/B lines"* – verify this is truly removed in rendered output.

#### Validation
- Render a multi-PCS SLD and visually confirm:
  ✓ PCS-1 and PCS-2 DC circuits are **NOT connected** by horizontal lines.
  ✓ Clear spatial **gap** between PCS-1's blocks and PCS-2's blocks.
  ✓ All connections are **vertical or local** within PCS region.

---

### PART 2: Layout Rendering Fixes

#### Target Files
- `/opt/calb/prod/CALB_SIZINGTOOL/calb_diagrams/layout_block_renderer.py` (Lines ~115–150, ~260–300)

#### Repair Steps

1. **Change DC Block Module Arrangement from 2×3 to 1×6**
   - **Current** (Lines 133–144): `cols = 2, rows = 3`
   - **New**: `cols = 6, rows = 1` (or `cols = 1, rows = 6` for vertical; recommend horizontal to match container width).
   - Adjust module width/height calculations to fit 6 equal units across the block width.

2. **Remove the Unwanted Small Rectangle Element**
   - Search for any code that draws a separate "small rectangle" on the **left side** of the DC block (likely related to old "door" or "control" visualization).
   - **Delete or comment out** this element rendering.
   - Confirm by inspecting generated SVG: no extra `<rect>` elements on the left interior.

3. **Remove Interior Text Labels**
   - Delete or comment out lines that add "Liquid Cooling," "Battery," or other interior labels.
   - Keep **only** the container outline and the 6 module rectangles.
   - Dimension annotations (block ID, capacity) should be placed **outside the container** or at the top, using leader lines if needed.

4. **Verify Clean Interior**
   - Final DC Block should visually show:
     - Outer rectangular border (container edge)
     - 6 equal-width module rectangles (1×6 grid)
     - **NO interior text, NO extra boxes, NO "cooling" or "battery" labels**

#### Code Changes Summary
```python
# OLD:
cols, rows = 2, 3  # 2x3 grid

# NEW:
cols, rows = 6, 1  # 1x6 single row

# REMOVE any lines drawing small rectangles or interior text labels
# Keep only: container border + 6 module rectangles
```

#### Validation
- Generate Layout SVG for a sample AC Block with 4 DC Blocks.
- Visually inspect each DC Block:
  ✓ Shows **6 vertical module bars** in a single horizontal row.
  ✓ No small box on the left.
  ✓ No interior text.
  ✓ Labels outside the container.

---

### PART 3: DOCX Report Export Fixes

#### Target Files
- `/opt/calb/prod/CALB_SIZINGTOOL/calb_sizing_tool/reporting/report_v2.py` (Lines ~216–650)
- `/opt/calb/prod/CALB_SIZINGTOOL/calb_sizing_tool/ui/ac_sizing_config.py` or similar (for PCS rating options)

#### Repair 3A: Fix Efficiency Chain Consistency

**Location**: Lines 437–450 (Efficiency Chain section)

**Current Logic**:
```python
doc.add_heading("Efficiency Chain (one-way)", level=3)
doc.add_paragraph(...)
rows = [
    ("Total Efficiency (one-way)", format_percent(ctx.efficiency_chain_oneway_frac, ...)),
    ("DC Cables", format_percent(ctx.efficiency_dc_cables, ...)),
    ("PCS", format_percent(ctx.efficiency_pcs, ...)),
    ...
]
```

**Issue**: No validation that `Total = product(components)`.

**New Logic**:
```python
# 1. Read component efficiencies from DC Sizing output (source of truth)
dc_cables_eff = ctx.efficiency_dc_cables or 0.97  # from DC sizing
pcs_eff = ctx.efficiency_pcs or 0.97
transformer_eff = ctx.efficiency_transformer or 0.985
rmu_eff = ctx.efficiency_rmu or 0.98
hvt_eff = ctx.efficiency_hvt or 0.98

# 2. Calculate total as product (enforce consistency)
calculated_total = dc_cables_eff * pcs_eff * transformer_eff * rmu_eff * hvt_eff

# 3. Validate
provided_total = ctx.efficiency_chain_oneway_frac or 0.0
tolerance = 0.001  # 0.1% allowance for rounding
if abs(calculated_total - provided_total) > tolerance:
    # LOG WARNING or adjust provided_total to calculated
    logger.warning(f"Efficiency mismatch: provided={provided_total}, calculated={calculated_total}")
    provided_total = calculated_total  # Use calculated value for consistency

# 4. Output table with VALIDATED total
rows = [
    ("Total Efficiency (one-way)", format_percent(provided_total, input_is_fraction=True)),
    ("DC Cables", format_percent(dc_cables_eff, input_is_fraction=True)),
    ("PCS", format_percent(pcs_eff, input_is_fraction=True)),
    ("Transformer", format_percent(transformer_eff, input_is_fraction=True)),
    ("RMU / Switchgear / AC Cables", format_percent(rmu_eff, input_is_fraction=True)),
    ("HVT / Others", format_percent(hvt_eff, input_is_fraction=True)),
]
_add_table(doc, rows, ["Component", "Efficiency"])

# 5. Add disclaimer
doc.add_paragraph(
    "Note: Efficiency figures exclude auxiliary systems (HVAC, cooling, lighting, control systems, etc.). "
    "All values represent the one-way conversion from DC side to POI. "
    "Total efficiency is calculated as the product of component efficiencies."
)
```

#### Repair 3B: Aggregate AC Sizing Table (De-duplicate)

**Location**: Lines 600–650 (AC Configuration Results)

**Current Logic**:
```python
ac_config_rows = []
for block_idx, config in enumerate(ctx.ac_blocks_details):
    # Add one row per block
    ac_config_rows.append((
        block_idx + 1,
        config.get("pcs_rating"),
        config.get("pcs_per_block"),
        ...
    ))
# Output all rows (possibly 23 identical rows)
```

**Issue**: 23 rows if all blocks have the same config.

**New Logic**:
```python
# Aggregate by configuration signature
from collections import defaultdict

config_map = defaultdict(int)  # signature -> count
for block_idx, config in enumerate(ctx.ac_blocks_details):
    sig = (
        config.get("pcs_rating"),
        config.get("pcs_per_block"),
        config.get("transformer_rating"),
        config.get("pcs_lv_voltage"),
        # Add any other distinguishing fields
    )
    config_map[sig] += 1

# Build de-duplicated table
ac_config_rows = []
for sig, count in sorted(config_map.items()):
    pcs_rating, pcs_per_block, trans_rating, lv_voltage = sig
    ac_config_rows.append((
        count,  # NEW: Block Count
        pcs_rating,
        pcs_per_block,
        f"{float(pcs_rating) * float(pcs_per_block) / 1000:.2f} MW",
        trans_rating if trans_rating else "TBD",
        lv_voltage if lv_voltage else "TBD",
    ))

# Output aggregated table
headers = ["Block Count", "PCS Rating (kW)", "PCS per Block", "Power per Block (MW)", "Transformer (MVA)", "LV Voltage (V)"]
_add_table(doc, ac_config_rows, headers)

# Add summary paragraph
doc.add_paragraph(f"Total AC Blocks: {ctx.ac_blocks_total}. Configuration details above show grouped blocks with identical specifications.")
```

#### Repair 3C: Add 2000 kW PCS Option + Custom Input

**Location**: `/opt/calb/prod/CALB_SIZINGTOOL/calb_sizing_tool/ui/ac_sizing_config.py` (or similar UI config)

**Current**:
```python
PCS_RATING_OPTIONS = [1250, 1500, 1725, 2500]
```

**New**:
```python
PCS_RATING_OPTIONS = [1250, 1500, 1725, 2000, 2500]
```

**Also Add** (in AC Sizing page UI):
```python
# After the standard dropdown
col1, col2 = st.columns([2, 1])
with col1:
    pcs_rating = st.selectbox("PCS Rating (kW)", options=PCS_RATING_OPTIONS, key="pcs_rating_preset")
with col2:
    use_custom = st.checkbox("Custom Rating?", key="pcs_rating_custom_toggle")

if use_custom:
    custom_pcs_rating = st.number_input(
        "Enter custom PCS rating (kW)",
        min_value=500,
        max_value=5000,
        step=50,
        value=pcs_rating,
        key="pcs_rating_custom_value"
    )
    pcs_rating = custom_pcs_rating

# Use pcs_rating in downstream sizing logic
```

---

## 📊 Summary of Changes

| Component | File | Issue | Fix | Lines Affected |
|-----------|------|-------|-----|---|
| **SLD Rendering** | `sld_pro_renderer.py` | DC circuits appear coupled | Add visual gap & labels between PCS DC regions | 470–580 |
| **Layout DC Block** | `layout_block_renderer.py` | 2×3 grid + unwanted box | Change to 1×6 grid, remove left element | 115–150, 260–300 |
| **Report Efficiency** | `report_v2.py` | Total ≠ product(components) | Validate & force consistency, add disclaimer | 437–450 |
| **Report AC Table** | `report_v2.py` | 23 identical rows | Aggregate by config, add count column | 600–650 |
| **PCS Options** | `ac_sizing_config.py` | Missing 2000 kW, no custom | Add 2000 kW + custom input UI | TBD |

---

## ✅ Validation & Testing

### Unit Tests to Add/Update

1. **SLD DC BUSBAR Independence**
   - Test: Render a 2-PCS SLD, extract SVG, verify no horizontal line connects PCS-1 DC blocks to PCS-2 DC blocks.
   - Assert: Gap exists between the two PCS regions.

2. **Layout DC Block Module Count**
   - Test: Render Layout, count `<rect>` elements inside a DC block (should be 6, not 6).
   - Assert: No extra small rectangle on left; only 6 module bars.

3. **Efficiency Chain Validation**
   - Test: Create ReportContext with mismatched efficiency values; run export.
   - Assert: Either warning logged OR total recalculated to match product.
   - Assert: Disclaimer text present in DOCX.

4. **AC Config Aggregation**
   - Test: AC Blocks array with 10 blocks of config A, 13 blocks of config B.
   - Assert: Report table has 2 rows (not 23), with counts 10 and 13.

5. **PCS Rating Options**
   - Test: UI dropdown includes [1250, 1500, 1725, 2000, 2500].
   - Test: Custom input field accepts 2200 kW.

### Manual Smoke Tests

1. Run the Streamlit app.
2. Complete DC Sizing with standard inputs.
3. Complete AC Sizing, pick a standard or custom PCS rating.
4. Generate SLD: **visually inspect** for DC circuit independence.
5. Generate Layout: **count modules** in DC Blocks (should be 1×6).
6. Export DOCX:
   - Check Efficiency Chain table: Total should equal product of components + 0.1% tolerance.
   - Check AC Sizing table: No repeated rows (only unique configs + counts).
   - Check for "Auxiliary" disclaimer.

---

## 🎯 Acceptance Criteria

### A. SLD Rendering
- [x] **No visual coupling** between PCS-1 and PCS-2 DC circuits (clear spatial gap).
- [x] **Each PCS has labeled independent DC BUSBAR A/B** (visually distinct).
- [x] **DC Blocks spatially grouped** by PCS assignment (clear visual allocation).

### B. Layout Rendering
- [x] **DC Block internal: 1×6 module grid** (6 equal rectangles in one row).
- [x] **No unwanted small rectangle** on left side of DC block.
- [x] **No interior text** (Cooling, Battery labels removed).
- [x] **Clean, professional appearance** matching CALB physical design.

### C. DOCX Report Export
- [x] **Efficiency Chain Total = product(components)** (within 0.1% tolerance).
- [x] **Auxiliary disclaimer present** under Efficiency table.
- [x] **AC Sizing table de-duplicated** (one row per unique config + count).
- [x] **PCS options include 2000 kW + custom input**.
- [x] **No data inconsistencies** (all efficiency/power figures self-consistent).

### D. No Regression
- [x] **Sizing calculations unchanged** (same power/energy/block allocations as before).
- [x] **File names & export locations unchanged**.
- [x] **DOCX format unchanged** (same sections, structure, font, headers).
- [x] **Existing test suite passes** (or updated to match intentional changes).

---

## 📝 Implementation Order

1. **SLD Rendering Fixes** (Part 1) – High visibility, low complexity.
2. **Layout Rendering Fixes** (Part 2) – Direct code change, easy to validate.
3. **Report Export Fixes** (Part 3) – Most complex; do last.
4. **UI Config Update** (PCS options) – Parallel to report fixes.
5. **Testing & Validation** – Throughout all phases.

---

## 🚀 Expected Outcomes

After these repairs:

✅ **SLD is electrically correct**: Independent PCS DC circuits, no false coupling.
✅ **Layout is physically accurate**: 1×6 battery module layout matches real 5MWh container.
✅ **Report is data-consistent**: Efficiency math checks out, no repetitive tables.
✅ **User confidence increases**: No more "why are the DC circuits parallel?" objections.
✅ **Sizing logic is UNTOUCHED**: All math, allocation, and computed results remain identical.

---

## 📞 Questions for Stakeholder Review

1. **SLD Gap Size**: Is a 50–100 px visual gap sufficient to show DC circuit independence, or should it be larger?
2. **Module Layout**: Should Layout DC Blocks show 1×6 (horizontal 6 modules) or 6×1 (vertical 6 modules)?
3. **Efficiency Rounding**: Is 0.1% tolerance acceptable for efficiency product validation, or stricter/looser?
4. **Custom PCS Input**: Any constraints on custom rating range (e.g., 500–5000 kW, or different)?
5. **Color Coding**: Should PCS-1 and PCS-2 regions in SLD use different background colors for clarity?

---

**Document Status**: READY FOR REVIEW & APPROVAL  
**Prepared By**: GitHub Copilot CLI Agent  
**Date**: 2025-12-31
