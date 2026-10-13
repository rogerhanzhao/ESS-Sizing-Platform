# Supplier cell degradation candidates

Owner request: persist uploaded curves, prepare for later activation, and export
tables for detailed review. Scope: admin data management, storage, review exports.

## Workflow

Admin → Product & Database → Degradation → Supplier curve candidates.
Upload XLSX, review its source labels and SHA-256, name the candidate, then
**Save all source curves as candidate**. All source cases are saved regardless
of the currently plotted subset. The same file is idempotent by SHA-256; changed
bytes create a separate immutable candidate. A renamed identical file reuses the
first import's provenance. Refresh/new sessions reopen via **Review source**.

Download all-curves or selected-case formatted XLSX. Both use the same exporter,
with a linked contents page, annual tables alongside editable charts, separate
SOC/series and common/extended worksheets, annual detail and duty review tables.
SOC50 appears first; Power Rate 0.25/0.33/0.5 with <=2 cycles/day is the common
presentation group, not a confirmation of feasible operation. Rates have separate
printable sections. 0.1 and >2/day remain available in extended worksheets.
Retention and SOC use numeric fractions with `0.00%` display (0.7899 = 78.99%).
Missing points stay N/A; charts do not extend missing checkpoints. Long hashes,
import IDs and actor IDs are not exported. Source sheet/cell references remain
in the detailed analysis worksheet. Text is explicitly stored as text, never a
spreadsheet formula. The unchanged supplier original remains in a separately
labelled source-verification expander; it is not a formatted presentation export.

## Storage and activation boundary

Migration `20261013_0010` adds only `supplier_degradation_import`. Each immutable
row has import ID, version label, source filename/hash, original bytes,
normalized curves, actor, timestamps, candidate status. Import and audit commit
together; no active SOH profile, curve point, RTE or catalogue default is written.
Reads verify the source hash and normalized curves against the original bytes.
The database accepts candidate status only. No activate/delete/edit action is
provided in this increment.

Later activation must explicitly resolve: cell/product applicability; SOC
standby/window meaning; Power Rate and charging/discharging basis; cycle depth,
temperature and rest time; Mean/lower-limit meaning; calendar-aging inclusion;
cell-to-system measurement boundary; unsupported year ranges; old 540/year vs
source 1.5/day; missing 1.0C source cases. Activation requires a separately
approved mapping into the existing sizing data chain with version provenance.
This change does not implement that mapping or relax the frozen canon.

## Validation

Compile check passed; full suite 774 passed (235.12 s). Export/library/parser
targeted checks: 12 passed; frozen guards are included in the full suite.
Real `app.py` AppTest with a production database copy and the
original supplier XLSX passed save + fresh-session reopen: 160 curves, 965 missing
points, original-byte equality, unchanged active-table counts (12 SOH profiles,
252 SOH points, 3 RTE profiles, 57 RTE bands, 12 catalogue degradation records).
The browser-based AC smoke script could not run because Playwright was missing;
AppTest verification is not a substitute for a completed human browser test.

Formatted XLSX examples were also generated from the saved Supplier-2026.10
source (160 curves, 4,160 annual positions, 965 missing points). All numeric
retention cells have `0.00%` format, no source/import/actor hashes are exported,
and chart references preserve source values and gaps. Cell-style/chart-data
layout projections were visually inspected; this is not native Excel rendering.

The timing table assumes 100% cycle depth, equal compatible nominal rates and
two 30-minute rests. Its result is a conditional arithmetic screen, not verified
dispatch feasibility. SOC is not relabelled DOD and Lower limit is not labelled
a warranty guarantee.

## Release

Back up production database before migration. Upgrade with the new image and
`python -m alembic upgrade head`; verify candidate table and previous SOH/RTE row
counts. A rollback image must include migration `20261013_0010` even when its
application UI is the prior release: otherwise old Alembic cannot resolve the
new database revision. Prepare this forward-compatible rollback image before
migration; do not downgrade/delete candidate storage during image rollback.
