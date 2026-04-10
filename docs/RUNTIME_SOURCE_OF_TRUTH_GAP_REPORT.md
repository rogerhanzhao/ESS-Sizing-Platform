# Runtime Source of Truth Gap Report

Date: 2026-04-10
Scope: Current Streamlit runtime data flow

## Source of Truth Inventory

### DB as primary (DC only)
- DC run persistence + restore: DB snapshots are authoritative and can rebuild a DC run by run_id. Evidence: [run_persistence_service.py](D:/CALB_SizingTool/calb_sizing_tool/services/run_persistence_service.py), [run_restore_service.py](D:/CALB_SizingTool/calb_sizing_tool/services/run_restore_service.py), [run_history_view.py](D:/CALB_SizingTool/calb_sizing_tool/ui/run_history_view.py), [dc_view.py](D:/CALB_SizingTool/calb_sizing_tool/ui/dc_view.py)

### Session as primary (AC / SLD / Layout / Report)
- AC sizing still reads `stage13_output` and `dc_result_summary` from `session_state`. Evidence: [ac_view.py](D:/CALB_SizingTool/calb_sizing_tool/ui/ac_view.py)
- SLD and Layout read `stage13_output`, `dc_result_summary`, `ac_output` from `session_state`. Evidence: [single_line_diagram_view.py](D:/CALB_SizingTool/calb_sizing_tool/ui/single_line_diagram_view.py), [site_layout_view.py](D:/CALB_SizingTool/calb_sizing_tool/ui/site_layout_view.py)
- Report export reads layout/diagram outputs and `stage13_output` from `session_state`. Evidence: [report_export_view.py](D:/CALB_SizingTool/calb_sizing_tool/ui/report_export_view.py)

### Mixed / cache state
- Projects/Cases/Run history use DB records, but active selection is stored in `session_state`. Evidence: [projects_view.py](D:/CALB_SizingTool/calb_sizing_tool/ui/projects_view.py), [cases_view.py](D:/CALB_SizingTool/calb_sizing_tool/ui/cases_view.py), [run_history_view.py](D:/CALB_SizingTool/calb_sizing_tool/ui/run_history_view.py)

## Dual-Write / Dual-Source Risks
- `stage13_output` is regenerated from DC snapshots but then used as the source for AC/SLD/Layout and report export, creating drift risk if session is stale or overwritten. Evidence: [session_state_adapter.py](D:/CALB_SizingTool/calb_sizing_tool/adapters/session_state_adapter.py), [ac_view.py](D:/CALB_SizingTool/calb_sizing_tool/ui/ac_view.py), [single_line_diagram_view.py](D:/CALB_SizingTool/calb_sizing_tool/ui/single_line_diagram_view.py)
- `dc_result_summary` is cached in session and used across pages, not rehydrated by run_id on every page. Evidence: [dc_view.py](D:/CALB_SizingTool/calb_sizing_tool/ui/dc_view.py), [report_export_view.py](D:/CALB_SizingTool/calb_sizing_tool/ui/report_export_view.py)
- Layout/Diagram results live only in session (SVG/PNG bytes, spec JSON). Evidence: [site_layout_view.py](D:/CALB_SizingTool/calb_sizing_tool/ui/site_layout_view.py), [single_line_diagram_view.py](D:/CALB_SizingTool/calb_sizing_tool/ui/single_line_diagram_view.py)

## Recommended Drift Elimination Steps
- Phase D: AC/SLD/Layout must read DC outputs from DB snapshots by run_id instead of `stage13_output` and session-only values.
- Persist AC/SLD/Layout artifacts in `artifact_registry` tied to run_id and snapshot hashes.
- Make `session_state_adapter.py` explicitly legacy-only, and remove it from new flows once DB-based reads are in place.
- Centralize summary building from DB snapshot payloads to avoid multiple summary formats.

## Local Runtime Note
- A local SQLite DB file exists under `var/` and is not tracked by git. Evidence: [calb_sizing.sqlite](D:/CALB_SizingTool/var/calb_sizing.sqlite)
