# CALB ESS Sizing Tool: Reporting and Diagram Generation

This document describes how to use the reporting and diagram generation features in the CALB ESS Sizing Tool v2.1.

## Overview

The tool generates four key outputs:
1. **DC Sizing Report** (V1 stable format)
2. **AC Sizing Report** (V1 stable format)
3. **Combined Report** (V1 or V2.1 beta format)
4. **Single Line Diagram (SLD)** with optional PNG export
5. **Typical AC Block Arrangement (Concept Only)** with optional PNG export

## Workflow

### 1. Running the Application

```bash
cd /opt/calb/<environment>/CALB_SIZINGTOOL
streamlit run app.py --server.address 0.0.0.0 --server.port 8511 --server.headless true
```

Or use the systemd service:
```bash
systemctl start calb-sizingtool@prod
```

### 2. DC Sizing (Stage 1–3)

1. Navigate to **DC Sizing** page
2. Enter project inputs:
   - POI Power Requirement (MW)
   - POI Energy Requirement (MWh) — this is the guarantee target
   - POI Guarantee Year
   - Other sizing parameters
3. Select a scenario (usually "container_only")
4. Click **Run Stage 1–3 Sizing**
5. Results are automatically saved to `st.session_state["dc_results"]`

**Key fields saved:**
- `dc_results["stage13_output"]` — stage1, stage2_raw, and stage3 metadata
- `dc_results["dc_result_summary"]` — quick reference values

### 3. AC Sizing (Stage 4)

1. Navigate to **AC Sizing** page
2. Ensure DC sizing is complete
3. Enter AC-specific parameters:
   - Grid voltage (MV level)
   - LV voltage selection
   - PCS modules per block
   - Transformer rating
4. Click **Run AC Block Sizing**
5. Results are saved to `st.session_state["ac_results"]`

**Key fields saved:**
- `ac_results["num_blocks"]` — number of AC blocks
- `ac_results["pcs_count_by_block"]` — PCS distribution
- `ac_results["block_size_mw"]` — AC block size

### 4. Single Line Diagram Generation

1. Navigate to **Single Line Diagram** page
2. Prerequisite: Complete DC and AC sizing
3. Configure diagram inputs (optional):
   - DC blocks per feeder
   - Transformer rating (auto-filled)
   - PCS rating (auto-filled)
   - Zoom level
4. Choose rendering style:
   - **Pro English V1.0** — Engineering style (recommended)
   - **Raw V0.5** — Minimal style
5. Click **Generate SLD**
6. Diagram outputs are saved:
   - `st.session_state["diagram_results"]` — contains SVG and PNG bytes
   - `st.session_state["sld_snapshot"]` — metadata for SLD version tracking
7. Download options:
   - SVG (vector, editable in Inkscape)
   - PNG (raster, for reports)

**Troubleshooting:**
- If you see a "First-click error" on the DC blocks table, refresh the page
- If SLD fails to generate, ensure svgwrite is installed: `pip install svgwrite`
- For PNG export, ensure cairosvg is installed: `pip install cairosvg`

### 5. Typical AC Block Arrangement Generation

1. Navigate to **Typical AC Block Arrangement** page
2. Prerequisite: Complete DC and AC sizing
3. Click **Generate Typical AC Block Arrangement**
4. Layout outputs are saved:
   - `st.session_state["layout_results"]` — contains SVG and PNG bytes
5. Download SVG or PNG

### 6. Report Export

#### V1 (Stable)

1. Navigate to **Report Export** page
2. Select **Report Template: V1 (Stable)**
3. Download options:
   - AC Report — AC sizing section only
   - Combined Report — DC sizing + AC sizing + summary
4. File format: DOCX (Microsoft Word)

#### V2.1 (Beta)

1. Navigate to **Report Export** page
2. Select **Report Template: V2.1 (Beta)**
3. The report will:
   - Use the **ReportContext** (single source of truth)
   - Embed SLD PNG if available (otherwise shows note)
   - Embed Layout PNG if available (otherwise shows note)
   - Include Stage 3 degradation analysis
   - Show QC checks and warnings
4. Download **Combined Report V2.1 (Beta)**

**V2.1 Report Sections:**
1. Cover page
2. Conventions & Units
3. Executive Summary (inputs + guarantee + results)
4. Stage 1: POI Requirements
5. Stage 2: DC Block Sizing
6. Stage 3: Degradation & Deliverable at POI
7. Stage 4: AC Block Sizing
8. Single Line Diagram (embedded PNG)
9. Block Layout (embedded PNG)
10. QC Checks and Warnings

## Data Flow and Session State

### Key Session State Fields

```python
st.session_state = {
    "project_name": str,
    "dc_results": {
        "stage13_output": {...},  # Stage 1–3 outputs
        "dc_result_summary": {...},
        "results_dict": {...},
        "report_order": [...]
    },
    "ac_results": {
        "num_blocks": int,
        "pcs_count_by_block": [...],
        "block_size_mw": float,
        ...
    },
    "diagram_results": {
        "last_style": str,
        "pro_v10": {"svg": bytes, "png": bytes},
        "raw_v05": {"svg": bytes, "png": bytes},
        ...
    },
    "layout_results": {
        "last_style": str,
        "raw_v05": {"svg": bytes, "png": bytes},
        ...
    },
    "sld_snapshot": {
        "snapshot_id": str,
        "snapshot_hash": str,
        "generated_at": str,
        "ac_block": {"group_index": int}
    }
}
```

### ReportContext Building

When exporting the V2.1 report, the system builds a `ReportContext` object that serves as the single source of truth:

```python
from calb_sizing_tool.reporting.report_context import build_report_context

ctx = build_report_context(
    session_state=st.session_state,
    stage_outputs={
        "stage13_output": stage13_output,
        "stage2": stage13_output.get("stage2_raw", {}),
        "ac_output": ac_output,
        "sld_snapshot": st.session_state.get("sld_snapshot"),
    },
    project_inputs={
        "poi_power_mw": stage13_output.get("poi_power_req_mw"),
        "poi_energy_mwh": stage13_output.get("poi_energy_req_mwh"),
        "poi_energy_guarantee_mwh": stage13_output.get("poi_energy_req_mwh"),
        "poi_guarantee_year": stage13_output.get("poi_guarantee_year"),
        ...
    }
)
```

The context consolidates all data and validates consistency:
- POI power matches AC blocks × block size
- DC and AC results reference correct sources
- SLD/Layout images are embedded if available
- Stage 3 degradation data is included

## Diagram File Locations

- **Latest SLD outputs**: `outputs/sld_latest.svg`, `outputs/sld_latest.png`
- **Latest Layout outputs**: `outputs/layout_latest.svg`, `outputs/layout_latest.png`
- **DOCX reports**: Downloaded directly from the browser

## Troubleshooting

### Report has missing or incorrect values

1. Check that DC sizing completed successfully (look for "POI Usable @ Guarantee Year" value)
2. Check that AC sizing completed successfully
3. Export as V2.1 to see detailed QC warnings
4. Verify `stage13_output` and `ac_output` are in session state

### SLD/Layout not embedding in report

1. Generate the SLD/Layout in the respective pages first
2. Ensure PNG export is enabled (cairosvg installed)
3. Check `outputs/sld_latest.png` and `outputs/layout_latest.png` exist
4. Re-export the report

### First-click error on SLD page

The error "StreamlitValueAssignmentNotAllowedError for key 'diagram_inputs.dc_blocks_table'" indicates a widget key conflict.

**Solution**: Refresh the page and try again. The fix ensures the session state is initialized before the widget is created.

### Text overlaps in SLD/Layout

This is a rendering improvement task. The current version has:
- Equipment labels placed above/below components
- DC block labels inside the container
- Allocation text in a dedicated note box

Improvement roadmap:
- Implement text wrapping with `<tspan>` elements
- Add collision detection to avoid overlaps
- Use dedicated label zones outside diagram areas

## Dependencies

### Required
- `streamlit` — UI framework
- `pandas` — Data handling
- `python-docx` — DOCX generation
- `openpyxl` — Excel data reading

### Optional (for diagrams and report images)
- `svgwrite` — SVG generation (required for SLD/Layout)
- `cairosvg` — PNG export from SVG (recommended for embedded images)
- `pypowsybl` — PowSyBl-based SLD (legacy, not used in Pro renderer)

### Optional (for development/testing)
- `pytest` — Test framework

Install optional dependencies:
```bash
pip install svgwrite cairosvg pypowsybl pytest
```

## Notes for Developers

### Report Context Validation

The `validate_report_context()` function checks for consistency issues and returns warnings (not errors). Use it when building reports:

```python
from calb_sizing_tool.reporting.report_context import validate_report_context

ctx = build_report_context(...)
warnings = validate_report_context(ctx)
if warnings:
    st.warning(f"Report consistency checks: {len(warnings)} issue(s) found")
    for w in warnings:
        st.caption(w)
```

### Regression Testing

To compare current behavior against the master branch:

1. Check out master: `git checkout master`
2. Compare calculation logic: `git diff refactor/streamlit-structure-v1 -- calb_sizing_tool/ui/dc_view.py`
3. See `docs/regression/master_vs_refactor_calc_diff.md` for detailed comparison

### Adding New Diagram Styles

To add a new SLD or Layout style:

1. Create a new renderer function in `calb_diagrams/`
2. Register it in the Single Line Diagram / Typical AC Block Arrangement page
3. Follow naming convention: `render_<type>_<style>_svg(spec: ..., out_svg: Path, ...)`
4. Return `(svg_path, png_warning_or_none)` tuple
5. Store results in `st.session_state["diagram_results"][<style_key>]`

## Further Reading

- [Report Context Module](calb_sizing_tool/reporting/report_context.py)
- [Report V2.1 Exporter](calb_sizing_tool/reporting/report_v2.py)
- [SLD Pro Renderer](calb_diagrams/sld_pro_renderer.py)
- [Layout Block Renderer](calb_diagrams/layout_block_renderer.py)
- [Single Line Diagram UI](calb_sizing_tool/ui/single_line_diagram_view.py)
- [Typical AC Block Arrangement UI](calb_sizing_tool/ui/site_layout_view.py)
- [Report Export UI](calb_sizing_tool/ui/report_export_view.py)
