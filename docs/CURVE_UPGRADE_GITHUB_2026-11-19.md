# Curve upgrade — scoped GitHub code synchronization

Owner authorization: push the current verified local work to GitHub. Branch:
`ops/ubuntu-docker-coexist-20260311`. This synchronization does not deploy production.

## Included change

- Immutable SOH/RTE packages and a separately revision-checked default binding.
- Administrator RTE working drafts, calculation provenance, complete-version
  publication and stopping new use, with explicit application or rollback of the default.
- Original SIZING entry, saved input packages, restoration checks, report provenance
  and reduced-string comparison adapters retain the selected data basis.
- Read-only annual and source previews use optional local refresh; the project
  selector and DC result share Admin display names and condition ordering.
- Administrator maintenance instructions distinguish curve version workflows from
  ordinary mutable product records and disclose existing status-consumer limits.
- Migrations `20261118_0014` and `20261118_0015`, plus directly related tests and
  engineering/design records. No frozen sizing formula or numerical-stage edit.

## Excluded local material

The local database, the 160-curve supplier original, published local data packages,
default activation state, credentials, generated pictures, `output/`, `tmp/`,
unrelated visual-design drafts and local operations records are not included.
Code synchronization alone does not transfer or activate local curve data on production.
The existing GitHub workflow runs tests and has no production deployment step.

## Verification and limits

- Required `python -m compileall -q app.py calb_sizing_tool calb_diagrams`: passed.
- Complete directly affected selection of curve/version/RTE/Admin/source/workspace,
  migration and guard tests: **134 passed in 106.66 seconds**. Local evidence:
  `output/curve_upgrade_20261118/github-scope-tests.log`.
- Prior actual application checks: 7 curve navigation steps and 5 product pages
  on a copied database; 19 actual WebSocket steps with normal login, including
  9 local fragment switches and 6 related full reruns, retained the same session.
  Actual and copied curve/product table fingerprints remained unchanged.
- Frozen Stage1/2/3, DC pipeline, AC sizing, shared sizing rules and diagram modules
  have no changes against the preceding commit. No dependency change.
- Earlier full-suite run recorded 2495 passes and one Arrow-containment failure.
  The implementation was corrected to native numeric inputs and static HTML
  tables; the guard and subsequent affected checks passed. This is reused
  historical evidence, not a claim that the final snapshot has had a new
  all-green full regression.
- GitHub's existing CI is triggered by this push. Its result must be checked,
  and final full release validation completed, before production deployment.

Local runtime stays on port 8511. Ordinary product versioning, AC catalogue-status
filtering and retired-version reactivation remain outside this change.
