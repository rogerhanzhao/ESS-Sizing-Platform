# Functional Test Plan V1 - Browser Acceptance

Date: 2026-07-14

Scope: CALB Sizing Tool local browser acceptance for the primary Project -> Case -> Run workflow. The test target is the local isolated instance, not the production server database.

## 1. Test Environment

- Repo: `D:\CALB_SizingTool`
- Branch: `ops/ubuntu-docker-coexist-20260311`
- Local URL: `http://127.0.0.1:8599`
- Database: `var/_uitest_copy.sqlite`
- Runtime env:
  - `CALB_DATABASE_URL=sqlite:///D:/CALB_SizingTool/var/_uitest_copy.sqlite`
  - `CALB_OPLOG_ENABLED=false`
- Test account: `uitest_admin` / local test password
- Source run used for regression: project `test`, case `test-case`, run `4ffb9a93-7f05-49f3-a153-3846e322acc3`

## 2. Acceptance Outline

### Authentication and Workspace

- Login as admin.
- Confirm current project, case, and run context are visible.
- Restore latest run from Workbench.
- Confirm DC Sizing opens with the restored POI, lifetime, efficiency, scenario, and advanced input values.
- Confirm downstream buttons unlock only after an active run is restored.

### AC Sizing

- Open AC Sizing from restored run.
- Confirm DC block count, target power and target energy are restored from persisted run data.
- Confirm saved AC runtime snapshot is displayed.
- Confirm AC Block Model selection restores the persisted model or legacy PCS signature before re-running.
- Run AC Sizing.
- Pass criteria:
  - no crash or logout,
  - no `Insufficient power` error for the known-good restored run,
  - AC Blocks = 94,
  - AC Block Model = `ACBLK-2X2500KW-20FT` or equivalent legacy `2 x 2500 kW` signature,
  - PCS per Block = 2,
  - PCS Rating = 2500 kW,
  - Total AC Power = 470.00 MW,
  - configuration is saved.

### Single Line Diagram

- Open Single Line Diagram from the active run.
- Confirm runtime data source is authoritative persisted mode.
- Generate SLD.
- Pass criteria:
  - concept SLD artifacts are generated and registered,
  - downloads are available,
  - no `1~2 BESS containers` range label,
  - no `F3=0` / `F4=0` dangling PCS allocation text,
  - formal readiness failures keep output as Concept / Not for Construction rather than pretending to be construction-ready.

### Typical AC Block Arrangement

- Open Typical AC Block Arrangement.
- Confirm the page states this is not a site plan or construction drawing.
- Confirm Master Layout is blocked without a Site Constraint Set.
- Generate Typical AC Block Arrangement.
- Pass criteria:
  - concept artifacts and downloads are generated,
  - output remains marked `CONCEPT ONLY - NOT FOR CONSTRUCTION`,
  - no site boundary, access route, fire lane, POI routing, or clearance is invented.

### Report Export

- Open Report Export from the active run after AC, SLD, and Typical AC Block Arrangement are generated.
- Confirm content preview recognizes:
  - DC Sizing,
  - AC Sizing,
  - SLD Image,
  - Typical AC Block Arrangement (Concept Only).
- Download Combined Report V2.1.
- Pass criteria:
  - report generation triggers a download,
  - no page error,
  - report page keeps Concept Only boundary for Typical AC Block Arrangement.

### Admin and History Pages

- Open Product & Database dashboard.
- Switch to Cells and AC Blocks.
- Confirm no DuplicateWidgetID or render abort.
- Open Project Directory, Case Directory, Engineering Settings, and Run Registry.
- Pass criteria:
  - each page renders without traceback,
  - AC Block Templates count is visible and currently 0.

## 3. Issues Found and Fixed

### FT-20260714-01 - Restored run AC Sizing used zero DC blocks

Symptom:

- Restoring the known-good 400 MW / 800 MWh run showed `DC Blocks: 0 x 20ft`.
- Clicking `Run AC Sizing` produced `Insufficient power: 0.0 MW < 400.0 MW`.

Root cause:

- `build_dc_result_summary()` exposed the canonical `dc_blocks_total` field, but the legacy AC page still reads `total_blocks`, `container_count`, and `cabinet_count` from session state.

Fix:

- Added legacy restore aliases in `calb_sizing_tool/adapters/session_state_adapter.py`.
- Added regression assertions in `tests/unit/test_workspace_state.py`.

### FT-20260714-02 - Restored run AC Sizing did not restore PCS/model selection

Symptom:

- The restored AC snapshot correctly displayed `2 PCS / 2500 kW / 470.00 MW`.
- The editable selector still defaulted to `2 x 1250kW = 2500kW`, making the form recalculate `235.00 MW`.

Root cause:

- The AC page restored the saved AC output panel, but did not map `pcs_per_block + pcs_kw` back into the selectbox default.

Fix:

- Added `_saved_pcs_choice_index()` in `calb_sizing_tool/ui/ac_view.py`.
- Added `_saved_ac_block_model_choice_index()` for the simplified AC Block Model dropdown.
- Added `tests/unit/test_ac_view_restore_defaults.py`.

### FT-20260714-03 - AC Block product records are empty, so AC Sizing needed a clear interim model selector

Symptom:

- Product & Database showed `AC Block Templates = 0`.
- AC Sizing still exposed the old PCS-centered selector, which made it unclear whether the user was selecting PCS only or an AC Block model.

Fix:

- Added simplified AC Block model options derived from the existing PCS recommendation library.
- Changed the AC page selector to `Select AC Block Model`.
- Added output trace fields: `ac_block_model_code`, `ac_block_model_name`, `ac_block_model_source`, `ac_block_container_type`, and `ac_block_quantity_basis`.
- Kept the existing downstream contract fields unchanged: `pcs_per_block`, `pcs_kw`, `block_size_mw`, and `total_ac_mw`.

### FT-20260714-04 - Container rule incorrectly treated four PCS as 40ft

Symptom:

- `4 x 1250 kW` is exactly `5.00 MW` per AC Block but was generated as a `40ft` simplified model.

Root cause:

- The container selector combined the valid power threshold with an unsupported `PCS >= 4` condition.

Fix:

- The container selector now uses only one AC Block's power: `> 5 MW` is `40ft`; `<= 5 MW` is `20ft`.
- Old saved `ACBLK-4X1250KW-40FT` selections recover through their PCS signature as `ACBLK-4X1250KW-20FT`.

### FT-20260714-05 - Restored run did not repopulate DC case inputs

Symptom:

- The run result and voltage were restored, but the DC Sizing form continued to show defaults or the previous Case values.

Root cause:

- Restore only rebuilt runtime result aliases; it did not map the persisted `dc_case_input` payload back to the DC widget state.
- Run History also stayed on the registry page after restore, so the input form was not visible.

Fix:

- Restore now repopulates the persisted editable DC input payload, including scenario switches and advanced efficiency fields.
- Workbench and Run History restore actions route to DC Sizing after the state update.
- Switching Project or Case clears stale DC widget state before the new context is opened.

### FT-20260714-06 - Case input was not kept as the current working configuration

Symptom:

- A newly created Case had an empty `input_json`, and later successful Runs did not update that Case record.

Fix:

- A successful DC Run now updates the Case working input JSON while retaining the Run input snapshot as the immutable historical record.

## 4. Current Findings Requiring Business Confirmation

- `Product & Database -> AC Blocks` is empty (`AC Block Templates = 0`). This is not a render failure, but it means AC sizing cannot yet use governed AC Block product records as the source of truth.
- Until product records are confirmed, AC Sizing uses a simplified AC Block Model dropdown derived from PCS count and rating.
- Adding 5 MW / 10 MW AC Block templates requires business confirmation of PCS configuration, LV winding count, transformer MVA, LV/MV voltage, impedance, and manufacturer/product basis.
- The current Project -> Case -> Run boundary remains: Case creation stores identity and scenario metadata; DC Sizing creates the first technical input set; each Run retains its own historical snapshot, while the Case record reflects the latest successful working input.

## 5. Executed Browser Checks

- Login: passed.
- Workbench latest-run restore: passed.
- Restored DC input form values: covered by unit regression tests; browser acceptance should confirm the visible values after routing to DC Sizing.
- AC Sizing restored-run recalculation after fix: passed.
- SLD generation: passed as Concept / Not for Construction.
- Typical AC Block Arrangement generation: passed as Concept Only.
- Report V2.1 download: passed.
- Admin Dashboard / Cells / AC Blocks: passed.
- Project Directory / Case Directory / Engineering Settings / Run Registry: passed.

## 6. Verification Commands

```powershell
python -m compileall -q calb_sizing_tool tests
python -m pytest tests\unit\test_ac_view_restore_defaults.py tests\unit\test_workspace_state.py -q
python -m pytest tests\unit\test_ac_sizing_service.py -q
python -m pytest tests\integration\test_run_restore_from_history.py tests\integration\test_dc_run_persist_and_restore.py -q
```
