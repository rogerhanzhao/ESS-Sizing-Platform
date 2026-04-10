# Quick Start Guide - CALB BESS Sizing Tool v2.1

## System Status

✅ **All systems operational and ready for production**

- **Prod Instance**: Running on port 8511
- **Test Instance**: Running on port 8512
- **Feature Branch**: `fix/report-export-consistency-v2.1` pushed to GitHub
- **Status**: Verified and production-ready

## 1. Starting the Application

### Option A: Streamlit Direct (Already Running)
The application is already running:
```bash
# Check if running
ps aux | grep streamlit

# You should see two processes:
# - Prod (port 8511)
# - Test (port 8512)

# Access via:
# Prod: http://localhost:8511
# Test: http://localhost:8512
```

### Option B: Manual Start (if needed)
```bash
cd /opt/calb/prod/CALB_SIZINGTOOL
source .venv/bin/activate
streamlit run app.py --server.port 8511 --server.headless true
```

## 2. Workflow: Sizing a Project

### Step 1: Dashboard
- Enter Project Name
- Enter Customer/Company
- Click "Start New Sizing"

### Step 2: DC Sizing (Stage 1-3)
- **POI Power Requirement**: Enter in MW (e.g., 100 MW)
- **POI Energy Requirement**: Enter in MWh (e.g., 400 MWh)
- **Guarantee Year**: Enter year for degradation calculation
- **Battery Parameters**: Adjust DoD, SC Loss, etc. as needed
- Click "Run DC Sizing"
- ✅ Review results

### Step 3: AC Sizing (Stage 4)
- System shows DC Block count and capacity
- Select **DC:AC Ratio** (1:1, 1:2, or 1:4)
  - This determines how many DC Blocks per AC Block
  - **Not** related to PCS count!
  
- Select **PCS Configuration**:
  - Choose from recommended options (1250, 1500, 1725, **2000**, 2500 kW)
  - Or click "Custom PCS Rating" to enter any value
  - Select number of PCS per AC Block (2 or 4)
  
- System calculates:
  - Total AC Blocks needed
  - Container type (20ft or 40ft)
  - Total AC power
  
- Click "Run AC Sizing"
- ✅ Review results

### Step 4: Generate Diagrams (Optional but Recommended)
- Go to **"Single Line Diagram"** page
  - Review SLD with proper electrical topology
  - Each PCS has independent DC BUSBAR
  
- Go to **"Site Layout"** page
  - Review DC Block layout (6 modules per block)
  - Container arrangement and spacing

### Step 5: Export Report
- Go to **"Report Export"** page
- Click **"Download AC Report"** or **"Download Combined Report"**
- File saved as: `CALB_<ProjectName>_BESS_Proposal_<YYYYMMDD>_V2.1.docx`

## 3. Key Features in v2.1

### New PCS Options
- Standard ratings: **1250, 1500, 1725, 2000, 2500 kW**
- Custom input dialog for non-standard values
- Automatic PCS count recommendation based on POI power

### AC Block Sizing
- DC:AC Ratio logic:
  - 1:1 → 1 AC Block per DC Block
  - 1:2 → 1 AC Block per 2 DC Blocks
  - 1:4 → 1 AC Block per 4 DC Blocks
- Container type auto-selection:
  - 20ft: AC Block ≤ 5 MW
  - 40ft: AC Block > 5 MW

### Report Export (V2.1)
- Unified file format: `CALB_<ProjectName>_BESS_Proposal_<YYYYMMDD>_V2.1.docx`
- Auto-generated SLD with proper electrical topology
- Auto-generated Layout with realistic container visualization
- Executive Summary with:
  - POI requirements (input)
  - Guarantee year and target
  - DC/AC configuration summary
- Efficiency chain with "No Auxiliary" disclaimer
- AC configuration table (aggregated, not per-block detail)

### Diagram Features
- **SLD**: Independent DC BUSBAR per PCS (proper electrical isolation)
- **Layout**: DC Blocks shown as 6 modules (1×6 configuration)
- Both embed in DOCX automatically

## 4. Testing the System

### Quick Test (5 minutes)
```bash
cd /opt/calb/prod/CALB_SIZINGTOOL

# Verify key files exist
python3 verify_fixes_simple.py
# Should show: 8/8 checks passed ✅
```

### Complete Test (10 minutes)
```bash
# Create test case (100 MW / 400 MWh)
# - Navigate to Dashboard
# - Enter test project details
# - DC Sizing: 100 MW, 400 MWh
# - AC Sizing: Select 1:4 ratio, 2×2500kW per AC Block
# - Generate diagrams
# - Export report
# - Verify output file exists in outputs/ directory
```

## 5. Troubleshooting

### Issue: SLD/Layout Images Not Showing
**Solution**:
1. Ensure diagrams were generated (check Single Line Diagram / Site Layout pages)
2. Check outputs directory exists: `/opt/calb/prod/CALB_SIZINGTOOL/outputs/`
3. Files should exist: `sld_latest.svg`, `layout_latest.svg`, and PNG versions

### Issue: Permission Denied on Export
**Solution**:
```bash
# Ensure outputs directory is writable
sudo chown -R calb:calb /opt/calb/prod/CALB_SIZINGTOOL/outputs
chmod 755 /opt/calb/prod/CALB_SIZINGTOOL/outputs
```

### Issue: App Won't Start
**Solution**:
```bash
# Check if port is in use
lsof -i :8511

# Kill existing process if needed
kill -9 <PID>

# Start fresh
cd /opt/calb/prod/CALB_SIZINGTOOL
streamlit run app.py --server.port 8511 --server.headless true &
```

## 6. File Structure

```
/opt/calb/prod/CALB_SIZINGTOOL/
├── app.py                          # Main entry point
├── calb_sizing_tool/
│   ├── ui/                        # Streamlit pages
│   │   ├── dc_view.py            # DC Sizing UI
│   │   ├── ac_view.py            # AC Sizing UI
│   │   └── single_line_diagram_view.py  # SLD/Layout UI
│   ├── sizing/                    # Calculation engines
│   │   └── dc_sizing.py          # DC sizing logic
│   └── reporting/                 # Report generation
│       ├── export_docx.py        # DOCX export
│       ├── report_v2.py          # V2.1 template
│       └── report_context.py     # Data snapshot
├── calb_diagrams/
│   ├── sld_pro_renderer.py       # SLD generation
│   └── layout_block_renderer.py  # Layout generation
├── outputs/                       # Generated diagrams & exports
└── docs/                          # Documentation
```

## 7. Verification Checklist

Before declaring "production ready":

- [x] Both Streamlit instances running (ports 8511, 8512)
- [x] Dashboard loads without errors
- [x] DC Sizing calculates correctly
- [x] AC Sizing with 2000kW option works
- [x] SLD generates with independent DC BUSBAR
- [x] Layout shows 6 modules per DC Block
- [x] Report exports as V2.1 format
- [x] File naming: `CALB_*_V2.1.docx`
- [x] Feature branch pushed to GitHub
- [x] Documentation complete

## 8. GitHub Status

**Feature Branch**: `fix/report-export-consistency-v2.1`  
**Status**: ✅ Pushed to remote  
**PR**: Ready to create on GitHub

**To create PR**:
1. Go to: https://github.com/rogerhanzhao/ESS-Sizing-Platform
2. Create new PR: `fix/report-export-consistency-v2.1` → `master`
3. Add title: "fix(report): Ensure data consistency and proper formatting in DOCX export"
4. Add description from GITHUB_PUSH_INSTRUCTIONS.md
5. Request review

## 9. Next Steps

**Immediate**:
1. Review and merge PR on GitHub
2. Tag as v2.1 release
3. Update deployment documentation

**Short Term**:
1. User acceptance testing
2. Gather feedback on visualizations
3. Collect sample exports for documentation

**Future**:
1. HVAC/Auxiliary sizing module
2. Advanced layout optimization
3. Multi-project comparison reports

---

**Status**: ✅ PRODUCTION READY  
**Last Updated**: 2026-01-04  
**Version**: v2.1  
**Maintained By**: CALB Engineering Team
