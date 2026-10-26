# Flexible DC product upgrade — Phase A local verification

Baseline: 05cb345. Local changes only; no GitHub push or production update.

## Implemented

- Read-only DC catalogue participation and parameter review in Product & Database → DC Block Templates.
- Uses the actual frozen picker to distinguish selected products from other active records; explains existing Published preference semantics.
- Reviews linked cell/curve status, voltage window, series/parallel fields and positive continuous power/current inputs. Does not equate these checks with engineering, duty, SOH/RTE or downstream drawing approval.
- Fixes a pre-existing ProductAdminService adapter DetachedInstanceError by materializing values while the session is open. Its six-column interface, capacity fallback and active/default flags are preserved.

## Evidence

- `python -m compileall -q app.py calb_sizing_tool calb_diagrams`: passed.
- Full final regression: **1034 passed in 508.06 seconds**.
- Real SQLAlchemy temporary-database/Streamlit AppTest rendered the full DC administration section without exceptions and verified records did not change. Adapter regression covers inactive records, unpublished records, kWh fallback and cabinet form preservation.
- Initial UI test exposed the existing detached-object bug. It was fixed and the final full suite rerun; the earlier interrupted run is not a passing result.
- Read-only audit of `var/calb_sizing.sqlite`, followed by an independent SQLite backup and actual service smoke test, returned four products. Diagnostics agree with the legacy picker. Original local data was not corrected from product-name inference.
- Earlier browser QA database `output/local_web_20261017_human/qa.sqlite` has zero DC product records. It is not the audited catalogue and is not production.
- Frozen seven sizing modules and `calb_diagrams` diff empty. `git diff --check` clean.

Artifacts: `output/flexible_dc_local_20261020/full-regression.txt`, `catalogue-readiness.json`, `产品参数审计.md`, `local-product-audit.json`, `isolated-qa-product-audit.json`. Customer/database artifacts are not for Git commits.

## Limits and next gate

AppTest is a Streamlit rendering/interaction simulation, not a human browser click inspection. No live browser or production verification is claimed for this phase. No new activation lifecycle, mixed-container search, AC allocation, SLD, layout or report generation capability has been enabled. Those follow the staged roadmap and require their own passing tests and rendered-output inspection before proceeding.
