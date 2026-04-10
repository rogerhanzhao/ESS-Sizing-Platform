# Root Documentation Audit

Cleanup date: 2026-04-10

Goal: keep the repository root focused on runnable project assets and move historical, temporary, or one-off documents out of the way.

## Kept At Root

- `README.md`: primary project entry point

## Promoted To Active Docs

- `QUICK_START_v2.1.md` -> `docs/QUICK_START.md`
- `RELEASE_NOTES_v2.1.md` -> `docs/releases/v2025.12.30-v2.1.md`
- `SYSTEM_AUDIT_REPORT_20250105.md` -> `docs/audits/system_audit_2026-01-05.md`

These files still have ongoing reference value, but they do not belong in the repository root.

## Archived As Legacy Or One-Off Material

Archived to `docs/archive/root-legacy/`:

- repair proposals and fix plans
- implementation summaries and final status reports
- verification checklists and test execution notes
- GitHub push and PR preparation notes
- version-specific temporary quick starts
- text manifests and visual reference notes

Files archived:

- `00_START_HERE.md`
- `AC_SIZING_FIXES.md`
- `CHANGES_SUMMARY.md`
- `CHANGES_SUMMARY_2000KW.txt`
- `COMPREHENSIVE_FIX_PLAN.md`
- `DEPLOYMENT_CHECKLIST_2000KW.md`
- `DEPLOYMENT_READY_SUMMARY.md`
- `DIAGRAM_FIXES_DETAILED.md`
- `DOCUMENTATION_INDEX.md`
- `DOCX_EXPORT_COMPREHENSIVE_FIX.md`
- `DOCX_EXPORT_FIX_SUMMARY.md`
- `DOCX_REPORT_FIX_GUIDE.md`
- `FINAL_CHANGES_DETAIL.txt`
- `FINAL_CHECKLIST.md`
- `FINAL_IMPLEMENTATION_REPORT.md`
- `FINAL_IMPLEMENTATION_STATUS.md`
- `FINAL_STATUS_REPORT.md`
- `FINAL_SYSTEM_STATUS.md`
- `FINAL_TEST_SUMMARY.txt`
- `FINAL_VERIFICATION_REPORT.md`
- `FIXES_COMPLETE.md`
- `FIXES_SUMMARY.md`
- `FIX_INDEX.md`
- `GITHUB_PR_TEMPLATE.md`
- `GITHUB_PUSH_GUIDE.md`
- `GITHUB_PUSH_INSTRUCTIONS.md`
- `GITHUB_PUSH_NOTES.md`
- `GIT_PUSH_READY.txt`
- `IMPLEMENTATION_CHECKLIST.md`
- `IMPLEMENTATION_COMPLETE.md`
- `IMPLEMENTATION_COMPLETE.txt`
- `IMPLEMENTATION_COMPLETE_FINAL.md`
- `IMPLEMENTATION_NOTES.md`
- `IMPLEMENTATION_SUMMARY.md`
- `IMPLEMENTATION_SUMMARY_FINAL.md`
- `IMPLEMENTATION_VERIFICATION.md`
- `IMPLEMENTATION_VERIFICATION_CHECKLIST.md`
- `IMPLEMENTATION_VERIFICATION_FINAL.md`
- `PCS_RATING_UPDATE.md`
- `PR_DESCRIPTION.md`
- `PROPOSAL_MANIFEST.txt`
- `PUSH_READINESS_CHECKLIST.md`
- `QUICK_START_2000KW.md`
- `QUICK_TEST_GUIDE.md`
- `README_2000KW.md`
- `README_FINAL_STATUS.md`
- `REPAIR_PROPOSAL.md`
- `REPAIR_SUMMARY.txt`
- `REPORT_EXPORT_FIXES_QUICK_REFERENCE.md`
- `REPORT_EXPORT_FIX_PLAN.md`
- `REPORT_EXPORT_IMPLEMENTATION_SUMMARY.md`
- `REPORT_FIXES_IMPLEMENTATION.md`
- `REVIEW_CHECKLIST.md`
- `SESSION_COMPLETION_SUMMARY.txt`
- `START_HERE.md`
- `TECHNICAL_FIXES_SUMMARY.md`
- `TEST_EXECUTION_INDEX.md`
- `VERIFICATION_CHECKLIST.md`
- `VERIFICATION_COMPLETE.md`
- `VISUAL_REFERENCE.txt`
- `_TEST_DOCUMENTS_README.txt`

## Removed As Junk Or Generated Artifacts

- interpreter caches: `__pycache__/`
- pytest cache: `.pytest_cache/`
- generated outputs and runtime logs under `outputs/`
- local editor folder `.vscode/`
- root-level ad-hoc verification scripts superseded by `tests/`

Removed scripts:

- `run_tests.sh`
- `test_ac_sizing_logic.py`
- `test_pcs_2000kw.py`
- `test_system_comprehensive.py`
- `verify_fixes_simple.py`
