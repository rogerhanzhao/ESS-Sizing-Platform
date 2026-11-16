# Photo asset release — 2026-11-15.r2

Owner approved the current R2 image set for publication and deletion of superseded
photo versions, explicitly excluding confirmed 3D models and associated materials.

Scope: replace 20 packaged PNGs, update hashes/provenance, and change two image-size
assertions from 2400 x 1600 to the native 1536 x 1024. Four configurations retain
their existing TOP plus random-oblique selection. Template matching, placements,
AC/DC sizing and whole-station drawing logic are unchanged. Pre-existing uncommitted
mixed-mode reporting changes are excluded from this release.

The approved set remains representative synthetic imagery. Owner acceptance is
not a claim of pixel-exact geometry, identical small details between views, or
fire-code compliance. Preserve the exact source models for engineering use.

Validation completed on 2026-11-16: 21 focused tests passed in an isolated
baseline-code checkout with only the new assets and two dimension assertions.
The working checkout also passed 23 tests including its pre-existing mixed-mode
changes, which remain excluded from this commit. Compileall passed. All 20
packaged image hashes verified. Four actual DOCX exports embed the approved
TOP and SW bytes after the existing report watermark, with unchanged tables,
AC output and Section 9 text. Existing unchanged-code full-suite evidence in
CURRENT_STATUS is reused; no new full regression for PNG-only runtime changes.

Deployment: local assets updated; this commit is the GitHub release candidate. Production SSH
connection timed out during preflight; no production mutation performed.

Cleanup scope: superseded PNG/JPG/HTML/ZIP outputs in photo_samples_20261115 and
photo_audit_20261115 only. Preserve the approved R2 set, original field evidence,
all model/CAD/STEP/GLB/geometry files, engineering-reference renders and source
scripts. 36 superseded image/preview/bundle files deleted; 458 protected model
and reference-file hashes verified unchanged. Deletion paths and protected-source
hash checks remain in local output/photo_review20_20261115_r2/.
