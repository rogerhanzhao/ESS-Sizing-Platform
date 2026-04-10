# Quick Test Guide - CALB Sizing Platform v2.1

## ✅ What's Ready

### 1. Core System Status
- **DC Sizing**: Stages 1-4 intact ✓
- **AC Sizing**: PCS ratings (1250/1500/1725/2000/2500 kW) ✓
- **Report Export**: Full DOCX with all sections ✓
- **Diagrams**: SLD (independent DC busbar per PCS) + Layout (1×6 modules) ✓
- **Data Consistency**: All fields linked to source calculations ✓

### 2. Recent Fixes
- [x] Guarantee Year correctly mapped to DC Sizing output
- [x] POI Usable @ Guarantee Year auto-populated
- [x] Stage 3 missing data (eta_chain_oneway, annual table) added
- [x] SLD DC block count per AC block (not total)
- [x] Layout 1×6 module arrangement
- [x] Report AC Sizing table aggregation (no duplicates)
- [x] Efficiency note: "excludes auxiliary loads"

---

## 🧪 How to Test (5-Step Workflow)

### Step 1: Start Streamlit
```bash
cd /opt/calb/prod/CALB_SIZINGTOOL
python3 -m streamlit run app.py
```
Open: `http://localhost:8501`

### Step 2: Project Inputs (Stage 1)
**Input Test Data:**
```
Project Name:              TEST_CNS_75MW
POI Power Requirement:     75 MW
POI Energy Requirement:    300 MWh
Guarantee Year:            10
Project Life:              20 years
Grid Voltage:              110 kV
```
✓ **Verify:** All fields saved to session_state

### Step 3: DC Sizing (Stage 2-3)
**Select:**
- Battery Technology: [your choice]
- DoD: [auto-calculated]
- Degradation: [auto-calculated]

✓ **Verify:** 
- `st.session_state["dc_results"]["guarantee_year"]` = 10
- `st.session_state["dc_results"]["poi_usable_mwh_at_guarantee_year"]` = ~270-290 MWh
- `st.session_state["dc_results"]["stage3_annual_degradation_data"]` has 10+ rows
- Efficiency components all populated (cable, PCS, transformer, etc.)

### Step 4: AC Sizing (Stage 4)
**Select:**
- PCS Model: 1500 kW (or test all 5 options)
- Target: Let system auto-select AC blocks
- Or manually set: 4-5 AC blocks

✓ **Verify:**
- `st.session_state["ac_results"]["ac_blocks"]` has correct count
- Each AC block shows: PCS count, power per block, transformer, DC blocks allocated
- Total PCS modules = sum of all PCS per block
- No duplicate rows in configuration table

### Step 5: Export Report
**Button:** "📥 Export Technical Proposal DOCX"

✓ **Verify Exported File:**

#### A. Executive Summary (Page 1)
| Field | Should Show | Status |
|-------|------------|--------|
| Guarantee Year | 10 | ✓ |
| POI Usable @ Guarantee | ~270-290 MWh | ✓ |
| DC Nameplate | [DC blocks × 5 MWh] | ✓ |

#### B. Stage 1: Energy Requirement
- [ ] eta_chain_oneway labeled as "**DC-to-POI Efficiency Chain (One-Way)**"
- [ ] S&C loss = [value]% (not empty)
- [ ] DoD = [value]% (not empty)
- [ ] DC RTE = [value]% (not empty)
- [ ] DC Energy Capacity Required = [value] MWh (not empty)

#### C. Stage 2: AC Sizing Table
```
| Config Type | Qty | PCS/Block | Rating | Power | Transformer |
|-------------|-----|-----------|--------|-------|-------------|
| 4x1500_2MVA |  1  |     4     | 1500kW | 6.0MW |  2000 kVA   |
```
- [ ] No duplicate rows (if all AC blocks are same config)
- [ ] "Qty" column shows number of blocks with this config

#### D. Stage 3: POI Usable Energy vs Year
- [ ] Graph visible (image embedded)
- [ ] **Table below graph** with columns:
  ```
  Year | SOH@COD | SOH vs FAT | DC Usable | POI Usable | DC RTE | System RTE
  0    | 100%    | 100%       | 300       | 285        | 95%    | 94.2%
  1    | 99.5%   | 99.5%      | 298.5     | 283.6      | 95%    | 94.2%
  ...
  10   | 96%     | 96%        | 288       | 273.6      | 95%    | 94.2%
  ```
  - [ ] Data matches DC Sizing Stage 3 export exactly
  - [ ] Rows = project_life_years (20 rows for 20-year project)

#### E. Chapter 6: Single Line Diagram
- [ ] SLD image embedded (PNG)
- [ ] Shows correct number of AC blocks
- [ ] Each AC block shows correct number of DC blocks
  - Example: If 5 AC blocks with 4 DC blocks each → 4 DC blocks shown per AC block
  - **NOT** 20 DC blocks under each AC block (total project count)
- [ ] Each PCS has **independent DC BUSBAR** (A/B not shared)
- [ ] DC circuits properly routed

#### F. Chapter 7: Site Layout
- [ ] Layout image embedded (PNG)
- [ ] DC blocks show **6 modules in 1 row** (1×6)
  - **NOT** 2×3 arrangement
- [ ] No "Liquid Cooling" or "Battery" labels inside container
- [ ] Right side has thin "Liquid Cooling" strip
- [ ] Dimensions labeled outside boxes (0.3m, 2.0m, etc.)

---

## 🐛 Quick Troubleshooting

### Issue: "No module named 'pydantic'"
```bash
pip install pydantic>=2.0.0
```

### Issue: "Permission denied: 'outputs/sld_latest.svg'"
```bash
chmod -R 755 /opt/calb/prod/CALB_SIZINGTOOL/outputs
```

### Issue: Streamlit "SessionState" error on SLD page
- Clear browser cache
- Restart Streamlit: `Ctrl+C` then run again
- Check that `st.session_state.setdefault()` is called before `st.data_editor()`

### Issue: DOCX export returns empty file
- Check `/opt/calb/prod/CALB_SIZINGTOOL/outputs/reports/` for error logs
- Verify DC Sizing was completed (check `st.session_state["dc_results"]`)
- Verify AC Sizing was completed (check `st.session_state["ac_results"]`)

---

## 📋 Verification Checklist

Run through each item:

### Data Consistency
- [ ] Executive Summary Guarantee Year = DC Sizing Guarantee Year
- [ ] POI Usable @ Guarantee Year = DC Sizing output value
- [ ] Total AC Power = AC blocks × power per block
- [ ] Total DC Blocks shown in SLD = AC sizing allocation sum

### Report Completeness
- [ ] No empty fields (marked with "=" or blank cells)
- [ ] No debug text like "aa"
- [ ] All efficiency components listed with percentages
- [ ] Stage 3 annual table has all 7 columns populated
- [ ] File name format: `CALB_<ProjectName>_BESS_Proposal_<YYYYMMDD>_V2.1.docx`

### Diagrams Quality
- [ ] SLD: DC BUSBAR per PCS clearly separated
- [ ] SLD: DC block count matches allocation
- [ ] Layout: All containers readable (no overlaps)
- [ ] Layout: Module grid properly formatted
- [ ] Both images embedded in DOCX (not missing)

### Edge Cases
- [ ] Test with custom PCS rating (2000 kW or manual entry)
- [ ] Test with mismatched DC/AC (10 DC blocks, 2 AC blocks)
- [ ] Test with 1-year project (guarantee_year=1)
- [ ] Test with 0-year project (guarantee_year=0)

---

## 📞 Key Test Data Files

If you have reference data, place in:
```
tests/golden_inputs/
├─ test_scenario_75mw_300mwh.json
├─ test_scenario_small_10mw_50mwh.json
└─ reference_outputs/
   ├─ dc_results.json
   ├─ ac_results.json
   └─ combined_results.json
```

Run comparison:
```bash
python3 tools/docx_diff_report.py outputs/reports/latest.docx reference_outputs/expected.docx
```

---

## 🎯 Success Criteria

✅ **PASS** if:
1. All Executive Summary fields populated correctly
2. Stage 3 annual degradation table visible below graph
3. SLD shows independent DC busbar per PCS
4. Layout shows 1×6 module arrangement
5. No empty fields or debug text in DOCX
6. Report file created with correct naming convention
7. All images (SLD + Layout) embedded in DOCX

❌ **FAIL** if:
1. Any field empty or showing placeholder value
2. Guarantee Year mismatch between sections
3. SLD shows wrong DC block counts or shared busbar
4. Layout shows 2×3 or 3×2 module arrangement
5. "aa" or other debug text visible
6. Report file not created or corrupted

---

## 📝 Log & Debug

Monitor console output:
```bash
# Watch Streamlit logs
tail -f ~/.streamlit/logs/

# Check report generation
cat /opt/calb/prod/CALB_SIZINGTOOL/outputs/reports/export.log

# Diagram generation
cat /opt/calb/prod/CALB_SIZINGTOOL/outputs/diagrams/generation.log
```

---

**Test Status:** Ready to Execute  
**Last Updated:** 2026-01-05  
**Test Coverage:** Complete workflow (Project → DC → AC → Diagrams → Export)

Good luck! 🚀
