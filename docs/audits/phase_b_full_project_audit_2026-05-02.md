# Phase B Full Project Audit - 2026-05-02

## Scope

This audit keeps the core sizing rules frozen. It does not propose changing the calculation logic in:

- `calb_sizing_tool/services/stage1_service.py`
- `calb_sizing_tool/services/stage2_service.py`
- `calb_sizing_tool/services/stage3_service.py`
- `calb_sizing_tool/services/dc_pipeline_service.py`
- `calb_sizing_tool/services/ac_sizing_service.py`

The review combines:

- Codex local read-only inspection.
- Codex sub-agent read-only inspection.
- Claude Code read-only inspection, written to `var/audits/claude_phase_b_audit_20260502_rerun.txt`.
- Local DB checks against `var/calb_sizing.sqlite`.
- Targeted regression tests.

## Current Verified State

Branch and DB:

- Branch: `ops/ubuntu-docker-coexist-20260311`, ahead of origin by 5 commits at the time of review.
- Alembic head: `20260502_0006`.
- Local Streamlit: `http://127.0.0.1:8511`, HTTP 200.
- Current server command includes `--server.fileWatcherType none`.

Local DB counts:

| Table | Count | Meaning |
| --- | ---: | --- |
| `product_cell` | 6 | Brochure cells seeded, excluding 280Ah. |
| `product_dc_block` | 4 | 418kWh, 5.01596MWh, 6.26208MWh, 10.05143MWh seeded. |
| `product_asset` | 18 | 10 structured datasheets + 8 extracted brochure images. |
| `degradation_curve` | 12 | 314Ah default degradation basis seeded. |
| `product_ac_block` | 0 | Model and Admin UI exist, no real product records yet. |
| `rte_curve` | 0 | Model and Admin UI exist, no records yet. |
| `degradation_plugin` | 0 | Registry exists, no plugin records yet. |
| `sizing_run` | 15 | Existing run history remains. |

Tests run:

```powershell
python -m pytest tests\unit\test_product_admin_repository.py tests\integration\test_db_migration_roundtrip.py tests\unit\test_workspace_state.py -q
```

Result: `8 passed`.

## Phase B Implemented

Confirmed implemented:

- Admin Portal is admin-only and separate from the main navigation.
- Admin Portal sections exist for Cells, DC Blocks, AC Blocks, Product Assets, Degradation, RTE, and Plugins.
- Product DB models and migrations exist:
  - `ProductCell`
  - `ProductDCBlock`
  - `ProductACBlock`
  - `ProductAsset`
  - `DegradationCurve`
  - `RTECurve`
  - `DegradationPlugin`
- Product catalog seed service imported the current brochure-based catalog.
- DC Sizing can choose between the Excel reference library and Admin product library.
- Admin product library currently feeds only the Stage2 block dataframe contract:
  - `Dc_Block_Code`
  - `Dc_Block_Name`
  - `Block_Form`
  - `Block_Nameplate_Capacity_Mwh`
  - `Is_Active`
  - `Is_Default_Option`
- 314Ah degradation curves are seeded.
- 418kWh and 5MWh 314Ah products point to the default 314Ah degradation basis.
- Non-314 products currently have no dedicated degradation curve, which matches the temporary requirement.
- Product datasheet/image metadata is now represented by `ProductAsset`.

## Not Yet Landed

These are not bugs in the calculation engine, but they are incomplete against the full product database/proposal direction.

### Product Assets Are Not In Proposal Export

`ProductAsset` has `proposal_section`, `storage_uri`, `asset_kind`, `caption`, `data_json`, and `metadata_json`, but report/proposal generation does not query or render it.

Current state:

- Asset data exists in DB.
- Admin Portal can view/create/edit asset metadata.
- `report_context.py`, `report_v2.py`, `export_docx.py`, and `report_export_view.py` do not consume `ProductAsset`.

Needed next:

- Add a proposal-only Standard Product Information section.
- Pull selected DC block/cell assets by product code.
- Render structured datasheet data and primary product images.
- Keep this strictly presentation-only so sizing math remains unchanged.

### Degradation/RTE Product DB Is Not Used By Stage3

`stage3_service.py` still reads SOH and RTE from the active Excel bundle.

Current state:

- `DegradationCurve` is a DB library and Admin-maintained data model.
- `RTECurve` is a DB library and Admin-maintained data model.
- Neither is used by `run_stage3`.
- This is acceptable for now because the current sizing freeze says Excel remains the active calculation source.

Needed next:

- Do not wire DB curves into Stage3 directly.
- First add a read-only comparison/preview layer and contract tests.
- Only later migrate Stage3 source after baseline parity is proven.

### Plugin Registry Is Registry-Only

`DegradationPlugin` stores `name`, `version`, `entrypoint`, `schema`, and status fields. No dispatcher or simulation execution path exists.

Current state:

- Registry table and Admin UI exist.
- No plugin runner exists.
- No degradation simulation is invoked by sizing.

Needed next:

- Treat plugin rows as registered metadata, not executable simulation.
- Add validation states such as `registered`, `validated`, `enabled`.
- Add runner only after schema, sandboxing, and baseline tests are defined.

### AC Block Product Library Is Empty And Not Wired To AC Sizing

`ProductACBlock` exists, but the local DB has zero records and AC sizing does not consume this library.

Needed next:

- Seed or enter AC/PCS products.
- Decide whether AC product selection is informational, default input population, or an actual sizing source.
- Do not silently override AC sizing defaults without an explicit user choice and regression tests.

### Product Library Provenance Is Not Persisted In Runs

DC Sizing can choose Admin product library, but the persisted run input does not record a clear `block_library_source` or product catalog version.

Risk:

- A restored run can show correct numeric output but not explain whether the block source was Excel or Product DB.

Needed next:

- Add run input provenance such as:
  - `dc_block_library_source`
  - `product_catalog_version`
  - selected `product_dc_block.block_code`
  - selected `product_cell.cell_code`

## Architecture Risks

### Startup Mutates Schema

`app.py` runs `Base.metadata.create_all()` at startup and also tries to add `product_dc_block.block_form` manually.

Risk:

- Alembic and runtime schema creation can diverge.
- A fresh environment can appear to work without migration discipline.
- Existing DBs may miss future columns because `create_all()` does not alter existing tables.

Recommendation:

- Keep Alembic as the only schema authority.
- Remove runtime `ALTER TABLE` once local DBs have been migrated.
- If a dev bootstrap remains, make it explicit and not part of normal app startup.

### SQLite Foreign Keys Are Not Enforced

Local SQLite reports `PRAGMA foreign_keys = 0`. The current DB has one `user_account` but five `user_role_binding` rows, meaning previous temporary users left dangling role bindings.

Risk:

- Local cleanup and tests can leave orphaned auth/product references.
- Cascades declared in SQLAlchemy models are not enforced by SQLite unless PRAGMA is enabled per connection.

Recommendation:

- Enable SQLite foreign keys in `create_engine_for_url()` using a connect event.
- Add a small DB hygiene check.
- Clean local orphan rows after confirming they are temporary visual-check users.

### Session Auth Is Not Revalidated Against DB

`AuthContext` stores roles in `st.session_state`. After login, pages trust session roles.

Risk:

- If a role is changed in the DB, the active browser session may keep old permissions until logout or session reset.

Recommendation:

- For admin-only actions, re-check admin role from DB or add a short-lived auth refresh.
- Keep UI session state for convenience, but do not use it as the only authority for admin mutations.

### Case Uniqueness Ignores Stage Scope

`create_case_if_needed()` de-duplicates by `project_id + case_code + scenario_mode`, not `stage_scope`.

Risk:

- Fine today because active cases are DC-oriented.
- Future AC or report-stage cases could collide with DC cases.

Recommendation:

- Include `stage_scope` in the lookup when stage-specific cases become real.

### Session Scope Creates A New Engine Per Call

`session_scope()` creates a new SQLAlchemy engine through the factory chain each time.

Risk:

- Functional on SQLite, but inefficient under Streamlit reruns.
- Makes DB behavior harder to reason about once the app uses more concurrent sessions.

Recommendation:

- Cache engines per DB URL.

## Workflow And UX Risks

### Run IDs Are Still Manually Editable In Some Pages

Workbench provides a proper project/case/run picker. SLD and Site Layout still expose raw Run ID text inputs for registered users.

Risk:

- Users can paste or keep stale run IDs.
- The app has validation in SLD, but the interaction model is still less safe than using active workspace state.

Recommendation:

- Registered users should use active workspace run as read-only default.
- If override is needed, put it behind an advanced expander.

### Site Layout Is Less DB-Authoritative Than SLD

SLD validates AC snapshot provenance against active run/case/project. Site Layout still builds more from session/project state.

Recommendation:

- Bring Site Layout to the same persisted AC snapshot and active-run validation pattern as SLD.

### Product Admin Portal Is Too Dense For Mobile

Admin forms use 3, 4, and 5 column layouts. On narrow screens this is physically hard to read and edit.

Recommendation:

- Convert large forms into grouped tabs or sections.
- Use 1 column on mobile, 2 columns on tablet, and 3 columns only on desktop.
- Add upload/import workflows instead of making users type every product field.

### No Bulk Import Or File Upload In Admin Portal

The only batch import path is the seed script. Admin Portal has no CSV/Excel upload and asset records are metadata-only entry forms.

Recommendation:

- Add CSV/Excel import preview with validation.
- Add file uploader for datasheets/images and store managed paths plus hashes.

## UI Root Cause For "Changed But Page Did Not Change"

There are three confirmed causes.

### 1. Streamlit File Watcher Is Disabled

`.streamlit/config.toml` and Docker startup set `fileWatcherType = "none"`.

Effect:

- Editing Python or CSS files does not update the page until the server process is restarted.
- Browser refresh alone is not enough.

### 2. The Local Start Script May Reuse An Old Process

`scripts/start_local_web.ps1` exits successfully if something matching `streamlit run app.py` is already listening on port 8511.

Effect:

- If an old process is still running, the script can say the app is running without starting the new code.

Recommendation:

- Add a restart script that kills only the verified CALB Streamlit process on 8511 and starts a fresh one.
- Add a visible or hidden build marker to Workbench/Admin pages so the running source can be verified.

### 3. The Earlier Workbench Title Bug Was Real CSS Geometry

The old title used too-tight height/line-height behavior. The current source uses a `div.wb-page-title`, explicit line-height, min-height, and `overflow: visible`.

If the browser still shows lowercase/clipped `workbench`, it is almost certainly not rendering the current `workbench_view.py` source, or it is running stale CSS from an old process/session.

Verification target:

- Current source marker: `workbench-toolbar-20260502-0006`.

## Priority Plan

### P0 - Do Not Break Sizing

- Keep Stage1/Stage2/Stage3/DC pipeline/AC sizing calculation logic frozen.
- Any product DB integration must be adapter-level and covered by contract tests.

### P1 - Close Phase B Business Gaps

- Add ProductAsset to proposal export as a product-information-only chapter.
- Add run provenance for selected product library/source.
- Add contract tests for ProductDCBlock to Stage2 dataframe conversion.
- Add file storage policy for product datasheets/images.

### P2 - Stabilize Architecture

- Move schema changes out of app startup and into Alembic-only flow.
- Enable SQLite FK enforcement and clean orphaned local auth rows.
- Cache DB engines per URL.
- Revalidate admin role for admin mutations.
- Align Site Layout with active run and persisted AC snapshot logic.

### P3 - UI And Admin UX

- Refactor Admin Portal forms into responsive grouped sections.
- Add CSV/Excel import preview and validation.
- Add asset upload and product preview.
- Add multi-width visual checks for Workbench, Admin Portal, DC, AC, SLD, Layout, and Report.

## Suggested Execution Order

1. Stabilize dev/runtime truth: restart script, build markers, migration discipline, FK enforcement.
2. Add ProductAsset proposal chapter without touching sizing math.
3. Add product-library provenance into run snapshots.
4. Add Admin import/upload ergonomics.
5. Add read-only Degradation/RTE comparison views.
6. Only after baseline parity, decide whether DB curves can replace Excel as the Stage3 source.

