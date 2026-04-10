# GitHub Push & PR Guide - CALB Report Fixes V2.1

**Date**: 2025-12-31  
**Branch**: `ops/fix/report-stage3`  
**Target**: Production Merge

---

## Quick Start (5 minutes)

### 1. View Local Changes
```bash
cd /opt/calb/prod/CALB_SIZINGTOOL
git log --oneline -10
git status
git diff --stat
```

### 2. Push to GitHub
```bash
git push origin ops/fix/report-stage3
```

### 3. Create Pull Request
Visit: https://github.com/[user]/CALB_SIZINGTOOL/pull/new/ops/fix/report-stage3

---

## Detailed Push Instructions

### Step 1: Verify Branch & Changes

```bash
# Confirm on correct branch
git branch -v
# Expected output: * ops/fix/report-stage3  3fcc45c Add comprehensive DOCX export fix summary documentation

# View commits since branching
git log --oneline master..ops/fix/report-stage3
# Expected: 5-8 commits with report/diagram fixes

# Check for uncommitted changes
git status
# Expected: working tree clean
```

### Step 2: Fetch Latest Remote (Optional)

```bash
git fetch origin
git log --oneline origin/ops/fix/report-stage3..ops/fix/report-stage3
# If output is empty, local = remote (good)
```

### Step 3: Push to GitHub

```bash
git push origin ops/fix/report-stage3 -v

# Expected output:
# Pushing to https://github.com/[user]/CALB_SIZINGTOOL.git
# Counting objects: 45, done.
# Delta compression using up to 8 threads.
# Compressing objects: 100% (20/20), done.
# Writing objects: 100% (22/22), ...
# remote: Create a pull request for 'ops/fix/report-stage3' on GitHub by visiting:
# remote: https://github.com/[user]/CALB_SIZINGTOOL/pull/new/ops/fix/report-stage3
```

### Step 4: Verify on GitHub

1. Visit: https://github.com/[user]/CALB_SIZINGTOOL
2. Click "Branches" tab
3. Find `ops/fix/report-stage3` in list
4. Should show "X commits ahead of master"

---

## Pull Request Template

**Title**:
```
Fix: DOCX Export - Efficiency Chain Validation, AC Block Aggregation, Consistency Checks
```

**Description**:
```markdown
## Summary
This PR addresses critical issues in CALB ESS Sizing Tool's DOCX report export functionality (V2.1).

## Changes Made

### A. Efficiency Chain (One-Way) - Source of Truth
- Uses DC SIZING output as single source for all efficiency values
- No fallback defaults; missing values trigger validation warnings
- Components: DC Cables, PCS, Transformer, RMU/Switchgear, HVT/Others
- Validation: Product check (2% tolerance), range checks (0-120%)
- Report explicitly states: "exclusive of Auxiliary loads"

### B. AC Block Configuration Aggregation
- Removes duplicate rows for identical configurations
- Single entry per config with "count" field (shows total AC blocks)
- Configuration signature includes: PCS count, PCS rating (kW), AC power (MW)
- Future enhancement: Support heterogeneous blocks via pcs_count_by_block

### C. Report Consistency Validation
- Comprehensive consistency checks (power, energy, efficiency, units)
- Power overbuild: Warn only if >10% AND >0.5 MW (intentional overbuild common in BESS)
- Efficiency product: 2% relative error tolerance
- Warnings logged in QC/Warnings section (don't block export)

### D. SLD & Layout Rendering (Finalized)
- SLD: Each PCS has independent DC BUSBAR (not shared/parallel)
- Layout: DC Block interior shows 6 modules in 1×6 single row (not 2×3 grid)
- Removed misleading "COOLING" and "BATTERY" labels from interior

## Files Modified

### Core Implementation
- **calb_sizing_tool/reporting/report_v2.py** (549 lines)
  - _validate_efficiency_chain() [177-242]
  - _aggregate_ac_block_configs() [245-281]
  - _validate_report_consistency() [283-350]
  - export_report_v2_1() [353-726]

- **calb_sizing_tool/reporting/report_context.py** (17 lines)
  - Efficiency extraction from DC SIZING stage1 [208-224]

### Diagrams (No Changes - Finalized)
- calb_diagrams/sld_pro_renderer.py (Independent DC BUSBAR per PCS)
- calb_diagrams/layout_block_renderer.py (1×6 DC modules, no labels)

### Testing & Documentation
- tests/test_report_v2_enhancements.py (NEW - comprehensive tests)
- docs/REPORT_EXPORT_ENHANCEMENTS_V2.md (NEW - technical design)
- DOCX_EXPORT_FIX_SUMMARY.md (NEW - implementation guide)
- IMPLEMENTATION_VERIFICATION.md (NEW - checklist & validation)

## Acceptance Criteria

✅ **Efficiency Chain**
- [x] Uses DC SIZING stage1 as source of truth
- [x] No fallback defaults (missing values warn)
- [x] 6 rows (Total + 5 components)
- [x] Internal consistency validation (product check)
- [x] Explicit "exclusive of Auxiliary loads" note

✅ **AC Block Configuration**
- [x] No duplicate rows for identical configs
- [x] Single entry with count field
- [x] Properly aggregated from AC SIZING output

✅ **Report Consistency**
- [x] Power/energy/efficiency validation
- [x] Reasonable tolerances (10% overbuild, 2% efficiency)
- [x] Warnings in QC section (non-blocking)

✅ **SLD/Layout**
- [x] Independent DC BUSBAR per PCS
- [x] 1×6 DC Block modules (not 2×3)
- [x] Clean rendering (no overlaps, proper labels)

✅ **No Auxiliary Assumptions**
- [x] Never calculated or estimated
- [x] Explicitly stated in report
- [x] Only DC SIZING values reported

## Testing

### Unit Tests
```bash
pytest tests/test_report_v2_enhancements.py -v
pytest tests/test_report_export_fixes.py -v
```

### Manual Testing
1. Complete DC Sizing (100 MW / 400 MWh)
2. Complete AC Sizing (1:2 or 1:4 ratio)
3. Export Combined Report (V2.1)
4. Verify:
   - Efficiency Chain table (6 rows)
   - AC Block config (single summary)
   - Stage 3 data (full year-by-year)
   - SLD (independent BUSBAR per PCS)
   - Layout (1×6 DC modules)
   - No "Auxiliary" text in doc

## Related Issues
- Addresses: Stage 3 data missing from report
- Addresses: AC Block config duplication
- Addresses: Efficiency chain validation gaps
- Related: SLD DC BUSBAR independence
- Related: Layout DC Block module layout

## Breaking Changes
None. Backward compatible with existing session_state keys and sizing logic.

## Deployment Notes
- No database migrations needed
- No new dependencies
- No new environment variables
- Staging: Ready for test environment deployment
- Production: Ready for merge to main

## Reviewers
@[product-owner] @[tech-lead]
```

---

## Step 5: Create the PR

### Option A: Via GitHub UI (Recommended)

1. Go to: https://github.com/[user]/CALB_SIZINGTOOL/pull/new/ops/fix/report-stage3
2. Click "Comparing changes"
3. Verify:
   - Base: `master` (or main branch)
   - Compare: `ops/fix/report-stage3`
   - Green checkmark: "Able to merge"
4. Fill in PR Title and Description (use template above)
5. Click "Create pull request"
6. Add labels: `type: enhancement`, `area: reporting`, `priority: high`
7. Assign reviewers
8. Set milestone (if applicable)

### Option B: Via GitHub CLI

```bash
gh pr create --base master --head ops/fix/report-stage3 \
  --title "Fix: DOCX Export - Efficiency Chain, AC Block Aggregation, Consistency Checks" \
  --body "$(cat <<'EOF'
## Summary
[Copy from template above]
EOF
)" \
  --reviewer @[reviewer1],@[reviewer2]
```

---

## Step 6: Review & Merge Process

### Code Review Checklist (for Reviewers)

- [ ] Efficiency chain values come from DC SIZING, not calculated in report
- [ ] AC Block aggregation removes duplicates (no 23 identical rows)
- [ ] Consistency validation doesn't block export (warnings only)
- [ ] SLD shows independent DC BUSBAR per PCS (not shared/parallel)
- [ ] Layout DC Block shows 1×6 modules (not 2×3)
- [ ] No Auxiliary assumptions or estimates in report
- [ ] All tests pass (unit + integration)
- [ ] Documentation is clear and complete
- [ ] No breaking changes to existing logic

### Approval & Merge

```bash
# After 1-2 approvals
git log --oneline master..ops/fix/report-stage3 | wc -l
# Should show 5-8 commits

# Merge via GitHub UI:
# 1. Click "Squash and merge" (optional, for cleaner history)
#    OR "Create a merge commit" (preserves individual commits)
# 2. Confirm merge
# 3. Delete branch (optional)

# OR merge via CLI:
git checkout master
git pull origin master
git merge ops/fix/report-stage3
git push origin master

# Tag release (if applicable)
git tag -a v2.1-report-fixes -m "DOCX Export improvements: efficiency chain, AC aggregation, consistency validation"
git push origin v2.1-report-fixes
```

---

## Troubleshooting

### "Nothing to push"
```bash
# Ensure changes are committed
git status
git add -A
git commit -m "Your message"
git push origin ops/fix/report-stage3
```

### "Merge conflict with master"
```bash
# Rebase on latest master
git fetch origin
git rebase origin/master
# Resolve conflicts in editor
git add [resolved-files]
git rebase --continue
git push origin ops/fix/report-stage3 --force
```

### "Remote rejected: insufficient permission"
```bash
# Check GitHub access
gh auth status
# If needed, re-authenticate
gh auth login
```

### Tests Failed in CI
```bash
# Run locally first
pytest tests/test_report_v2_enhancements.py -v
# Fix errors, commit, push again
git add .
git commit -m "Fix test failures"
git push origin ops/fix/report-stage3
```

---

## Verification Checklist

Before pushing, verify:

- [ ] `git status` shows clean working tree
- [ ] `git log -5` shows your commits
- [ ] All changes are committed (no staged/unstaged)
- [ ] Branch is `ops/fix/report-stage3`
- [ ] Remote is `origin`
- [ ] Tests pass locally:
  ```bash
  pytest tests/test_report_v2_enhancements.py -v
  ```
- [ ] Documentation is complete and accurate
- [ ] No sensitive data in commits
- [ ] Commit messages are clear and descriptive

---

## Post-Merge Cleanup

After merge to master:

```bash
# Delete local branch
git checkout master
git branch -d ops/fix/report-stage3

# Update local master
git pull origin master

# Verify merge
git log --oneline | head -5

# Delete remote branch (optional, GitHub can auto-delete)
git push origin --delete ops/fix/report-stage3
```

---

## Success Criteria

✅ PR created and visible on GitHub  
✅ All tests pass in CI/CD pipeline  
✅ Code review approved by 1-2 reviewers  
✅ No merge conflicts  
✅ Merged to master/main branch  
✅ Branch deleted (cleanup)  
✅ Release tag created (if applicable)

---

## Support

For questions during PR process:
- Check GitHub PR comments
- Review CI/CD logs for test failures
- Reference DOCX_EXPORT_FIX_SUMMARY.md for technical details
- Contact code reviewers in Slack/email

---

**Ready to push to production! 🚀**
