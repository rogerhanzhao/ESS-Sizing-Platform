# REPAIR PROPOSAL - STAKEHOLDER REVIEW CHECKLIST

## 📋 Pre-Implementation Review

This document is for **Human Review & Approval** before any code changes begin.

---

## 🔍 Review Section 1: SLD Rendering (Visual DC Circuit Independence)

**File(s) to modify**: `calb_diagrams/sld_pro_renderer.py`

### Current Visual Problem
```
PCS-1         PCS-2
  |             |
  v             v
┌───┐         ┌───┐
│DC │         │DC │
│BUS│         │BUS│
│A/B│         │A/B│
└───┘         └───┘
  │             │
  └─────X─────┘  ← Visually appears connected (FALSE COUPLING)
        ↑
   Shared DC lines make it look parallel
```

### Proposed Visual Solution
```
PCS-1 Region          [50-100px Gap]          PCS-2 Region
  ┌──────────┐                                  ┌──────────┐
  │         │                                  │         │
  │ PCS-1   │                                  │ PCS-2   │
  │  DC │                                  │  DC │
  │  BUS │                                  │  BUS │
  │  A/B │                                  │  A/B │
  │         │                                  │         │
  └──────────┘                                  └──────────┘
      │ │                                        │ │
  [Block 1]                                  [Block 3]
  [Block 2]                                  [Block 4]
  
  ← INDEPENDENT ↑                             ← INDEPENDENT
    (no shared lines crossing gap)
```

### Questions for Stakeholder
- [ ] Approve 50–100px gap size for visual separation?
- [ ] Want colored zone backgrounds (e.g., light blue for PCS-1, light orange for PCS-2)?
- [ ] Should allocation notes appear as text labels or just implicit in layout?

**Stakeholder Sign-off**: _____________ Date: _______

---

## 🔍 Review Section 2: Layout Rendering (DC Block Module Arrangement)

**File(s) to modify**: `calb_diagrams/layout_block_renderer.py`

### Current Visual Problem
```
DC Block (Old 2×3 layout)           DC Block (New 1×6 layout)
┌───────────────┐                  ┌───────────────────────┐
│ [1] [2]       │                  │ [1][2][3][4][5][6]    │
│ [3] [4]       │                  │                       │
│ [5] [6]       │                  │                       │
│ ┌─────┐       │  (small box)      │                       │
│ │???  │       │                  │ (no clutter)          │
└───────────────┘                  └───────────────────────┘
```

### Proposed Visual Solution
```
✓ Remove 2×3 grid → use 1×6 single row
✓ Delete small rectangle on left
✓ Remove interior text ("Cooling", "Battery")
✓ Keep container outline + 6 module bars + external label (Block ID, capacity)
```

### Questions for Stakeholder
- [ ] Approve 1×6 horizontal layout (vs. 6×1 vertical)?
- [ ] Any specific module bar colors/patterns preferred?
- [ ] Should module bars have individual ID labels (e.g., M1, M2, ..., M6) or stay clean?

**Stakeholder Sign-off**: _____________ Date: _______

---

## 🔍 Review Section 3: DOCX Report Export (Data Consistency & Aggregation)

**File(s) to modify**: `calb_sizing_tool/reporting/report_v2.py`

### Sub-Issue 3A: Efficiency Chain Math

#### Current Problem
```
Report shows:
┌─────────────────────────────┬──────────┐
│ Component                   │ Value    │
├─────────────────────────────┼──────────┤
│ Total (one-way)             │ 96.74%   │ ← Provided
│ DC Cables                   │ 97.00%   │
│ PCS                         │ 97.00%   │
│ Transformer                 │ 98.50%   │
│ RMU / AC Cables             │ 98.00%   │
│ HVT / Others                │ 98.00%   │
└─────────────────────────────┴──────────┘

Manual check: 0.97 × 0.97 × 0.985 × 0.98 × 0.98 = 0.9454 ≠ 0.9674
⚠️ MISMATCH! Reader questions credibility.
```

#### Proposed Solution
```
1. Read components from DC Sizing (source of truth)
2. Calculate: Total = 0.97 × 0.97 × 0.985 × 0.98 × 0.98 = 0.9454
3. If provided total ≠ calculated, use calculated (more conservative)
4. Add disclaimer:
   "Note: Efficiency figures exclude auxiliary systems (HVAC, cooling, 
    lighting, controls, etc.). All values represent one-way DC→AC conversion."
5. Table now shows CONSISTENT math
```

### Questions for Stakeholder
- [ ] Accept 0.1% tolerance for efficiency validation (e.g., |0.9454 - 0.9474| = 0.002 < 0.001 → OK)?
- [ ] Prefer to force exact product match or allow small discrepancy if source data says otherwise?
- [ ] Approve disclaimer text wording?

**Stakeholder Sign-off**: _____________ Date: _______

---

### Sub-Issue 3B: AC Sizing Table De-duplication

#### Current Problem
```
AC Configuration Results
┌──────────┬────────────┬──────────────┬────────────────┐
│ Block ID │ PCS Rating │ PCS per Blk  │ Power per Blk  │
├──────────┼────────────┼──────────────┼────────────────┤
│ 1        │ 2500 kW    │ 2            │ 5.0 MW         │
│ 2        │ 2500 kW    │ 2            │ 5.0 MW         │
│ 3        │ 2500 kW    │ 2            │ 5.0 MW         │
│ ...      │ ...        │ ...          │ ...            │
│ 23       │ 2500 kW    │ 2            │ 5.0 MW         │ ← 23 identical rows!
└──────────┴────────────┴──────────────┴────────────────┘

Problem: Hard to read, unprofessional, defeats summary purpose.
```

#### Proposed Solution
```
AC Configuration Summary
┌────────────────┬────────────┬──────────────┬────────────────┐
│ Block Count    │ PCS Rating │ PCS per Blk  │ Power per Blk  │
├────────────────┼────────────┼──────────────┼────────────────┤
│ 23             │ 2500 kW    │ 2            │ 5.0 MW         │ ← 1 row!
└────────────────┴────────────┴──────────────┴────────────────┘

Summary text: "All 23 AC Blocks share identical configuration (2 × 2500 kW per block)."

Clean, professional, easy to read.
```

### Questions for Stakeholder
- [ ] Approve aggregation logic (group by config signature)?
- [ ] Any additional fields that should be included in config signature (e.g., feeder count)?
- [ ] If 20 blocks match config A and 3 blocks match config B, should both rows appear? (yes)

**Stakeholder Sign-off**: _____________ Date: _______

---

### Sub-Issue 3C: PCS Rating Options & Custom Input

#### Current Problem
```
Available PCS ratings: 1250, 1500, 1725, 2500 kW
Missing: 2000 kW (common intermediate size)
No custom input for unique project requirements
```

#### Proposed Solution
```
Step 1: Add to PCS_RATING_OPTIONS
PCS_RATING_OPTIONS = [1250, 1500, 1725, 2000, 2500]

Step 2: Add Custom Input UI
┌─────────────────────────────────┬──────────┐
│ Select PCS Rating (kW)          │ Dropdown │ ← Standard options
└─────────────────────────────────┴──────────┘

☐ Use custom PCS rating?          ← Checkbox

If checked:
┌─────────────────────────────────┬──────────┐
│ Enter custom rating (kW)        │ 2350 kW  │ ← Number input
│ (Range: 500–5000 kW)            │          │
└─────────────────────────────────┴──────────┘
```

### Questions for Stakeholder
- [ ] Approve adding 2000 kW to standard options?
- [ ] Custom input range: 500–5000 kW acceptable? (or different bounds?)
- [ ] Should custom input validation check against equipment database, or allow any value?

**Stakeholder Sign-off**: _____________ Date: _______

---

## ✅ Final Acceptance Checklist

Before implementation starts, confirm all checkboxes:

### SLD Independence
- [ ] Stakeholder reviewed visual gap proposal
- [ ] Gap size (50–100px) approved
- [ ] Zone labeling approach approved

### Layout 1×6 Arrangement
- [ ] Stakeholder reviewed module layout change
- [ ] Removal of small left box and interior text approved
- [ ] Final cleanliness/professional appearance acceptable

### Efficiency Chain Validation
- [ ] Stakeholder approved math fix (Total = product of components)
- [ ] Tolerance level (0.1%) acceptable
- [ ] Auxiliary disclaimer text approved

### AC Table Aggregation
- [ ] Stakeholder approved de-duplication logic
- [ ] Table structure (Block Count + Config) acceptable
- [ ] Summary paragraph approach approved

### PCS Configuration
- [ ] 2000 kW addition approved
- [ ] Custom input feature approved
- [ ] Input range (500–5000 kW) approved

### Code Quality & Regression
- [ ] No changes to Sizing logic (DC/AC blocks, power allocation, PCS counts)
- [ ] No changes to efficiency calculations (only DISPLAY/CONSISTENCY)
- [ ] File names, export paths, DOCX format remain unchanged
- [ ] All existing tests still pass (or updated intentionally)

---

## 🚀 Sign-Off

**Project Manager**: _________________ Date: _______

**Technical Lead**: _________________ Date: _______

**Stakeholder**: _________________ Date: _______

---

## 📝 Notes & Comments

```
[Stakeholder to fill in any special requirements, constraints, or clarifications]
```

---

**Once all signatures are collected, implementation can proceed with confidence.**
