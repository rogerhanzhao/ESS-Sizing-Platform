# Report illustrations and AC sizing boundary

AC sizing remains authoritative for saved PCS count/rating, AC block count, DC allocation, mixed schedules and product selection. The existing arrangement resolver reads those results and determines cabinet length and layout. No render asset can change these inputs or choose a different arrangement to obtain a match.

The report selector operates only after the arrangement has been resolved. Its keys are AC cabinet length, DC count, placement variant, equipment dimensions/coordinates, service-door and equipment-end directions, and spacing profile. It does not filter by MW or MWh. Consequently a change in MW alone does not reject a template, but if the existing resolver changes the cabinet class as a result, the image must follow that resolved geometry. This preserves the existing AC sizing and cabinet-resolution rules.

The four illustrations describe 40ft+8DC central, 20ft+4DC linear, 20ft+2DC linear, and 40ft+4DC linear. Their pictured PCS bodies and transformer internals are representative, not the source of electrical counts. Section 8 now states this beside the illustrations; the AC sizing schedule remains the source of the project's counts and ratings.

The selector is read-only. Unsupported geometry, mixed schedules, white-label reports, incompatible bound products, or missing/damaged assets use the original engineering drawing. Section 9 retains its existing composer. There is no recalculation, write-back, database migration, or network rendering.

Validation scope: selector/fallback tests; input immutability checks; real-image exports compared against engineering-only exports for unchanged tables and Section 9 content. Reuse the preceding 48-shape geometry comparison and 61/14 affected-test evidence because those modules have not changed again.

2026-11-10 GitHub candidate: the owner-approved gravel/close-view revision replaces all 20 formal PNGs (2400 x 1600), with updated manifest integrity hashes. All 21 selector and packaged-asset tests pass. Four paired real exports preserve tables, AC output and whole-site content while embedding the new images. Production deployment remains a separate step.

Release checks: compileall passed. The full suite returned 2449 passed and one caption regression, with two inherited serializer warnings. The render caption now retains the equipment envelope dimensions and area, as the original engineering caption did. All 58 affected diagram/selector/report tests passed after this caption-only correction, including the original failing test. The unchanged full-suite results are reused rather than repeating the entire run.
