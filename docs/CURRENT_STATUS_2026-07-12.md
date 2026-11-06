# Current Status 2026-07-12

> 2026-11-06 LOCAL MIX LAYOUT: restoring a whole-station concept figure for manual
> mixed container runs from each saved AC row. Uses the shared typical-block
> geometry, including odd DC tails and central stations; no Sizing recalculation.
> Original Layout page gains a collapsed read-only whole-station preview; report
> Section 9 uses the same composer. Uniform/governed/cabinet routes stay intact.
> Targeted checks cover unchanged uniform/governed layouts, current-allocation
> preview refresh, stale head-layout hints and invalid saved quantities. A final
> rendered-report check caught responsive SVG CSS producing a blank raster;
> intrinsic SVG dimensions now stay separate from browser styling, with opaque
> equipment-pixel regression coverage (12 new-module checks pass). B-ON saved-source
> export is ten Word-rendered pages; all 12 tables match the owner download except
> issue date. Authenticated local browser review and actual Westlake download
> confirm the two saved blocks, 10 DC containers / 10 PCS / 12.50 MW.
> The scope note now precedes the whole-station figure, avoiding a lone final note page.
> Linux isolated checks verify actual equipment pixels, saved B-ON totals, eight tail
> comparison reports and unchanged 39-table copied data. Final full regression:
> 2417 passed, two inherited invalid-frequency fixture warnings, 1264.96s; compileall
> passed. Frozen sizing modules have no changes. Deployment evidence is recorded
> separately in the private operations release record.

> 2026-11-05 LOCAL DISPLAY REVIEW: removed the hardcoded typical-block energy
> label, wrapped concept-site annotations for narrow canvases, released the
> oversized report figure pagination chain, and scoped Workbench Restore run
> selection to its Case. Full regression passed 2405 tests with two inherited
> invalid-frequency fixture warnings (1464.34s); the saved-source report renders
> to nine pages, with all 11 tables unchanged except issue date. Browser review
> confirmed cross-Case restore and mixed concept layout generation. A follow-up
> AC copy-only fix removes a uniform station total from the per-model container
> note; 18 focused AC checks pass. The actual Westlake browser download was
> Word-rendered and reviewed: 10 PCS, 12.50 MW, 10 DC containers, no body UUIDs,
> and a visible Head arrangement; formal SLD was not generated. Follow-up local
> fixes qualify the Section 7 reference and remove the isolated arrangement-note
> page (10 to nine pages, all 11 tables identical); 21 report tests pass. The
> final release regression completed on 2026-11-06: 2405 passed, two inherited
> fixture warnings, 1849.74s; compileall passed. No frozen sizing logic, catalogue or production data
> changes. This checkpoint is local validation, not a GitHub/production release.

> 2026-10-30 RELEASE CHECKPOINT: final full regression completed on 2026-10-29
> with 2404 passed, two inherited invalid-frequency fixture warnings, 1380.49s;
> compileall passed. Frozen core modules are unchanged. Linux candidate checks
> verify 239 runtime Python source hashes, eight reduced-string comparisons and
> exports, unchanged 39-table database copy, and the 75 MW / 68-container
> recommendation (34 x 2500 kW PCS, 85 MW installed). The saved 170 MW source
> report was read-only re-exported and Word-rendered to ten pages; affected
> summary/AC pages are legible. Release deployment and owner browser acceptance
> are recorded separately in private operations evidence.

> 2026-10-29 LOCAL PCS REPORT REVIEW: a saved 75 MW / 300 MWh case uses
> 68 standard DC containers, 17 AC Blocks and 4 x 2500 kW PCS per block:
> its 68 PCS / 170 MW report matches the production snapshot. Existing initial
> selection recommends 2 x 2500 kW per block (34 PCS / 85 MW) at the same 1:4
> grouping. Historical choices are preserved; their original selection gesture
> cannot be inferred from a saved snapshot. The original AC page now warns when
> the selected uniform model is larger than its suggested alternative. Uniform
> reports explicitly disclose installed PCS MW alongside POI duty and saved
> equipment quantities. No sizing equation or historical record is rewritten.
> Full release regression is pending after this follow-up. The earlier full
> run passed 2399 checks and found two missing data-image declarations for the
> new tail report; its logo/data chart are now explicitly classified in the
> watermark guard. Production remains at the prior release pending validation.

> 2026-10-27 LOCAL DC COMPARISON SCOPE: the owner paused formal tail adoption
> and requested a separate saved/exportable DC comparison with unchanged total
> container count, then clarified a manual range of 1..4 reduced-string boxes.
> The original DC Advanced area selects either the 10-string or 8-string product
> and a quantity. Standard 12-string sizing remains the default and active run;
> the comparison keeps at least one main container, does not add boxes to cure a
> failed energy check, and uses the original Stage3 curve selection. Single-tail
> saved payloads remain version 1; multiple-tail attachments use version 2 and
> are excluded from the old single-tail AC review / SLD preview. A separate
> DOCX download reads the validated saved comparison on both Run and Load Run.
> Original proposal/DC exports, sizing formulas, database schema and standard
> AC/SLD/layout paths remain unchanged. This is local work, not a production release.
> Verification completed 2026-10-28: 186 focused tests pass, including signed-in
> Run / saved-result reload / separate download presence / original AC handoff;
> compileall and frozen-core checks pass. Forty catalogue-copy cases cover both
> products and 1..4 quantities (34 calculated, six correctly rejected because
> no standard container would remain); failed energy checks stay failed without
> added boxes. Two final DOCX samples were rendered by Microsoft Word, three
> pages each, and all pages visually inspected. Original production snapshot
> hash is unchanged. Local 8511 uses a separate review DB copy; native-browser
> click acceptance and production release are not claimed. Evidence is private
> under output/dc_tail_range_review_20261027/.

> 2026-10-25 AC INITIAL-SELECTION / MISSING-SLD FOLLOW-UP (local validation):
> the owner's actual 100 MW / 400 MWh test has 92 standard containers. Its
> saved 230 MW and 115 MW alternatives are arithmetically correct; stale keyed
> AC controls and an index-zero default made the initial model misleading.
> The original AC form now suggests the smallest existing model passing the
> original feeder/aggregate checks, preserves saved/manual choices, clears
> controls only on source switches, and updates the upper snapshot in the same
> successful save response. MIX summaries use actual saved rows. No identity,
> grouping, sizing equation, feasibility threshold or model-library change.
> A separate older Admin 661Ah test exposed reuse of the 314Ah curves: a bounded
> preflight now checks the exact original picker's product-to-cell link before
> new Admin calculations, preserving the approved legacy 314Ah-A and Excel
> paths. Other cells require a future verified curve resolver; no fallback or
> retrospective rewriting of saved results. Initially the missing report SLD
> had never been generated, with incomplete engineering inputs. The original direct
> download remains; a warning/link now precedes it, and missing-figure status
> no longer reserves its own near-empty page. Valid-image Word rendering is
> pixel-identical in all ten pages. Final ratio-switch state refinement adds
> a source-scoped standard-model memory so first visits get the new grouping's
> suggestion and returning visits retain manual choices (38 focused pass).
> Final clean aggregate regression: 2373 passed, 2 inherited fixture warnings,
> 1021.84s, exit 0; compileall also passes. An earlier aggregate exposed one old
> mixed-report test requiring drawing-scope text with no drawing. Its test-only
> correction now verifies absent and available SLD, with 26 focused passes,
> followed by the successful complete rerun. Native Chrome restored the actual
> 1:4 / 115 MW run and recommendation correctly, then capture returned black.
> The follow-up after owner display/login recovery is blocked by the Computer
> Use safety mechanism: current browser URL cannot be determined reliably.
> No further automated app input was issued. The owner subsequently generated
> the AC B draft SLD and concept arrangement, then clicked the original direct
> download. The actual 20261025 AC-B DOCX is now verified: 92 standard containers,
> 23 AC groups x 2 x 2500 kW = 115 MW, 46 PCS, correct parent/child, zero UUIDs.
> Its ten-page Word rendering includes a readable SLD on page 7. The 1:4 diagram
> is linked to the current AC B artifact records and explicitly draft_override;
> registered file hashes match, and report SVG-to-PNG rendering has only tiny
> text-edge raster differences. This is not formal engineering acceptance.
> The source DB/workbook/catalogue/schema remain unchanged; 19 owner-generated
> draft/concept artifacts and related runtime snapshots/audits are accounted for.
> The actual saved 115 MW report separately passes readonly export/Word render
> QA (ten pages, no UUID, correct 23 x 2 x 2500 kW, no SLD fixture substituted).
> Same isolated DB on 8511, final runtime PID 13180, health ok.
> No source data, drawing engine, commit, GitHub or production change.
> Evidence: output/ac_sld_issue_review_20261025/REVIEW.md.

> 2026-10-24 ORIGINAL-PAGE HUMAN-VIEW REVIEW (local): external Chrome reviewed
> all ten original workflow pages and all ten Product & Database sections.
> Kept the existing navigation, Run/restore/Next/direct-download and comparison
> boundaries. Improved readable product/run tables, summary precision, clear
> English actions/source labels, collapsed technical IDs/hashes, and the
> contradictory supplier-uploader size hint. Fixed the RMU widget's duplicate
> SessionState/default warning. Report provenance copy now follows the resolved
> source without changing the resolver. Actual AC A download exposed integer
> rounding of 112.5 MW / 2.5 MW per block; report table/caption and the site
> figure's two title format strings now preserve decimals. No geometry, rule,
> sizing formula, source-data or product-activation change. Full checkpoint:
> 2321 passed, 2 existing invalid-frequency-fixture warnings, 1025.38s. Later
> source/precision changes separately pass 15 and 44 focused checks. Current
> compile, core hashes, exact diagram-label-only diff and data audits pass.
> Word/PDFium render QA retains ten pages; first eight are pixel-identical,
> changed pages 9/10 inspected. Original browser workflow and an actual before
> download pass; after owner sign-in the final actual Chrome download also
> passes. Every OOXML part and all five media match the reviewed saved-case
> export; Word/PDFium confirms all ten rendered pages are pixel-identical.
> Correct 112.50 MW / 451.440 MWh and 2.50 MW per block, no UUID or comparison
> capacity leakage. Signed-in Report Export remains open. No new sizing run.
> Local 8511, same isolated copy, no commit/push/deploy. Evidence and exact
> coverage: output/ui_human_review_20261024/REVIEW.md.

> 2026-10-24 FOLLOW-UP BOUNDARY RECHECK (297 focused tests and live switching passed):
> no application/test source changes. Current product/DC/BOM: 96 passed;
> AC/saved-source/SLD: 168 passed; original report isolation: 33 passed, all
> without warnings. Four real saved samples retain exact BOM/source checks;
> ten-string two-PCS is rejected and eight-string unknowns remain TBC. Previous
> DOCX files still match all OOXML/media; saved-file verification is separate
> from the additional current-cycle actual browser download, which also passes.
> The machine rebooted at 14:56; local 8511 was stopped and its old tab absent.
> Restored the same isolated DB on localhost only, health ok. External Chrome
> current-cycle external Chrome as administrator verifies eight-string tail feeding two
> PCS (individual duties TBC) and one PCS (input arrangement TBC), ten-string
> two-PCS rejection/no image and normal 1500+1000 kW MIX recovery. Foreign or
> unselected AC sources cannot reuse the old figure. Original AC/SLD/Arrangement
> Next and direct download pass; the new actual Word matches all reviewed
> OOXML/media. Signed-in original report page left open. Final 39-table/source
> 33-table/workbook audit and seven frozen hashes pass. No run, product, curve,
> figure, migration, commit, push or production change. Evidence:
> output/flexible_dc_boundary_recheck_20261024/REVIEW.md.

> 2026-10-24 COMPREHENSIVE LOCAL RECHECK (software and administrator browser
> acceptance passed):
> domains: product maintenance, original DC form/restore, optional AC/SLD tail
> preview and original report presentation. Known current catalogue conflicts
> and actual linked-cell changes can no longer bypass tail eligibility; legacy
> saved comparisons retain their recorded interpretation. One-PCS/three-winding
> preview input now shows an unused LV winding explicitly as TBC without
> inventing a connection or rating. The original DC page fixes duplicate
> frequency defaults, inline Load Run rendering the previous result, and
> returning from another page resetting restored inputs to workbook defaults.
> Historical report library provenance is no longer guessed from the current
> form radio. Two long AC identifier lists become exact continuous ranges and
> one caption pagination link is relaxed; sections/models/quantities/images and
> direct download are unchanged. The real saved AC B report remains 90 standard
> containers / 451.440 MWh / 45 AC groups / 113 MW; no comparison BOM or PCS
> override leaks into it. Word visual review improved 13 pages to 12; actual
> browser download matches every reviewed OOXML part and media hash.
> Compile and final complete suite pass: 2318 tests, 2 inherited intentional
> invalid-frequency fixture warnings, 762.65s (full-pytest-final.txt).
> Focused original DC restore/navigation/frequency/provenance: 6 passed.
> Source 33 tables and default workbook are unchanged; isolated-copy 39 tables
> differ only in normal login timestamps. Seven pinned canon modules and the
> original calb_diagrams tree have no diff. Final runtime is local 8511 on the
> same isolated DB; fresh Guest defaults/guard pass on the final runtime.
> Post-restart external Chrome as administrator confirms one inline Load Run immediately
> replaces the 46-container result with the exact saved 90-container parent,
> 98% DoD / 6 months S&C survive Workbench navigation, and the frequency warning
> is absent. Original Next through AC B / SLD / Arrangement / Report works.
> The historical source disclosure is correct; another actual download matches
> all reviewed OOXML/media. No Run/Generate clicked; signed-in report left open.
> Formal/manual tail adoption, arrangement and proposal remain incomplete;
> the existing one-tail producer is a comparison scope, not a product rule.
> Evidence: output/flexible_dc_full_recheck_20261023/REVIEW.md. No source DB
> write, migration, frozen formula edit, commit, push or production deployment.

> 2026-10-23 OWNER MANUAL-COMBINATION CORRECTION / NEXT LOCAL INCREMENT:
> one replacement, final position and ten/eight mutual exclusion are the scope
> of the existing comparison producer and test samples, NOT permanent product
> rules. The owner wants future manual adjustment; quantities and editing UX
> are not decided. Do not silently expose arbitrary combinations or encode the
> old sample limits into the inventory handoff. Ten-string 1-output/1-PCS and
> eight-string 2-output/up-to-2-PCS product constraints remain in force.
> Current work stays in the original DC page and existing adapters: explicit
> guarantee checkpoint Yx / POI target / usable energy / margin, actual versus
> selected SOH/RTE rates and curve-change disclosure. The existing session
> adapter gains an opt-in actual BOM handoff, preserving per-SKU subtotals,
> displayed unit precision and full Stage2 identity without inventing a physical
> connection. Only the optional tail preview consumes it in this batch, checking
> actual products/quantities/capacities against the saved AC assignments.
> Original scalar handoffs and the standard default are unchanged. Formal tail
> adoption / arrangement / proposal are still incomplete: no adopted button or
> reclassification of a comparison is enabled. Full regression: 2280 passed,
> two existing intentional invalid-frequency fixture warnings, 1094.05s.
> External Chrome as administrator verified eight/ten saved DC cards, original Next from
> DC to AC to SLD, explicit-AC-source requirement, eight-string two-PCS TBC,
> ten-string/two-PCS rejection and subsequent normal AC B preview. No Run or
> Generate clicked. Final page remains the signed-in ten-string DC result.
> All 39 isolated-copy tables match the pre-browser baseline except normal
> administrator login timestamps; source 33-table hashes and default Excel match.
> Compile/diff/frozen checks pass. Evidence:
> output/flexible_dc_tail_next_20261023/. No core formula, source DB,
> product/curve edit, new table/migration, commit, push or production deployment.
> This current correction supersedes the one-tail wording in historical entries.

> 2026-10-23 TAIL LAST-GROUP SLD PREVIEW (local acceptance complete):
> the next bounded increment stays on the original Single Line Diagram page,
> in one collapsed comparison area before the legacy MIX Head-fleet projection.
> It consumes a read-only handoff from the exact selected saved AC child and
> DC parent: actual run parent/project/case/type, full saved output hashes and
> displayed AC content must all match. No parent-runtime/session/artifact
> fallback is used by this optional preview. The pure adapter revalidates the
> existing DC comparison and AC review, preserving physical DC IDs, actual unit
> energies, separate PCS ratings and saved links. Errors produce no drawing.
> Eight-string unknown output duties/input arrangements remain explicitly TBC.
> A separate SVG depicts only that physical last group and marks comparison /
> not adopted / not for construction on the image. It is not registered,
> downloaded, published to shared SLD state or included in the proposal.
> Original Generate, standard renderer, downloads and Next remain unchanged.
> Full regression: 2231 passed in 1181.45s, two existing intentional invalid-
> frequency fixture warnings. The final display-only Workbench picker fix then
> passed 40 focused onboarding/alternative/workspace checks: it consumes the
> stable service A/B name and shows actual AC group count, total MW and DC count
> in the same existing control. External Chrome as administrator verified all four saved
> cases: ten-string 1500+1000 kW true MIX preview, ten-string/two-PCS no drawing,
> eight-string/two-PCS unknown duties and eight-string/one-PCS input TBC.
> Historical DC restoration alone does not substitute a parent-runtime source:
> the user must select the actual AC child in original Workbench before this
> preview is drawn. Final selector labels and Selected/Use were verified after
> restart; final signed-in page displays the AC B / group 45 ten-string preview.
> No original Run or Generate was clicked in this browser pass. Final read-only
> 39-table comparison allows normal administrator login timestamps only; no new run,
> snapshot, audit or artifact. Source 33-table hashes and default workbook match.
> Compile/diff/frozen checks pass; screenshots are browser-*.png in the evidence
> folder. The complete run preceded the final picker-copy change; its separate
> 40-check run and final browser acceptance cover that presentation-only edit.
> Formal tail adoption is still later work; source/artifact binding must be
> closed before an old standard or other-alternative image can enter a tail
> proposal. Evidence: output/flexible_dc_tail_sld_20261023/. No source database
> write, migration, frozen-core / calb_diagrams edit, commit, push or deploy.

> 2026-10-22 AC LAST-GROUP TAIL REVIEW (local comparison acceptance complete):
> original AC form / MIX rows / Run / save / Next remain the workflow. If its
> selected DC run has the saved owner-basis tail comparison, one collapsed area
> shows the final group's actual main + tail composition and separate ratings
> for only the PCS connected to that tail. Original Run attaches a nominal
> review to the standard AC output; it does not adopt the smaller DC BOM.
> The bounded service preserves exact source identities and original feeder
> mapping. Ten-string/two-PCS is a comparison error; eight-string/two-PCS keeps
> individual output duties unknown. No 4+4, equal split, current rating or winding
> capacity is inferred. DC duty shares are an explicit nameplate comparison
> policy; original cable / PCS efficiencies convert to the PCS AC boundary.
> Discovered and fixed MIX alternative hash collision: a changed tail PCS
> rating now creates a distinct alternative. Standard / legacy-no-row hashes
> remain unchanged; a legacy MIX is reused only after full new-identity equality.
> Also repaired lightweight same-DC restore losing the selected AC alternative
> while project/case metadata is filled, and Custom controls losing their saved
> count/rating. Foreign AC selections are not retained; existing user edits are
> not overwritten. Full regression: 2155 passed in 762.27s, with only the two
> existing intentional invalid-frequency fixture warnings. Original-page
> AppTest covers save/restore, actual MIX, selected older AC alternatives,
> Custom defaults, comparison-only rating reuse and unchanged SLD projection.
> External Chrome verified actual 1:2 grouping, the eight-string/two-PCS unknown
> output duties, ten-string/two-PCS rejection, and a last-group MIX comparison
> with separate 1500 + 1000 kW PCS ratings (not averaged). Standard Run / save /
> alternative reuse / original Next controls remain available. The two-winding
> selection used in these local cases is a test basis, not OEM confirmation.
> Final read-only database check matches all 39 isolated-copy tables against
> before-browser.sqlite: four normal AC children, their inputs/outputs and
> correlated audits, plus normal login timestamps. Existing DC inputs and
> products/curves are unchanged. User-created DC samples before that baseline
> are retained and are not attributed to browser acceptance. Source 33-table
> hashes and default workbook match; compile/diff/frozen checks pass.
> Source/product/curve data untouched. No frozen module / diagram edit,
> migration, new page, commit, push or deployment. Evidence directory:
> output/flexible_dc_tail_ac_20261022/. Tail adoption / downstream integration
> remain a later step after the last-group contract is accepted.

> 2026-10-22 OWNER-BASIS TAIL DC COMPARISON (latest, local implementation):
> owner explicitly authorizes the original cell-to-block energy calculation,
> default 0.5C and current standard 12-string 314Ah runtime curves. Exact 10/8
> capacities are 4.179968/3.3439744 MWh; nominal powers 2089.984/1671.9872 kW.
> The isolated 8511 copy now has two precisely linked Special tail records;
> source DB, main product, cells, curves and default Excel remain unchanged.
> Engineering variants stay outside the standard picker. Original collapsed
> Advanced area offers the two eligible choices; original Run calculates and
> saves one N-1 + 1 comparison beside the unchanged standard run. Original
> renderer shows BOM, lifetime plot and annual data; saved comparisons restore
> without calculation/adoption. Exact parent precision follows the existing
> Excel/Admin input path. Separate current-capacity rate review does not alter
> Stage3, and nominal 0.5C is not a hardware or lifetime power guarantee.
> Fixed an original historical-DC page gap: valid saved results now retain both
> Next buttons; AC restores the standard active run. Targeted 79 checks pass
> (58.23s), including four tail/source combinations and saved Next routing.
> Full regression: 2040 passed, 2 existing intentional fixture warnings
> (774.34s); compile, diff and frozen checks pass. External Chrome as administrator:
> both options enabled, original Run saved two real comparisons, original BOM /
> lifetime plot / annual data displayed. Original Workbench Restore selected
> each saved comparison without a new run; both historical Next buttons remain.
> Next -> AC for each still shows 92 standard boxes / 461.5 MWh. Returned to
> original DC Advanced area, signed in and ready for owner testing. Source
> unchanged; local writes are the two controlled child products, two correlated
> DC runs with inputs/outputs/audits and normal administrator login timestamps only.
> This supersedes
> older missing-nominal-energy/curve and disabled-placeholder statements below
> only for local DC comparison. Tail adoption, AC MIX last-group integration,
> output-level ratings and subsequent drawings/reports remain next work.
> New ownership: services/dc_reduced_string_tail_service is the bounded adapter;
> ui/dc_view remains the only DC renderer and workflow. No frozen core edits,
> independent page, new migration, commit, GitHub push or production deploy.
> Evidence: output/flexible_dc_owner_tail_20261022/.

> 2026-10-22 BATCH 2a LOCAL FOUNDATION VERIFIED: the original DC form now has
> one collapsed Advanced: Reduced-string tail area before Efficiency Chain.
> Its three choices are disabled and fixed to standard; no business input,
> scenario, second Run, adopted tail, product activation or new page is added.
> Maintenance summaries reuse the original catalogue diagnostics and exact
> selected-container/parent codes, never equal Ah or fuzzy product names.
> Guest does not read this maintenance preview; read failure leaves standard
> sizing available. The existing DC payload hash already covers Stage 2 BOM:
> persistence rejects non-original comparison modes before opening a database;
> restoration verifies existing DC input/output hashes before constructing the
> bundle. Hashless legacy runs and AC alternative identity hashes retain their
> prior compatibility. This does NOT add tail revision/topology adoption.
> Validation: 15 form/frozen checks passed (17.05s); 20 persistence/restore
> checks passed (22.11s); full suite 1991 passed, 2 existing fixture warnings
> (726.23s); compile/diff/frozen checks passed. Existing isolated-copy 54 DC
> input and 54 output hashes all match the unchanged hash algorithm. Source
> data unchanged; local data retains prior 418 form corrections plus login times.
> Old local service was already stopped when checked; started PID 27760 on
> 8511 with the same isolated copy, all pilot flags off, without startup-script
> migration. External Chrome login then confirmed the collapsed area, disabled
> 3 choices, short maintenance table, original Run, and admin -> Back to Sizing
> preserving administrator / V2.2 TEST / 4th / unselected run / 100 MW / 400 MWh.
> No real-browser Run/Save/Import was clicked. Evidence: batch2a-* under
> output/flexible_dc_connection_maintenance_20261022/. Batch 2 formal tail
> adoption is still incomplete; ratings/curve applicability and actual BOM to
> AC handoff remain open. No GitHub push, commit or production deploy.

> 2026-10-22 ORIGINAL PRODUCT PAGE BROWSER ACCEPTANCE COMPLETE: after the fresh
> user login, all four actual external Chrome uploads completed. Valid 10-string
> shows 1 DC output / maximum PCS 1; valid 8-string shows 2 / 2; unknown ratings
> remain blank. The 10-string/PCS-2 counterexample shows Row 2, zero valid rows
> and disabled Import. Legacy 57-column input previews with the new fields blank.
> Exporting during a valid preview retains that preview and administrator authentication;
> its 4-row/60-column CSV is byte-identical to the prior actual download. Removed
> all test uploads, returned via Back to Sizing to Workbench and opened the
> original DC Sizing page. Project V2.2 TEST / Case 4th / Run Not selected remain
> intact. No Save, Import, Run, restore, product activation or application edit.
> Data verification passes: source unchanged, local product changes still only
> the two previously documented 418 form corrections, plus normal login times.
> No further logout occurred during this fresh-session pass. The earlier lost
> session's precise trigger remains unconfirmed; do not call it an app fix.
> Evidence: browser-*.txt/png and browser-catalogue-during-preview.csv under
> output/flexible_dc_connection_maintenance_20261022/. Batch 1 maintenance is
> verified locally. Batch 2 DC integration has not started; actual tail ratings
> and cell/curve applicability remain open. No GitHub push or production deploy.

> 2026-10-22 CHROME FILE PERMISSION CONFIRMED: user screenshot shows Allow
> access to file URLs enabled. Reconnected the same external CALB tab through
> the refreshed Chrome connection; administrator/Admin and the original project/case
> were visible. The file chooser now opens and accepts the local preview CSV.
> The subsequent page state returned to Sign In before a preview appeared.
> PID 25552 has not restarted and stderr has no application exception. Read-only
> review finds no auth clearing in the upload-preview path; a replaced/lost
> Streamlit session is a hypothesis, not an established root cause. Requested
> one fresh user login to retry immediately. Database verification still passes.
> Actual upload-preview acceptance and return to Sizing remain pending; no
> Save/Import, application change, GitHub push or production deploy occurred.

> 2026-10-22 EXTERNAL CHROME REVIEW RESUMED: after user restored the extension,
> opened the original Product & Database page as administrator and inspected the three
> new English fields on the existing 5MWh edit form (blank/Not specified, no
> automatic tail values). Actual catalogue/template downloads completed: 4
> product rows vs header-only, same 60 ordered fields, no UUIDs, byte-identical
> to the service export. Screenshot: browser-fields.png in the evidence folder.
> File-chooser wait then timed out and control detached during upload preview;
> Chrome upload guidance requires checking Allow access to file URLs. User has
> been asked to restore upload permission/connection, without logging out.
> Four exact preview files pass the live service's read-only checks (invalid
> 10-string/2-PCS is rejected; valid 10, valid 8 and legacy 57-column pass).
> These are service checks, not completed browser upload acceptance. No Save or
> Import clicked, no app/code changes or test rerun. Actual upload previews and
> return-to-Sizing review remain pending; see current evidence/review record.

> 2026-10-22 PRODUCT CONNECTION MAINTENANCE IMPLEMENTED (local only): original
> DC Block add/edit forms maintain DC output circuits, maximum connected PCS
> and connection source. The existing metadata owns these values; no new table
> or migration. Shared maintenance parsing/validation covers forms, flat CSV
> and legacy metadata aliases; new exports/templates have 60 fields, old 57-field
> input remains compatible. Counts are product capability, not actual operating
> PCS quantity. Special tail 10 requires declared 1/1; 8 requires declared 2/2;
> missing draft values remain Incomplete and all special tails stay outside the
> standard picker. Standard records are neither inferred nor constrained by
> these family rules. Known interface/family conflicts cannot be bypassed by
> partial edits once connection counts are declared. Explicit null/nonmapping
> product metadata is rejected so the tail role/parent/constraints cannot be
> erased. Legacy invalid metadata opens safely with Needs correction and allows
> repair; reads do not modify records. Ownership remains product maintenance
> service + original admin UI; DC/AC formulas, original flow, diagrams/reports
> and default selection remain unchanged. No real tails created/activated.
> Validation: basic/backend and UI checks passed; first full run had 1966 pass
> and one UI-refresh assertion failure caused by a pre-existing test leaking
> a mocked _refresh. Scoped that mock; the ordered 27-check regression passed.
> Final full regression after the null-metadata repair: 1972 passed (736.55s),
> with only two existing intentional Pydantic fixture warnings; compile, frozen
> and diff checks passed. Local 8511
> had stopped and was started with the same isolated DB and pilot flags off.
> User signed in as administrator in external Chrome; browser-control connection then
> failed (Debugger unattached), so current live field/download review is pending
> connection restoration. Keep this distinct from passed AppTest checks.
> Source tables unchanged; local product/cell/curve records retain only the
> prior two 418 classification deltas. Normal login updated user timestamps.
> Evidence: `output/flexible_dc_connection_maintenance_20261022/`.
> No GitHub push, production deploy or further DC/AC integration in this batch.

> 2026-10-22 OWNER TAIL-TOPOLOGY CLARIFICATION (latest): the 10-string tail has
> ONE DC output and must not feed two PCS simultaneously; the 8-string tail has
> TWO DC outputs and can feed two PCS. This is direct user design input, not
> a newly obtained supplier drawing. Output count is no longer wholly unknown;
> actual ratings, the 8-string per-output distribution and curve applicability
> remain separate open inputs. Keep the original 12-string default plus at
> most ONE tail (10 OR 8), and use the original DC/AC MIX/downstream workflow.
> Do not create an independent platform or force a new AC Block/transformer for
> every tail. First replace the final DC unit within the existing last AC group;
> split a tail group only if actual equipment cannot support that combination.
> Original MIX has one PCS rating per group and a station-wide DC-output count;
> these cannot represent the new per-product topology or unequal PCS ratings
> inside a tail group. The planned narrow adapter must preserve actual DC/PCS
> composition only for that group, not change the old core/standard main groups.
> Updated `FLEXIBLE_DC_EXISTING_UI_INTEGRATION_2026-10-21.md` is authoritative.
> This pass revises planning only: no app/DB writes, product activation, restart,
> GitHub push or deployment. Earlier statements below about unknown tail output
> counts are historical and superseded only for the two confirmed interface facts.

> 2026-10-22 BATCH 1 PRODUCT DATA RECONCILIATION (local only): user confirmed
> independent 8/10-string specifications/drawings are unavailable; keep tails
> pending and do not enable batch 2. Read source PDFs and the actual 5MWh DC SLD:
> standard 12 strings use two 6+6 outputs and paired-string HV boxes, so 10
> strings cannot silently become 5+5. Continuous per-output ratings, exact
> cell/revision and curve applicability still need independent evidence.
> Corrected only 418 block_form container→cabinet and its matched structured
> datasheet field in the 8511 isolated copy, with backup, identity guards and
> exact whole-database delta checks. Source remains unchanged at 0010; all
> other copy data, flags, curve/cell links and default Excel remain unchanged.
> Future seed now explicitly declares all four forms; no existing-library
> reseed. Admin cabinet/hybrid availability intentionally reflects the fixed
> form. A/B/G1 identities remain unresolved and are not rebound; master SOH
> 178 and RTE 51 effective points match v13. Module ownership stays in catalogue
> initialization/maintenance. 78 focused checks passed (45.84s), plus the added
> datasheet-form assertion (1 passed, 2.24s); compile/diff checks passed. Actual
> browser shows cabinet, downloaded CSV has 4 rows/57 fields and no UUIDs.
> Frozen core, original DC/AC/SLD/layout/report UI and app routing are unchanged.
> See `FLEXIBLE_DC_PRODUCT_DATA_RECONCILIATION_2026-10-22.md` and
> `output/flexible_dc_data_reconcile_20261022/`. No GitHub push or deployment.
>
> The earlier seven-table source/copy equality below describes the pre-repair
> browser check; after this bounded correction, only the two documented form
> fields intentionally differ. It is not a claim of current whole-table equality.

> 2026-10-22 BATCH 1 LOGGED-IN BROWSER REVIEW COMPLETE: original Product &
> Database → DC Blocks opened successfully as administrator. Checked original edit/add
> controls, 5MWh missing-parameter messages and the filtered parent selector;
> downloaded the actual catalogue and blank template (same 57 columns, 4 rows
> versus header-only, no internal IDs). Repeated download retained the upload
> preview and authentication. Uploaded current and legacy-format no-write
> previews; human codes and Special tail labels rendered correctly. An invalid
> parent produced a row-specific message and disabled import. No Save/Import
> was clicked; uploads were removed. Back to Sizing retained administrator, project
> V2.2 TEST, case 4th and the original no-selected-run state; returned to a clean
> DC catalogue page. All seven catalogue tables match the source exactly, and
> all 32 source data tables remain unchanged at 0010. Evidence and screenshots:
> `output/flexible_dc_product_browser_20261022/`. This resolves the sign-in
> visual-review pending item below; no app code changed in this browser pass.
> Existing DATA issues remain separate: 418kWh is classified container in both
> source/copy; 5MWh lacks continuous power/current and its curve/cell linkage
> needs reconciliation. Do not infer repairs, activate tails or reinterpret
> Published as engineering approval. Wide catalogue tables still horizontally
> scroll at the observed viewport; no navigation/layout redesign was made.
> Batch 1 functional review ends here. Before enabling batch 2, reconcile the
> exact product/cell/curve basis and obtain confirmed independent tail ratings.
> No GitHub push, production deploy or new sizing/diagram/report connection.

> 2026-10-22 BATCH 1 READABILITY FOLLOW-UP (local only): use engineering labels
> in missing-parameter details, lock existing Special tail role, filter known
> incompatible parent choices (without rejecting incomplete parent drafts), and
> project import previews to human codes/labels instead of legacy UUID/JSON.
> Full import payload and legacy backend compatibility remain unchanged.
> Module ownership stays in original admin UI and product maintenance services.
> 75 focused checks passed (43.90s), including original DC run/navigation smoke
> and frozen canon checks; compile/diff/source-data checks passed. The prior
> full 1871 pass is the Oct 21 baseline, not a new Oct 22 full run.
> Browser initially showed administrator signed in but navigation rebuilt a signed-out
> session; admin-page visual acceptance remains pending. Local 8511 was then
> restarted to load these display changes, using the same isolated DB copy.
> A separate original-app navigation check passes: Product & Database → DC
> Blocks → Back to Sizing retains authentication, active case and DC page.
> Nine original-page tests passed (10.99s), including this added regression.
> No auth behavior, sizing, diagrams, reports, activation, push or deploy changed.

> 2026-10-21 BATCH 1, ORIGINAL PRODUCT MAINTENANCE (local only): the existing
> DC Block Templates add/edit forms now maintain configuration role, parent,
> source/version and restrictions; the original catalogue shows live missing
> parameter status. No new page, sizing option or workflow step was added.
> Module ownership: `services/dc_product_maintenance.py` owns the draft field
> contract, code/identity resolution and known-conflict validation, reusing the
> existing lineage structure checker; `product_admin_service.py` owns writes,
> previews, read-only diagnostics and flat parameter export; original admin UI
> owns those form controls. No new migration or automatic registry transition.
> CSV template/export use one field list and cell/parent codes rather than UUIDs.
> Cells/parents must already exist; import remains create-only. Custom metadata
> and engineering review history are outside this parameter export. Legacy raw
> service updates remain compatible and can expose incompatible drafts, while
> original forms and maintained-field imports enforce declaration consistency.
> Special tails remain excluded from standard sizing, including Active/Published
> records. Missing data is never approved or scaled from parent ratings.
> Validation complete: 1871 tests passed (501.33s), including 35 new maintenance
> and 5 original-form interaction checks; two existing intentional Pydantic
> fixture warnings. Compile/diff checks passed. Frozen core, app routing, other
> UI, diagrams and reports are unchanged. All 32 source data tables remain
> unchanged at 0010; existing 16 FK issues did not increase. Local 8511 uses the
> same isolated copy. Logged-in browser visual review remains pending admin
> sign-in; do not claim it completed from AppTest. Stop at batch 1 and report.

> 2026-10-21 ORIGINAL-UI INTEGRATION CLEANUP (latest user direction): removed
> all seven experimental UI modules and their entry points, the standalone D2
> search stack, its dedicated fixtures/tests, and prototype rehearsal launchers.
> 26 application/script/test files plus eight historical launch/reproduction
> scripts were SHA-verified into an external recovery archive before removal.
> Original app/DC/Admin/AC/SLD/layout/report UI now has zero diff against 05cb345.
> Module ownership: original dc_view remains the sole DC result renderer;
> readiness, finite-tail comparison, lineage, manifest/dispatch and D1 checks
> remain backend assets for narrow original-page adapters. No new sizing feature
> is connected yet. Migrations 0011-13 and required models retain compatibility.
> `FLEXIBLE_DC_EXISTING_UI_INTEGRATION_2026-10-21.md` supersedes the prototype
> expansion plans: batch 0 ends after cleanup/planning/verification; report back
> before product/DC/AC integration batches. No GitHub push or deployment.
> Cleanup validation complete: 1831 tests passed (629.52s); 27 original-page
> focused checks passed (46.08s), compile and diff checks passed. No dangling
> imports after removal. Source DB remains 0010 with unchanged records and 16
> inherited FK issues. Batch 0 ends here; next continuation is product
> maintenance only, with no automatic advance into DC/AC implementation.

> 2026-10-21 USER SCOPE RESET: retain the original pages, buttons and workflow.
> Stop further D2 development and independent prototype acceptance. D1/D2
> remain local research assets, not the planned replacement UI or a release.
> The near-term scope is the original 12-string default plus one optional
> 8/10-string tail, using the existing AC and export flow. The formerly visible
> admin readiness panel is now opt-in (`CALB_DC_CATALOGUE_REVIEW=1`); all other
> pilot entry points remain default-off. Original app routing, AC/SLD/layout/
> report pages and frozen modules are unchanged against 05cb345. See
> `FLEXIBLE_DC_SCOPE_RESET_2026-10-21.md`, which takes precedence over expansion
> steps below. The D2 full run was stopped at the user's scope correction and
> is not a full acceptance result. No GitHub push or production deployment.
> Scope-reset checks: 33 original-flow regressions passed (60.50s), compile
> and diff checks passed. Original app.py is running on 8511 with all five
> experimental UI flags off and a separate source-data copy; 8527 was stopped.
> Source remains 0010 with unchanged records. Logged-in browser acceptance of
> the full original workflow remains pending.

> 2026-10-21 Phase D2a local implementation: module-map additions
> `schemas/dc_ac_candidate_search.py` owns explicit assembly/slot declarations
> and computation budgets; `services/dc_ac_candidate_search_service.py` owns
> bounded revision-multiset exact cover, full D1b evaluation and batch review
> checkpoints; `ui/dc_ac_candidate_review_view.py` owns independent English
> candidate diagnostics. The D1b AC-reference prerequisite is reused through
> `validate_equipment_source_boundary`; its semantics are unchanged.
> One whole DC unit occupies one PCS slot; full templates and separate input
> buses only. No DC paralleling, new sizing ratios, adoption or drawing release.
> See `DC_AC_CANDIDATES_D2A_2026-10-21.md` and local D2a evidence directory.

> 2026-10-21 second independent D1b recheck found pilot input metadata loss:
> `ui/dc_view.py` now forwards POI AC/DC location, voltage and actual frequency
> into comparison inputs. TBD blocks only the experimental comparisons and
> clears their temporary preview; the original Run Sizing path is unchanged.
> The equipment diagnostic adapter now rejects DC-side/unspecified POI sources,
> TBD frequency and conflicting selected/numeric frequencies before using any
> equipment rating. It never infers AC boundaries from 100% efficiencies.
> Earlier pilot comparisons with lost metadata must be recomputed from the
> corrected UI; they cannot be inferred, relabelled or silently rehashed.
> Module ownership remains unchanged: pilot input context and diagnostic guards.
> Evidence: `output/flexible_dc_phase_d1b_finalcheck_20261021/`.
> Final regression: 1877 passed (688.62s), including 21 new metadata/boundary
> checks. Twelve synthetic scenarios were recomputed; browser checks confirm
> DC-POI/TBD rejection, 60/50Hz failures and exact download content with preview
> retained. Source records/version remain unchanged; no push or deployment.

> 2026-10-21 independent D1b recheck: the pre-fix 1844 suite passed again
> (512.82s), but independent edge probes found two known-failure masking gaps:
> a missing temperature endpoint hid an exceedance of the other known endpoint;
> unknown PF hid an apparent-power rating below the known active-power lower
> bound. Fixed in the independent equipment diagnostic adapter, with 12 new
> regressions. Equipment tokens are checked again after final DC revalidation.
> The result/UI now explicitly describe separate read checkpoints and require
> atomic revalidation for future adoption; this remains comparison-only.
> No frozen sizing, legacy matching, original diagram or source DB changes.
> Final recheck evidence: `output/flexible_dc_phase_d1b_recheck_20261021/`.
> Post-fix full regression: 1856 passed (504.63s); all 12 added edge regressions
> passed (20.94s), 42 previous equipment tests passed (89.86s), and 7 UI checks
> passed (10.23s). Original seven synthetic scenarios retain their numerical
> duties/statuses; two added edge scenarios now fail for the known shortfall.

> 2026-10-21 Phase D1b local equipment diagnostics: after 148 D1a checks passed,
> added `schemas/ac_equipment_capability.py` for strict component ratings and
> explicit equipment duty; `infra/db/models/ac_equipment_capability.py` plus
> migration 0013 for independent immutable revisions/events; and
> `services/ac_equipment_capability_service.py` for admin-only monotonic review,
> lifecycle integrity and exact reference resolution. Module-map additions:
> `services/dc_ac_equipment_assessment_service.py` owns declared discharge-point
> checks using the signed Stage1 loss chain, individual PCS ports/whole units
> and transformer windings/total ratings; `ui/dc_ac_equipment_review_view.py`
> owns English static diagnostics outside the original page routing. These do
> not own frozen sizing, legacy catalogue matching, run adoption or rendering.
> Ratings and project conditions can remain unknown; all results stay local,
> comparison-only and downstream-not-ready. See `DC_AC_EQUIPMENT_D1B_2026-10-21.md`.
> Migration rehearsed only on isolated databases/copy; all existing source-copy
> records preserved, zero additional FK violations, source remains at 0010.
> Final D1b full regression: 1844 passed (550.44s); 42 focused equipment checks,
> 187 schema/registry/migration/UI-containment checks and 7 UI checks passed.
> Compile and frozen-module/diagram diff checks passed. Browser verified seven
> synthetic scenarios and retained preview after download; final table-width
> presentation adjustment passed another 7 UI/containment checks (11.29s).
> No frozen-module/diagram changes, actual product release, push or deployment.

> 2026-10-21 Phase D1a local mapping diagnostics: after 299 C2b compatibility
> checks passed (107.95s), added `schemas/dc_ac_allocation.py` for strict explicit
> equipment connections; `services/dc_ac_allocation_source_service.py` for exact
> retained-comparison identity and current DC source/dispatch revalidation;
> `services/dc_ac_allocation_topology.py` for complete connection and bus-boundary
> checks; `services/dc_ac_allocation_service.py` for before/after source checks
> and upstream DC-duty aggregation. Module-map additions own diagnostics only,
> not sizing formulas, numerical AC capability, release, adoption or rendering.
> `ui/dc_ac_allocation_review_view.py` presents English static diagnostic tables;
> the isolated loopback review app does not change production page routing.
> Equipment references remain unverified; all new results stay comparison-only
> and downstream-not-ready. See `DC_AC_ALLOCATION_D1A_2026-10-21.md`.
> Final D1a regression: 1614 tests passed (404.45s); compile, diff and frozen
> checks passed. Browser verified six synthetic cases and retained preview after
> diagnostic download. Four isolated rehearsal DBs pass integrity/FK checks.
> Source remains at 0010; its 16 inherited FK violations remain unresolved.
> No frozen-module/diagram edits, source DB migration, push or deployment.

> 2026-10-21 Phase C2b local comparison: scoped to the existing 314Ah / 416S /
> 20ft / 12-string family, with at most one independently reviewed 10- or
> 8-string tail replacing one standard container. Module-map additions:
> `services/dc_tail_candidate_service.py` owns bounded candidate enumeration
> from a separately computed standard count; `services/dc_composition_dispatch_service.py`
> owns declared per-box/per-domain DC discharge-duty diagnostics;
> `services/dc_composition_comparison_service.py` owns fixed-BOM evidence checks
> and experimental comparison orchestration using unchanged Stage1/Stage3 and
> frozen Stage2 record rounding. It neither replaces the original guarantee
> loop nor adopts a run. Common numerical curves must be independently approved
> for every revision. `ui/dc_tail_comparison_view.py` presents these separate
> energy/DC/AC states under admin-only `CALB_DC_TAIL_COMPARISON=1` (default off).
> These modules do not own production sizing, AC/PCS allocation, rendering,
> product activation or release. See `DC_TAIL_COMPARISON_CONTRACT_C2B_2026-10-21.md`.
> All new rehearsal data are SYNTHETIC, isolated and not CALB performance evidence.
> No source/production DB migration, GitHub push or deployment.
> Final C2b verification: 1473 full-suite tests passed (423.73s), 299 focused
> tests passed (108.21s), plus 10 final UI/Arrow/English checks passed. Compile,
> diff and frozen-module/diagram checks passed. The Arrow chart regression was
> fixed using the existing locked Matplotlib PNG path, without weakening the
> platform containment test. Browser checked normal and underpowered-tail
> cases, individual/domain limits, annual chart/data and preview after download.
> Two synthetic databases pass integrity/FK checks; source remains at 0010 with
> four products and the same 16 pre-existing FK orphans. Actual C2a draft-product
> planning retains incomplete-review gates. Next AC contract design is recorded
> in `DC_AC_ALLOCATION_D1_DESIGN_2026-10-21.md`; no AC adoption/SLD release yet.

> 2026-10-20 Phase C2a local pilot: the active scope is the existing 314Ah /
> 416S / 20ft / 12-string parent and special 8/10-string child configurations.
> Module-map additions: `infra/db/models/dc_configuration_variant.py` and migration
> `20261020_0012` own versioned lineage/events; `services/dc_configuration_variant_service.py`
> owns lineage integrity/review/special-scope checks; `common/dc_configuration_identity.py`
> owns explicit 20ft catalogue terminology only; `services/dc_composition_manifest_service.py`
> owns explicit planning BOM/physical identities/output partitions and content signature.
> `ui/dc_configuration_variant_view.py` presents the opt-in administrative local pilot
> (`CALB_DC_VARIANT_REVIEW=1`). The product-library adapter quarantines registered/marked
> engineering child products from the standard picker regardless of Active/Published;
> all other existing records retain their prior semantics. C1 comparison enforces the
> special scope before/after evaluation. No sizing formula, AC allocation, diagram
> engine, run adoption or release responsibility moves into these modules.
> See `FLEXIBLE_DC_PHASE_C2A_2026-10-20.md`. Isolated-copy rehearsal only; no source
> database migration, commit, GitHub push or production deployment.
> Final C2a checks: 226 focused tests and 1272 full-suite tests passed (362.62s
> full suite); compile/diff/frozen checks passed. Browser checked both 12+8 and
> 12+10 planning BOMs, scope rejection, physical register and preview after download.
> All 32 original source tables' records are preserved; 16 inherited foreign-key
> orphans are recorded separately, with zero new violations. This is not full
> production database health or mixed-sizing/AC/drawing acceptance.

> 2026-10-20 Phase C1 local pilot: `services/dc_product_comparison_service.py`
> validates a reviewed product revision and a separately approved DC curve
> package, preflights the entire requested evaluation budget, then invokes the
> frozen container-only pipeline. `ui/dc_product_comparison_view.py` exposes an
> administrator-only comparison under `CALB_DC_PRODUCT_COMPARISON=1` in the DC
> page. It owns no sizing formula, persistence, adoption or downstream readiness.
> Standard flow remains the default. Module-map addition: these modules own
> comparison applicability/validation and presentation only. See
> `FLEXIBLE_DC_PHASE_C1_2026-10-20.md`. Final local regression: 1142 passed /
> 308.02 seconds; compile and frozen-canon checks pass. No push or deployment.

> 2026-10-20 Phase B local pilot: Phase A recheck passed 24 tests. New
> `infra/db/models/dc_catalogue_revision.py` and migration `20261020_0011`
> persist isolated parameter revisions and review events;
> `services/dc_catalogue_revision_service.py` owns snapshot integrity, review
> transitions and staleness checks. `ui/dc_catalogue_revision_view.py` exposes
> an administrator-only, opt-in review panel through the existing product page.
> These modules do not own sizing, runtime curve applicability or activation.
> Runtime release remains disabled. Migration rehearsal used an isolated copy;
> source/production databases are unchanged. See `FLEXIBLE_DC_PHASE_B_2026-10-20.md`.
> Final Phase B regression: 1049 passed / 258.25 seconds; compile check passed.
> Independent follow-up found and fixed old-review revival after parameter
> restoration; v2 snapshots include catalogue modification tokens. New captures
> are selected explicitly, review form state is isolated, captured values are
> visible. Final second-pass regression: 1054 passed / 361.37 seconds.

> 2026-10-20 local planning / Phase A: see
> `FLEXIBLE_DC_PRODUCT_ROADMAP_2026-10-20.md`. Product administration now has a
> read-only participation/parameter review using the actual frozen picker.
> Module-map addition: `services/dc_catalogue_readiness_service.py` owns catalogue
> diagnostics only; `ui/admin_portal_view.py` presents them. No sizing, activation,
> drawing, curve mapping or database responsibility moves into this service.
> Multi-variant search and a versioned equipment allocation contract are staged
> follow-ups, not enabled by this diagnostic. No production release.
> Actual database/Streamlit testing exposed and fixed the existing detached-ORM
> product-to-sizing adapter bug without changing its selection semantics.
> Final local regression: 1034 passed / 508.06 seconds; see
> `FLEXIBLE_DC_PHASE_A_VALIDATION_2026-10-20.md`.

> Local-only work (2026-10-18): cabinet concept SLD, symbolic Block Arrangement
> and technical DOCX export are implemented on the existing saved-AC/page/artifact
> flow, with the original direct report download restored (no additional
> Generate Report step). Final full regression: 1001 passed in 379.55 s. Actual browser downloads
> and all 10 rendered report pages were checked; the isolated database retains
> 18 DC runs and 11 AC runs. The five original SLD core files and frozen sizing
> formulas remain unchanged. Preview-sheet selection reads verified packages;
> unchanged AC re-runs retain drawings despite a renewed session token.
> Installation-source PDF bodies are still unreadable while OneDrive sync is
> pending: dimensions, installation spacing and test conditions remain unverified.
> See `REPORT_EXPORT_UNIFIED_FLOW_REVIEW_2026-10-18.md`,
> `CABINET_ARRANGEMENT_REPORT_LOCAL_REVIEW_2026-10-18.md` and
> `CABINET_SLD_LOCAL_REVIEW_2026-10-17.md`. No commit, push or production deploy.
> Earlier milestones and their historical test counts below are retained.

> 2026-10-19 presentation-only follow-up: both report branches now use the generic
> `Download Technical Proposal` button, with no product details in its label.
> UI + frozen-canon targeted checks: 13 passed. The supplied 10-page cabinet
> document was reviewed without editing its data or drawings; see
> `CABINET_REPORT_PRESENTATION_REVIEW_2026-10-19.md`. The 1001 figure above is
> the preceding full-regression checkpoint, not a new run for this label change.

> 2026-10-19 owner follow-up: the isolated cabinet proposal now follows the
> original report's nine engineering chapters, including saved Stage 1 DC
> requirements and efficiency chain, Stage 2 configuration, Stage 3 lifetime
> results and Stage 4 AC equipment. All actual SLD sheets precede all arrangement
> sheets. The 13-page sample (four A3 drawing pages) was fully rendered and
> inspected; all 21 annual rows and equipment/group assignments match the
> supplied original cabinet proposal. Report plugin version: 1.1.1. Final
> regression: 1008 passed in 227.31 s; focused report/data/UI/canon checks:
> 90 passed. The original container report, five SLD core files and seven frozen
> modules remain unchanged. Local QA service on port 8511 is healthy. No commit,
> push or production deployment. See `CABINET_REPORT_PRESENTATION_REVIEW_2026-10-19.md`.

> **Latest stage record: `docs/CURRENT_STATUS_2026-07-28.md`** (tip `20676fe`,
> 517 tests). This doc remains the standing detail + module map (§2.7–§2.12,
> §4.1); read the 2026-07-28 record first for the current milestone.

Branch: `ops/ubuntu-docker-coexist-20260311`
Milestone commit: `b992818` — "SLD Proposal Package V1 + Site Constraint Set V1"
Verification: `python -m compileall` clean, 215/215 tests passing (~50 s).

This document records the state of the proposal-output governance version and
the agreed direction for future maintenance decomposition. The previous status
baseline (`CURRENT_STATUS_2026-04-13.md`) remains valid as the frozen sizing
reference; this document supersedes it only for SLD/Layout document governance.

## Active AC Sizing direction (owner decision, 2026-07-27)

For new AC runs, `AC_SIZING_UNIFIED_FLOW_V2_2026-07-27.md` is the governing
handoff. It replaces the UI-level governed-product preset with one generic
grouping -> PCS -> explicit topology -> optional product-match flow. The
supported grouping set now includes 1:8, but 1:8 is not a locked standard
product: 2 x 2,500 kW remains the normal comparison preference and 8 x 1,250
kW is an optional small-PCS candidate only for a user-selected 1:8 case.

Local verification on 2026-07-27: `AC_SIZING_UNIFIED_FLOW_V2_2026-07-27.md`
records 477 passing tests and a real Guest 1:8 -> 8 x 1,250 kW -> 3-winding
catalogue-bound SLD render. Guest SLD previews are intentionally not persisted;
formal run artifacts remain a signed-in, traceable workflow.

Cloud implementation handoff and the machine-enforced cross-module acceptance
contract are in `CLAUDE_CLOUD_AC_SIZING_SLD_EXECUTION_GUIDE_2026-07-28.md` and
`tests/integration/test_claude_ac_sizing_handoff.py`. They record the active
new-run rules, P0/P1/P2 remaining work and the requirement that 1:8 remain a
generic grouping rather than a product lock. The 2026-07-28 checkout collected
481 tests and passed the full suite after adding that contract; the 477 figure
above remains the 2026-07-27 historical verification record.

Sections 2.3–2.5 below are retained as implementation history and compatibility
context for persisted governed outputs. They must not be used to restore the
old checkbox or a separate sizing engine.

## 1. Completed in this version

### SLD Proposal Package V1 (P1)

- `services/sld_proposal_package_service.py` issues SLD-01 Site Electrical
  Index, SLD-03 Electrical Design Basis Schedule and SLD-04 Concept
  Interface/Scope sheets (JSON/SVG/PNG) around the typical SLD-02 drawing.
- `document_status` tri-state (`official` / `concept` / `draft_override`)
  drives watermarks, `.concept`/`.draft` file suffixes, artifact metadata,
  UI copy and docx report captions.
- Concept issues scrub renderer `MISSING: <label>` markers by pattern, not by
  label text; a readiness manifest artifact carries the full issue register
  with per-artifact content hashes.
- SLD-03 renders at most six issues and prints an explicit "... and N more"
  note pointing to the manifest.

### Site Constraint Set V1 (P2 gate)

- `services/site_constraint_readiness_service.py` +
  `services/site_constraint_set_service.py`: nine input groups (CRS, boundary
  polygon, POI location, routes, fire/maintenance, footprint catalogue, MV
  corridor, rule basis, by-others interfaces) must be present before any
  future Concept Master Layout is unlocked.
- Incomplete uploads persist as `draft_incomplete` with audit history.
- Registration rejects a constraint set whose `source_run.run_id` names a
  different run.

### Rename and fixes

- "Site Layout" page renamed to "Typical AC Block Arrangement" everywhere
  (nav with legacy alias, login copy, reports, docs); layout artifacts carry
  a concept watermark.
- `artifact_service.load_artifact_bytes_from_db` reads value tuples inside
  the session scope (no detached ORM access).
- Layout plugin emits per-artifact metadata dicts (no shared-dict aliasing).
- Official documents reuse the already-rendered PNG instead of re-rendering.

## 2. Deferred items (low priority, tracked here)

1. `ui/site_layout_view.py` reloads the persisted Site Constraint Set from
   DB+disk on every Streamlit rerun — cache in `st.session_state` keyed by
   run_id, invalidated on register.
2. Uploaded Site Constraint Set JSON has no size cap before persistence.
3. Concept value scrubbing is a post-render regex in
   `sld_pipeline_service._concept_safe_svg`; the cleaner design is for the
   renderer to emit placeholder text directly from `document_status`.

## 2.1 SLD drawing quality hardening (2026-07-15)

Professional redraw of the transformer symbols (3-winding = three interlocked
equal circles per IEC 60617/ANSI 315; winding marks derived from the vector
group), label/wire collision fixes, and a rendered-SVG quality gate
(`validate_rendered_sld_svg`) that asserts geometry on the actual SVG output.
Root-cause analysis and binding rules for all future diagram work (including
P2 Master Layout): `DIAGRAM_QUALITY_GOVERNANCE_2026-07-15.md`. Regression
baseline case01 regenerated.

## 2.2 AC Block product & arrangement knowledge base (2026-07-18)

`AC_BLOCK_PRODUCT_KNOWLEDGE_2026-07-18.md` records the 5.015 MWh product
construction, owner-confirmed appearance rules (mirrored pairing, roof vents on
the no-door edge, cooling-bay and end-face composition, livery positions), the
international arrangement code basis (IFC/NFPA 855/NFPA 850/UL 9540A — owner
decision: no GB), the Sineng/NR-based PCS & MV Station composition of the AC
Block, and site-array logic. The parametric concept renderer lives at
`docs/concept/ac_block_concept_render.html`. Feed both into P2 Master Layout
and any future 3D rendering work. The staged implementation plan (L1 unit
arrangement engine → L2 site-array concept → L3 Master Layout, plus report
integration as §8 upgrade / new §9) is `LAYOUT_ROADMAP_V1_2026-07-18.md`.

## 2.3 Active Claude handoff: 10 MW / 8 PCS / 8 DC (2026-07-24)

Before changing code, read
`CLAUDE_HANDOFF_10MW_8PCS_8DC_2026-07-24.md` in full. It records the
owner-confirmed bilateral 4+4 `田`-shaped DC arrangement around one central,
vertically placed 40 ft AC Block, the recommended governed-configuration
upgrade, open engineering decisions, and the recovery boundary that was used
for the mixed worktree.

Recovery completed on 2026-07-24: the invalid linear 1:8 draft was surgically
removed while the previously verified L2 Site Array and report integration
were preserved. `compileall`, the 23-test L2 target set, and the full suite
(`326 passed`) are clean. The governed bilateral 4+4 1:8 configuration remains
an implementation task; it is not present in this recovered baseline.

## 2.4 Governed AC Block 10 MW / 8 PCS / 8 DC — Phase A (2026-07-24)

The bilateral 4+4 1:8 configuration handed off in §2.3 is now implemented as a
**governed configuration** (Phase A). See
`GOVERNED_AC_BLOCK_10MW_8PCS_8DC_2026-07-24.md`.

- `schemas/governed_ac_block_config.py` (new) is the single contract
  (`ACBLK-10MW-8PCS-8DC-40FT-BILATERAL`) that threads
  `configuration_code` / `layout_variant` through AC Sizing -> SLD -> Layout ->
  Site Array -> Report. Phase A gate: `dc_blocks_total % 8 == 0`; mixed tails
  stay deferred.
- `calb_diagrams/ac_block_bilateral_layout.py` (new) is the
  `central_40ft_bilateral_4plus4` engine emitting per-equipment placements
  (~18.79 × 13.02 m envelope), not just one envelope.
- SLD render layer gained a LV-secondary busbar collision fix for wide feeder
  counts (8 PCS split 4+4); no topology/sizing change. The
  `[1,1,0,0]` dangling-PCS defect was re-verified and remains repaired at the
  physical-connection layer.
- Provisional engineering values (transformer MVA/vector group/Uk%/LV V/cooling,
  actual 40 ft dims, aisle/pair-to-pair gaps) stay gated as `None` and are never
  inferred. Frozen sizing is unchanged (`git diff` over frozen modules empty).
- L2 Site Array / report integration from `252bc75` preserved unchanged.
- Report-layer consistency (Phase A finishing): the report no longer fabricates
  a transformer nameplate for governed configs (no silent 10 MW / 0.9 = 11.11
  MVA), report §8 routes to the bilateral engine by `layout_variant`, and the
  linear §9 site figure is suppressed for the bilateral variant. Ungoverned
  runs unchanged; locked by `tests/unit/test_report_governed_consistency.py`.

### 2.5 Governed AC POI power-closure gate (2026-07-27)

- `services/governed_ac_block_service.py` now evaluates the already-selected
  governed PCS capacity at the POI plane using the Stage 1 MVT, MV
  cable/switchgear and HVT efficiency handoff. It does not change a sizing
  formula or synthesize a smaller station configuration.
- A governed output is held when it cannot meet POI power or exceeds the
  temporary 10% POI oversize safety ceiling. The 200 MW / 202 DC example
  (252.5 MW installed PCS; approximately 249.23 MW deliverable at POI) is
  therefore held at approximately 24.6% excess instead of being persisted as
  a valid AC, SLD or report selection.
- The AC page now prefers the Stage 1/3 POI P/E handoff over legacy summary
  aliases. SLD rejects historical governed snapshots without a passing
  persisted POI-closure record, so an old one-DC-to-one-PCS result cannot be
  rendered as a current engineering selection. A physically usable smaller
  PCS/station mix remains a separate DC-augmentation and connection-contract
  implementation; it must not be represented by an average DC split.

### 2.6 AC-to-SLD transformer vector-group contract (2026-07-27)

- `sld/transformer_vector_group.py` is the shared authoritative parser for
  every AC Sizing route.  It requires exactly one declared LV vector token per
  independently drawn LV winding: `Dyn11` is valid only for a two-winding
  transformer; `Dy11y11` / `Dy11-y11` declares two LV windings.
- SLD strict mode rejects a vector/topology mismatch. Draft mode renders `TBD`
  without inferring a neutral or earth connection. `n` only means the neutral
  terminal is brought out; all `y` / `yn` / `z` / `zn` vector tokens render as
  a plain Y unless a future explicit grounding-design contract is provided.
- For governed catalogue products, product vector data cannot be silently
  overridden by a conflicting Engineering Settings value. The conflict is
  explicit (strict rejection or draft `TBD`). Engineering V2 SVG regression
  tests assert actual winding elements and the absence of earth-bar elements,
  including both low-voltage windings for `Dy11y11` and a `Dyn11` two-winding
  path.
- The approved `case01` regression fixture now explicitly declares its two
  LV neutral terminals as `Dyn11yn11`; normalized topology/render baselines
  are regenerated through `scripts/generate_sld_regression_baseline.py`.
- Generic AC Sizing no longer auto-selects a three-winding transformer merely
  because an AC Block has more than two PCS.  New runs, and legacy runs without
  an explicit confirmation marker, require the operator to select the actual
  secondary arrangement before they can be issued.  A three-winding selection
  warns that an OEM-declared vector group with two LV tokens is required.

### 2.7 Mixed AC Block station → SLD head-fleet projection (2026-07-28)

- The opt-in mixed AC Block station (head + tail models; report §6.1 schedule)
  produces a non-uniform `pcs_count_by_block`. The SLD authoritative contract
  is uniform-only *by design* — `schemas/sld_authoritative_input.py` requires
  `pcs_count_by_block` uniform in SLD V1 — so feeding a mixed output straight to
  `adapters/ac_to_sld_adapter.py` fails the contract (the adapter rebuilds a
  uniform plan from the scalar `pcs_per_block` and it no longer matches the true
  per-block lists). A mixed run therefore could not render an SLD at all.
- `services/ac_mixed_station.py` gained `head_fleet_ac_output_for_sld()`: it
  projects a (possibly mixed) AC output onto its **head AC-Block fleet** — a
  genuine uniform sub-station of the real site (same PCS count/rating; DC Blocks
  may still fill unevenly, which V1 permits), nothing fabricated. The tail
  model(s) remain fully described by the report §6.1 schedule.
- `ui/single_line_diagram_view.py` detects `ac_block_mixed` and swaps the
  resolved `ac_snapshot` for this head-fleet projection, with an explicit note
  that the SLD shows the representative head fleet and that tails live in the
  report. Uniform stations (including single-model, uneven-DC ones) are
  unaffected — the projection is an identity for them.
- A true **per-model mixed SLD** (drawing head *and* tail blocks) is a deferred
  enhancement; it requires extending the versioned uniform invariant plus the
  topology builder and renderer, out of scope for this manual-adjustment layer.
  (Note: "per-model mixed SLD" is a *data-contract* feature and is unrelated to
  the "Engineering V2" renderer mode in the SLD dropdown.)

### 2.8 Mixed AC Block station → report §8/§9 head-representative (2026-07-28)

- Follow-up audit of the mixed-station chain: the report's §8 (Typical AC Block
  Arrangement) and §9 (Concept Site Arrangement) still drew from the *fractional
  average* `dc_per_ac = round(dc_total / ac_total)`, which for a mixed station is
  a block that exists nowhere — inconsistent with §6.1 (head/tail schedule), §7
  (SLD head fleet) and the interactive Layout page (already per-block via
  `plugins/layout_engineering_plugin.py`, which reads `pcs_count_by_block[idx]`
  and the per-block `dc_allocation_plan`).
- `reporting/report_v2.py` gained `_representative_dc_per_ac()` /
  `_mixed_head_entry()`: §8 and §9 now draw the **Head AC Block** for a mixed
  station (identity/average for uniform, including single-model uneven-DC), with
  an explicit note pointing to §6.1. §9's whole-site power/energy come from the
  actual head + tail sizing (`total_ac_mw`, `dc_total_energy_mwh`) rather than a
  uniform multiplication of the head block, and the "DC/block" label is replaced
  by a mixed head + tail descriptor.
- Not changed (by design / flagged for later): the manual-mixed toggle is not
  gated from a governed run — a run carrying both `configuration_code` and
  `ac_block_mixed` is an untested combination (governed §9 vs manual §6.1); and
  the mixed editor allows a per-row PCS rating that the SLD head-fleet does not
  render for tails. Both are low-priority edge cases, not regressions.

### 2.9 Mixed AC Block station — formality boundary hardening (2026-07-28)

Review follow-up (Codex) closing three engineering-integrity gaps so a mixed
station is never mistaken for a formal engineering result:

1. **Product nameplate attribution.** A bound catalogue product only matches the
   HEAD spec; applying its transformer nameplate across a differing tail and
   labelling it "per block" was a false attribution. `ui/ac_view.py` now
   **disables single-product binding for a mixed run** (skips
   `product_transformer_overrides`, records `ac_block_product_binding_suppressed`)
   so every model falls back to a MW ÷ PF estimate; uniform runs keep the
   confirmed nameplate. Per-model product binding is future work.
2. **SLD formality.** The head-fleet projection was only forced non-official
   *incidentally* (head DC total ≠ whole DC total). `sld_formal_readiness_service`
   now raises an **explicit `representative_head_fleet_only` error** when
   `sld_representative_of_mixed` is set (→ `document_status=concept`, CONCEPT
   watermark, `not_for_construction`), and **suppresses the incidental
   head-vs-whole total/energy mismatches** so the drawing carries an honest
   reason. The marker is also threaded into `sld_pipeline_meta`.
3. **Validation boundary.** The manual table validates DC sum / feeder capacity /
   raw AC MW only — not per-model OEM data or full POI-efficiency capacity
   closure. It is now explicitly labelled **concept/draft** in the AC Sizing UI
   and in report §6.1, directing the user to confirm per-model product and
   transformer data before formal use.

### 2.10 SLD transformer-winding formality + renderer dropdown (2026-07-28, in progress)

Review of a rendered SLD (uniform 25×2-PCS station) surfaced that a
three-winding transformer with an unconfirmed vector group draws three "TBD"
winding circles behind a DRAFT watermark — not a readable engineering drawing.
Owner direction: (1) never pass a TBD-winding three-winding SLD off as a normal
drawing; (2) drop the legacy renderer from the public dropdown; (3) backfill AC
Block product topology / vector group / LV arrangement with standard defaults
marked *assumed, pending confirmation*; (4) add real page-export acceptance for
two-winding/`Dyn11` and three-winding/`Dyn11yn11` (plain Y, no earth bar,
busbar structure, PNG).

Landed so far (this increment):
- **#2 done** — `sld_renderer_mode_service` gains `PUBLIC_SLD_RENDERER_MODES`
  (`engineering_v2` only) + `DEV_ONLY_SLD_RENDERER_MODES` (`legacy_server`);
  `is_sld_renderer_mode_public`. The SLD page dropdown offers only the public
  mode; legacy is reachable only behind the dev entry `?sld_dev=1`. Legacy stays
  in `AVAILABLE_*` for dev tooling/tests.
- **#1 formality gate done** — `sld_formal_readiness_service` now raises
  `transformer_vector_group_unconfirmed` (missing/TBD) or
  `transformer_vector_group_topology_mismatch` (wrong LV-token count for the
  winding count), reading the authoritative resolved value from
  `canonical_input`. Strict build already *requires* a vector group; this makes
  the draft/TBD path carry an explicit non-formal reason.

- **#1 renderer placeholder done** — `sld_engineering_v2_renderer` now draws an
  explicit dashed "TRANSFORMER / VECTOR GROUP / UNCONFIRMED / NOT A DRAWING"
  placeholder (with connection stubs so surrounding conductors still resolve)
  whenever the vector group does not parse into one LV token per winding, instead
  of winding circles annotated `TBD`. Confirmed vector groups are unaffected
  (regression baseline regenerated only for the two added CSS classes).
- **#3 product-data defaults done** — `ac_block_transformer_defaults.normalize_ac_product_transformer_fields`
  derives `transformer_topology` / `lv_winding_count` / `lv_arrangement` from a
  stated datasheet vector group, flags ambiguous datasheet text as
  `unconfirmed`, and only otherwise fills a conservative single-LV-winding
  default (`Dyn11`, `common_single_lv_busbar`) — never a PCS-count three-winding
  guess (honours §2.6) — with a `*_basis` marker
  (`datasheet` / `derived_from_vector_group` / `standard_default_pending_confirmation`).
  Applied in `seed_ac_block_products`; the matcher already reads these fields.
- **#4 export acceptance done** — a two-winding/`Dyn11` and three-winding/`Dyn11yn11`
  render assert single vs two LV windings, `NO LV BUS TIE`, plain-Y windings, an
  identical ground-symbol count between topologies (the extra LV secondary adds
  no earth bar), and a valid PNG.

Residual now closed (Codex review): the `*_basis` marker is threaded from the
product catalogue (`ac_block_product_match` exposes `transformer_vector_group_basis`,
`product_transformer_overrides` carries it onto the AC output) into
`sld_formal_readiness_service`, which raises
`transformer_vector_group_assumed_default` when the basis is
`standard_default_pending_confirmation`. An assumed standard-default vector group
can therefore never back a formal SLD — only a `datasheet` /
`derived_from_vector_group` value can. Regression tests cover both.

### 2.11 SLD sheet redesign — AC Block boundary, single-PCS busbar, DC proportion (2026-07-28)

Owner-directed visual redesign of the engineering_v2 sheet (electrical logic
unchanged):
- **AC Block boundary** — a dashed blue boundary (`ac-block-boundary`) is drawn
  around the RMU + step-up transformer + PCS (down to just above the DC Blocks),
  so the sheet reads as one physical AC Block skid.
- **Single-PCS LV winding** — when a transformer LV winding serves a single PCS
  there is nothing to bus, so no LV busbar line / tap junction is drawn; the
  secondary connects straight to that one PCS feeder. Windings with ≥2 PCS keep
  the busbar.
- **DC Block proportion** — the DC Block symbol is enlarged to a container-scale
  box (116×84, larger than the 80×60 PCS) and the row is raised to clear the
  title block, visually balancing the AC Block boundary. Symbol size is a
  drawing convention, not a physical footprint. Regression baseline regenerated.

### 2.12 Report rule — concept figures are ALWAYS NOT FOR CONSTRUCTION (2026-07-28)

**Firm owner rule (record permanently):** every concept engineering figure in the
exported report — the SLD (§7), the Typical AC Block Arrangement (§8) and the
Concept Site Layout / Arrangement (§9) — is stamped
**`DRAFT / OVERRIDE - NOT FOR CONSTRUCTION`** *unconditionally*, no matter how
professional the SLD is drawn or how the typical arrangement / site layout
resolves. The exported report is a concept / proposal document and is never a
construction-issue drawing set.

- `reporting/report_v2.py`: `_stamp_not_for_construction()` overlays the mark in
  the same style/format as the SLD-pipeline watermark (`#B42318` @ 0.28 opacity,
  bold, horizontal-centred). `_add_concept_figure()` routes every §7/§8/§9 figure
  through the stamp before embedding, so the mark is present regardless of the
  figure's own document status (even an "official" SLD is stamped in the report).
  Every §7/§8/§9 Figure caption also carries `NOT FOR CONSTRUCTION`. Enforcement
  is **fail-closed**: if a figure cannot be stamped, `_stamp_not_for_construction`
  substitutes a visibly-marked red placeholder (`_watermark_failure_placeholder`)
  — never the original drawing — and if even a placeholder cannot be produced
  (Pillow unavailable) it raises `WatermarkError` so the report aborts rather than
  emit an unmarked figure. `tests/test_report_watermark_fullreport.py` renders the
  whole DOCX (non-governed and governed paths) and asserts every §7/§8/§9 concept
  figure embedded in the report carries the red mark, that no un-watermarked source
  image leaks through, and that every §7/§8/§9 caption states NOT FOR CONSTRUCTION.
- Any new report figure that depicts an engineering drawing MUST be embedded via
  `_add_concept_figure` (never a bare `doc.add_picture`).

## 3. Next boundary

The package deliberately stops before a Concept Master Layout. Unlocking it
requires (in order): a registered complete Site Constraint Set, a controlled
equipment footprint catalogue, a deterministic geometry validator, and an
explicit project/authority rule basis. Do not extrapolate site geometry from
the AC Block index. See `SITE_CONSTRAINT_SET_V1.md` and
`SLD_PROPOSAL_PACKAGE_V1.md`.

## 4. Maintenance decomposition plan

Motivation: the repo is now ~30k lines of source plus 7k lines of tests.
Every agent session (Codex/Claude) that starts from zero re-reads large parts
of the tree, which is slow and error-prone. The codebase already has clean
seams; maintenance should exploit them instead of scanning everything.

### 4.1 Module map (2026-07-12, arrangement/layout rows updated 2026-08-04)

| Domain | Packages | Size | Change frequency |
| --- | --- | --- | --- |
| Sizing core (FROZEN) | `services/stage*_service`, `dc_pipeline`, AC capacity/calculation services | part of `services/` (29 files, 6.3k lines) | Frozen — no edits without explicit logic-upgrade approval |
| **Admin DC product / curve preflight** | `services/dc_product_curve_guard.py`; caller in original `ui/dc_view.py` | ~0.12k lines | Low — inspects the exact frozen picker's selection and linked cell before a new Admin run. Preserves the approved legacy 314Ah-A basis; rejects unrelated or unverified cells and explicit curve conflicts. No product fallback, curve resolver, new publication workflow, saved-result rewrite or sizing arithmetic. |
| SLD engine | `sld/` (18 files, 3.1k), `services/sld_*`, `schemas/sld_*`, `schemas/ac_electrical_topology.py`, `schemas/governed_ac_block_config.py`, `adapters/ac_to_sld_adapter.py`; mixed→SLD bridge in `services/ac_mixed_station.py` (`head_fleet_ac_output_for_sld`) | ~6k lines | High — owns AC-to-SLD physical topology contract and the governed AC Block configuration; SLD V1 is uniform-only, so mixed stations render via a head-fleet projection; remains the most active area |
| Diagram renderers | `calb_diagrams/` (incl. `ac_block_bilateral_layout.py`) | ~6.9k lines | Medium — renderer/template + governed layout-variant engines |
| **Typical AC Block Arrangement (contract)** | `calb_diagrams/typical_ac_block_arrangement.py` | ~0.4k lines | **Low, but load-bearing** — SOLE owner of the engine-selection rule, the drawing title, the shape resolution from a run, and the CONCEPT marking. The exported report (`reporting/report_v2.py` §8/§9) and the web page (`plugins/layout_arrangement_v2_plugin.py`) are both thin callers; neither may reimplement any of it. `tests/unit/test_typical_ac_block_arrangement.py` holds the two surfaces byte-identical. |
| Arrangement geometry | `calb_diagrams/ac_block_arrangement_v2.py` (linear row + SHARED equipment glyphs), `ac_block_bilateral_layout.py` (central-station 4+4) | ~1.3k lines | Low — geometry is owner-ruled; both engines draw through the shared `draw_dc_container` / `draw_mv_station` glyphs |
| Site array (L2) | `calb_diagrams/site_array_concept.py`; `mixed_site_concept.py` (manual MIX rows, conservative concept road grid, shared block geometry; consumed by report and original Layout page) | ~0.7k lines | Medium — owns the minimum-land packing search, the connected fire-road loop and the reported land metrics; tiles any `BlockForm`, including a central-station block via its real placements |
| Layout / constraint gate | `plugins/layout_*`, `services/site_constraint_*` | ~1k lines | Medium — P2 Master Layout work lands here. `services/layout_service.ARRANGEMENT_PLUGIN_ID` names the ONE arrangement renderer the page offers |
| **AC alternatives (identity)** | `services/ac_run_service.py` | ~0.4k lines | **Low, but load-bearing** — SOLE owner of what makes two AC schemes different (the original scalar identity plus actual per-row PCS model / DC allocation for true MIX, the gate against over-splitting) and of how siblings are NAMED (`ac_alternative_label`, oldest-first `A`/`B`/…). Standard / historical no-row hashes stay unchanged. Legacy MIX reuse requires the saved output's complete new identity to match, so changing only a tail PCS rating cannot overwrite another alternative. Optional comparison attachments do not mint a formal AC alternative. Report file names, covers and provenance quote the service's label; no other module computes it. Its snapshots are the per-alternative configuration `sld_data_source_service` reads back. |
| **AC alternative resolution** | `services/sld_data_source_service.resolve_preferred_ac_snapshot`, `state/workspace_state.artifact_run_id()` | ~0.3k lines | **Low, but load-bearing** — the two places that answer "which alternative am I working from": one for INPUTS (the AC snapshot), one for OUTPUTS (the artifacts). Both read `active_ac_run_id` themselves. A page that decides this for itself is the defect pattern that gave the arrangement two implementations. |
| **DC run persistence / restoration** | `services/run_persistence_service.py`, `services/run_restore_service.py` | ~0.4k lines | Low — owns the existing full DC input/output payload hash and restoration checks before session adoption. Original three modes only; comparison results are not adopted runs. Hashless old runs remain compatible; AC alternative identity hashes are a separate contract. No sizing arithmetic or tail revision/topology adoption is owned here. |
| **Reduced-string DC comparison** | `services/dc_reduced_string_tail_service.py` | ~0.42k lines | Bounded adapter — validates the owner-authorized 314Ah capacity chain and exact maintained parent/child; evaluates N-k mains plus k identical tails, k=1..4, with the original Stage2 item builder and Stage3; owns saved comparison/restore checks. Single-tail version 1 remains compatible; multiple-tail version 2 is DC-only. No new search, active scenario or AC topology adoption. The existing `ui/dc_view.py` owns the original Advanced option, Run, shared result display and Next buttons. |
| **Reduced-string DC report** | `reporting/dc_tail_report.py`; optional download in `ui/dc_view.py` | ~0.25k lines | Read-only standalone DOCX for the owner-requested special DC comparison. Consumes the service-validated saved attachment, shows the standard baseline, unchanged count, actual BOM, guarantee-year energy/power checks, selected curve rates and annual results. No independent database record, sizing calculation, adoption or change to the original technical/proposal exports. |
| **Reduced-string AC nominal review** | `services/dc_tail_ac_review_service.py` | ~0.3k lines | Local bounded adapter — consumes the validated saved DC comparison and original AC rows / feeder plan, replacing only the last physical DC slot in its review. Owns explicit nameplate-share DC reference, separate PCS AC checks and unknown-output handling, winding disclosure, review identity and saved-content consistency. `ui/ac_view.py` remains the only AC form / Run / result / Next. No original sizing arithmetic, actual tail adoption, new equipment capability register or diagram engine is introduced. |
| **Reduced-string SLD comparison preview** | `services/dc_tail_preview_service.py`, `services/dc_tail_preview_source_service.py`, `sld/tail_comparison_preview.py`; optional area in `ui/single_line_diagram_view.py` | ~0.5k lines | Local read-only last-physical-group preview. Exact authorized saved DC/AC child and complete payload checks precede the adapter; separate SVG consumes validated physical links, never Head-fleet averages. No standard SLD/artifact publication, new generation workflow or actual tail adoption. Original SLD pipeline and customer report remain the standard branch. |
| **DC inventory handoff** | `adapters/session_state_adapter.py::build_dc_bom_handoff`; optional consumer in `services/dc_tail_preview_service.py` | ~0.15k added lines | Reads actual canonical Stage2 BOM, preserves source subtotals/total and per-unit display precision; validates quantities and rounding bounds. Inventory ordinals are not physical/electrical mapping. No permanent one-tail/last-position/exclusive-SKU constraint; no adopted scenario or change to legacy summary/stage13 scalars. Preview cross-checks assigned products, quantity, capacity and distinct physical units. |
| Reporting | `reporting/` (5 files, 1.4k) | 1.4k lines | Low — two original customer-facing DOCX surfaces (plus the owner-requested 2026-10-27 standalone DC comparison described above): `report_v2.export_report_v2_1` (the proposal, from the Report Export page) and `dc_view.build_report_bytes` (the DC page's technical export). `export_docx` is now shared DOCX primitives plus `create_dc_report`, which is the REGRESSION BASELINE pinning the DC page's export — not a product path, and not to be given callers. Owner ruling 2026-08-08 deleted `create_ac_report` / `create_combined_report` and the 413 lines only they reached; `export_docx` embeds no engineering drawing at all now, which `test_watermark_choke_point` enforces. Wording/section changes; the AC alternative label is CONSUMED here (file name, cover, provenance), never derived. A figure that could not be READ is never reported as one that was never GENERATED — `ctx.artifact_read_failures` carries the distinction from `artifact_service.load_artifact_bytes_with_failures` into §7/§8 (owner ruling 2026-08-08, 读取失败重新读取). **Carries no QC/validation layer**: the report states what the run produced. Consistency belongs upstream — `services/dc_input_guard_service` before sizing, the §6/§6.1/§9 schedules for disclosure. Owner ruling 2026-08-08 removed `report_v2._validate_*` / `_aggregate_ac_block_configs`, `report_context.validate_report_context` and `ReportContext.qc_checks`: nothing in the product ever called them, and their uniform-station arithmetic (blocks × per_block) mis-stated every mixed governed site. Do not reintroduce a validator here without a caller. |
| Web UI | `ui/` (18 files, 6.7k), `state/`, `app.py` | ~7.5k lines | Medium — copy and workflow polish. `ui/dc_view.py` sizes each mode ONCE (2026-08-08): the snapshot it persists and the tuple it displays are the same run, derived by `snapshot_to_legacy_tuple`. A page that sizes again for the DB is the defect that was removed; `tests/unit/test_dc_page_sizes_each_mode_once.py` asserts it by AST. |
| Platform | `infra/` (36 files), `db/`, `importers/`, `adapters/`, `migrations/` | ~3.4k lines | Low — deployment/migration driven |

### 4.1b Data model — owner rulings 2026-08-04

2026-10-17 local-only cabinet AC interface: `services/cabinet_ac_preview_service.py`
owns the owner-confirmed 1..12-cabinet independent-group mapping and conceptual
PCS candidate enumeration. The standalone `ui/cabinet_ac_preview.py` is now
disconnected from the application: the owner requires the original continuous
AC save -> SLD -> layout -> report workflow. Its earlier AC-page bypass has
been removed. Keep it as an offline design reference until the group contract
can be integrated into the existing workflow with downstream acceptance tests.
DC snapshot adapters carry explicit source product codes for applicability.
The frozen DC K_MAX_FIXED=10 and existing container AC engine remain unchanged.


2026-10-13 addition to the Web UI / data-review domain: the existing admin
Degradation page calls `ui/supplier_degradation_preview.py`; its read-only
parser is `services/supplier_degradation_service.py`. It retains supplier
SOC/Power Rate labels, source-cell provenance, missing years and source hash.
It does not publish curves, replace SOH/RTE master data or change sizing.

2026-10-13 candidate-persistence extension (owner requested): the same UI uses
`services/supplier_degradation_library_service.py` to save/reopen immutable
source versions in `infra/db/models/supplier_degradation_import.py`, migration
`20261013_0010`. Original XLSX bytes, normalized source curves, hash, actor and
audit are stored atomically; duplicate file hashes reuse the existing version.
Review exports now use `services/supplier_degradation_export_service.py` for
formatted XLSX: annual tables with 0.00% number formats, charts, separate common
and extended cases, source-point detail and conditional duty timing checks.
Long IDs stay in the database, not the presentation workbook. This responsibility belongs to admin data
management / Platform, never Stage 1/2/3. Candidate-only DB constraint and no
activation API keep the existing SOH/RTE and sizing selection untouched.

2026-10-13 browser UX follow-up: `UI_REVIEW_2026-10-13.md` records native browser
observations and scoped fixes in admin / Workbench / app sidebar. Saved source
versions reopen by default, source filters and percentage display are compact,
and catalogue/source definitions remain separate. These are presentation and
session-navigation changes, not active curve selection or sizing parameters.

**Project → Case → Run**, and what each layer means:

| Layer | Meaning | Mutability |
| --- | --- | --- |
| `Project` | commercial entity; `project_code` globally unique | long-lived |
| `SizingCase` | **一个方案 x 一个 scenario**, inside one project | mutable — `input_json` tracks the latest successful run |
| `SizingRun` | one execution, immutable, input + output each stored with a content hash | append-only |

**Case identity is `(project_id, case_code)`** (owner ruling A, 2026-08-04). A Case
is 方案 x scenario, so one code means one scenario and the scenario belongs IN the
code. Two projects may reuse a code. Reusing a code under a second scenario is a
naming clash and is refused in plain words, not as an IntegrityError. Migration
`20260804_0008`; locked by `tests/unit/test_case_identity.py`.

**Artifacts** are files on disk under `outputs/artifacts/<run_id>/<plugin_id>/`,
registered in `artifact_registry`. The stored `file_path` is **relative to the
outputs directory** so the database stays portable; a path outside that tree, and
any row written before 2026-08-04, stays absolute and still resolves. Always read
through `artifact_service.resolve_artifact_path` — never `Path(row.file_path)`.

**AC alternatives branch off a DC run** (owner ruling B, 2026-08-04, step 1 done).
`sizing_run.parent_run_id` is self-referential with CASCADE, and
`services/ac_run_service.persist_ac_run` records one run per DISTINCT AC
configuration under its DC run. Identity is a hash of the 17 fields that actually
decide a scheme — PCS count and rating, transformer size and topology, LV winding
count, the DC allocation plan, the bound product — so recomputing an unchanged
configuration reuses its run and the table counts alternatives tried, not clicks.
An AC run does not duplicate a Case: `SizingCaseInput` has no AC field at all,
which `test_ac_run_service.py` verifies rather than assumes.

**Drawings follow the alternative** (step 2 + 3 done 2026-08-04). SLD and
arrangement artifacts attach to the selected AC run;
`load_artifact_bytes_from_db` walks up `parent_run_id` NEAREST FIRST, so an
alternative's own figure wins, one it never produced falls back to the DC run's,
and a pre-AC-run database needs no migration. Pages ask
`workspace_state.artifact_run_id()` — one helper, never a per-page decision.
`site_constraint_set` deliberately stays on the DC run: site boundary and access
do not change with an AC choice. The workbench shows an AC alternative switcher
only when a DC run actually has two or more.

**Reports are versioned per alternative** (step 4 done 2026-08-06). Both versions
used to download under the SAME file name, so the second silently replaced the
first — the "最终报告可以重新生成一个版本" half of ruling B was still open.
`ac_run_service.ac_alternative_label(dc_run_id, ac_run_id)` names the siblings
`A`, `B`, … **oldest first**, so a later alternative never renames an earlier one
(and `list_child_runs` now orders by `started_at, sizing_run_id` so a clock-tick
tie cannot swap two labels between calls). The label reaches
`ReportContext.ac_alternative_label`, the proposal file name
(`..._V2.1_AC-B.docx`), the cover, and the Document Provenance table.
**It is None when the DC run has only one alternative** — the ordinary report's
file name and wording are unchanged, which
`tests/unit/test_report_ac_alternative_versioning.py` holds in both directions.

**Regeneration follows the alternative too** (step 5 done 2026-08-06, ruling B
now fully landed). `load_persisted_ac_snapshot` used to read "the last AC saved
on this DC run", so regenerating on alternative A after B was saved fed A's
figures with B's parameters. It now takes `ac_run_id` and prefers that
alternative's own `ac_case_input` / `ac_sizing_output` — snapshots
`persist_ac_run` ALREADY writes from the same dicts, so this adds no storage and
needs no migration; anything an alternative has not recorded falls back to the
DC run's runtime snapshot, which is all a pre-AC-run database has.
`run_id` stays the DC run: it is the identity anchor the pages cross-validate
against, and a selection pointing at another DC run's branch is refused rather
than used. `resolve_preferred_ac_snapshot` reads `active_ac_run_id` itself —
same rule as `artifact_run_id()`, the decision lives in ONE place. AC sizing
now selects the alternative it just saved (`clear_downstream=False`, because
that session state IS the alternative's).

Step 5 opened one hole and closed it in the same breath, worth stating because
it is not obvious: the identity hash covers 17 fields, so a re-save can carry
NEW content under the SAME identity (a renamed case, an edited input that does
not change the scheme) and the run is REUSED. Once the alternative's own
snapshots became what the pages read, leaving them at the first save served
stale values — something that could not happen while the DC runtime snapshot
was rewritten every time. `_refresh_alternative_snapshots` re-records them
**only when the content actually differs**, so an unchanged re-run still writes
nothing and 行数 = 真正试过的方案数 still holds. The refreshed input row keeps
the IDENTITY hash, never a hash of its payload — `find_child_run_by_hash`
matches on it, and changing it would orphan the alternative and mint a
duplicate. `prune_snapshot_generations` now covers input snapshots for the same
reason, and that is safe because every input row of one AC run carries that same
identity hash.

**Still deliberate, not debt**: `site_constraint_set` stays on the DC run, and
`external_layout_service` resolves "last AC saved" — an external caller passes a
run id and has no alternative context.

**Bounded growth** (owner requirement 2026-08-04: 日志和数据库不能无限制的变大).
Measured on a working checkout before the fix: 479 run directories, 5081 files,
172 MB — all of it written by the TEST SUITE into the real `outputs/`. Controls
now in place, at the source and after the fact:

| store | control |
| --- | --- |
| test artifacts | `tests/conftest.py` redirects `CALB_OUTPUTS_DIR` to a temp dir |
| artifact files + rows | each `(run, kind, artifact_mode)` lineage keeps the newest generation only (`CALB_ARTIFACT_GENERATIONS`, default 1) |
| orphaned rows (row without file) | `maintenance_service.prune_orphaned_artifacts` |
| orphaned files (file without row) | `prune_unreferenced_artifact_files` — **counts, does not delete**, unless `CALB_PRUNE_UNREFERENCED_FILES=1` |
| old artifacts | `prune_artifacts_older_than` — **row AND file together** (`CALB_ARTIFACT_RETENTION_DAYS`, 30) |
| run snapshots (input AND output) | `prune_snapshot_generations` (`CALB_SNAPSHOT_GENERATIONS`, 3) |
| audit trail | `prune_audit_log` (`CALB_AUDIT_RETENTION_DAYS`, 180 — longer than artifacts on purpose) |
| op log | `prune_oplog` (`CALB_OPLOG_RETENTION_DAYS`, 30) |

`deploy/docker/calb-maintenance.sh` now runs the database sweep BEFORE the file
sweep. It used to delete files only, leaving rows that pointed at nothing — and
because the reader swallows every error, an old run's report lost its figures
silently. Never prune one side alone. `storage_report()` gives the current
numbers so growth is measured rather than assumed.

**Re-measured 2026-08-06** (`find_unreferenced_artifact_files`): the source
control works — a full suite run adds **0** files to the real `outputs/`. What
remains is the pre-fix backlog, and it had no owner: every Python sweep worked
from the registry outward, so a file whose row was gone was reclaimed only by
the shell `find -mtime` in `deploy/docker/calb-maintenance.sh`, which runs
against `CALB_RUNTIME_ROOT` on the deployed host. **A developer checkout was
swept by nothing.** Local cleanup is now one command:

```powershell
python -m calb_sizing_tool.services.maintenance_service          # counts only
$env:CALB_PRUNE_UNREFERENCED_FILES=1; python -m calb_sizing_tool.services.maintenance_service
```

Counting is the default because an operator pointed at the wrong database sees
an empty registry, and a sweep that trusted it would call every artifact on disk
garbage. Two further guards: only `outputs/artifacts` is walked (`logs/` has its
own retention, `external_ai/` is user-facing), and a file younger than
`CALB_UNREFERENCED_GRACE_DAYS` (7) is never a candidate, so an artifact whose row
has not committed yet is safe. An unreadable registry deletes nothing at all —
`test_an_unreadable_registry_deletes_nothing`.

**Full execution record for this round**: `docs/WORK_RECORD_2026-08-06.md` —
what changed, why, how to verify each claim yourself, and the two items that
remain blocked on machine access rather than on engineering.

**The server was tunable only on paper** (found 2026-08-06). `calb-maintenance.sh`
runs the sweep INSIDE the app container, but `docker-compose.ubuntu.yml` passed
none of the database-side knobs — so every retention value an operator set in
`deploy/docker/.env` was discarded at the container boundary and the sweep could
only ever use its built-in defaults. The unreferenced-file sweep could not be
enabled at all. All seven are now in the `environment:` block with matching
defaults and documented in `.env.example`; `test_the_server_can_actually_tune_the_sweep`
holds it. Only `CALB_OUTPUT_RETENTION_DAYS` worked before, because that one is
consumed by the host-side `find` rather than by the app.

**`.gitignore` closed three ways junk reaches the public repo** (2026-08-06):
`*.docx` (a proposal carries customer figures and `export_docx` writes wherever
it is run from), `*.db` / `*.sqlite*` / `*-wal` / `*-shm` (a sizing database is
customer data; `var/` was covered but a stray path was not), and root-level
`/.env`, `/secrets.toml`, `/.streamlit/secrets.toml`. Root-anchored on purpose,
so the existing `deploy/systemd/*.env.example` negation still holds. No tracked
file is caught by any of them — verified with `git ls-files | git check-ignore --stdin`.

**Guest mode never touches the database**: the login page injects
`roles=["guest"]` with a synthetic `user_id`, and DC results live in
`st.session_state`. Note that `ensure_system_roles()` seeds only `admin` and
`normal_user`, so a persistent guest ACCOUNT cannot be created from the admin
portal — guest is the button, not a role row.

### 4.2 Working rules effective immediately (no code moves)

1. **Scope declaration first**: every task states up front which domains it
   touches. An agent reads only those domains plus this document — not the
   whole tree.
2. **This section is the navigation index**: update the module map in the
   same commit whenever a domain gains or loses responsibility, so future
   sessions can trust it instead of re-scanning.
2b. **One rule, one home**: the Typical AC Block Arrangement is published on two
   surfaces (report and web page). Its engine choice, title, shape resolution and
   CONCEPT marking live ONLY in `calb_diagrams/typical_ac_block_arrangement.py`.
   Adding a second copy in a caller is how this domain accumulated its 2026-08-03
   defect list (see `docs/LAYOUT_ARRANGEMENT_DEFECTS_2026-08-03.md`); an audit on
   2026-08-04 still found three live divergences hiding in shape resolution alone.
   Nothing dimensional may be hardcoded in a layout module — station size, block
   power and per-DC energy all come from the run.
3. **Frozen core stays frozen**: sizing formula modules are read-only;
   `git diff` review before commit must show no changes there (rule inherited
   from `OPTIMIZATION_EXECUTION_PLAN_2026-06-17.md`).
4. **Tests are partitioned by domain**: run the domain's tests during
   iteration; run the full suite once before commit.

### 4.3 Split roadmap (future, in order)

- **Step 1 — Import-boundary enforcement (cheap)**: add a lint/CI check that
  `ui/` imports only `services/` + `schemas/` + `state/`; `calb_diagrams/`
  imports nothing from `ui/` or `infra/`; sizing core imports nothing from
  SLD/layout/reporting. This makes the seams mechanical before any move.
- **Step 2 — Package extraction inside the repo**: promote `calb_diagrams` +
  `sld/` + diagram plugins into a `calb-diagram-engine` package with its own
  tests and doc index; reporting likewise. App remains one deployable.
- **Step 3 — Repo split (only if team/process needs it)**: diagram engine and
  sizing core become versioned dependencies of the web app. Do not split
  earlier than Step 2 proves stable, and never split the frozen sizing core
  away from its golden-case tests.

Trigger for Step 2: when SLD/Master-Layout work (P2) starts in earnest, the
diagram engine is the first extraction candidate — it is the largest
high-churn domain and has the fewest inbound dependencies.

### Local cabinet interface integration — 2026-10-17 (not deployed)

The original `ui/ac_view.py` owns the sole AC interaction and save/navigation path.
`services/cabinet_ac_preview_service.py` now also validates and binds the approved
1..12-cabinet independent group contract to existing AC allocations. No frozen
formula or allocation utility changed. `services/ac_run_service.py` includes the
optional contract in alternative identity; legacy hashes remain unchanged when absent.
`ui/cabinet_handoff.py` presents the persisted group schedule on existing SLD,
arrangement and report pages and blocks incompatible container rendering. Actual
cabinet drawing/layout/report support is pending. The standalone preview remains disconnected.

Latest local audit: see docs/LOCAL_OPTIMIZATION_AUDIT_2026-10-17.md. Original AC
alternative save must succeed before selecting it or publishing session output.
Raw product-import headers are checked before pandas can rename duplicates.
Persisted cabinet interfaces are validated before downstream presentation.
Compilation, 831 full tests and 39 extra DC/AC scope regressions passed. This is
not a release approval: cabinet drawings/layout/formal reports remain pending.

### Cabinet SLD module map addition — local only, 2026-10-17

SLD cabinet-specific rendering: `calb_diagrams/cabinet_sld.py` owns pure topology
and SVG generation; `services/cabinet_sld_service.py` owns concept artifact package,
strict selected-AC persistence/restoration, input/file hashes and verified-package
preview-sheet selection without database writes;
`ui/cabinet_sld_view.py` owns controls within the existing SLD page. The only
routing addition in `single_line_diagram_view.py` follows existing snapshot/context
validation. Container/mixed renderer and frozen sizing ownership remain unchanged.
See `CABINET_SLD_LOCAL_REVIEW_2026-10-17.md`. Cabinet concept SLD is implemented;
physical layout and formal cabinet report remain pending.

### Cabinet arrangement and report additions — local only, 2026-10-18

`calb_diagrams/cabinet_arrangement.py` owns symbolic equipment zones and source-bound
installation references. `services/cabinet_document_service.py` and
`cabinet_arrangement_service.py` own strict saved-child verification and immutable
all-sheet packages. `cabinet_report_data_service.py` copies verified persisted
DC/AC values; `cabinet_report_service.py` owns complete-package report provenance
and persistence; `reporting/cabinet_report.py` owns the cabinet-specific DOCX.
`ui/cabinet_document_context.py`, `cabinet_arrangement_view.py` and
`cabinet_report_view.py` stay within the original downstream pages. Container
engines and frozen sizing ownership do not move. See
`CABINET_ARRANGEMENT_REPORT_LOCAL_REVIEW_2026-10-18.md` for local validation and
the outstanding OneDrive installation-evidence read.

### Mixed AC report presentation and shared download panel — local, 2026-10-19

`reporting/report_context.py` reads actual saved manual mixed AC rows for the
report allocation summary; it does not rebalance them. `reporting/report_v2.py`
owns the mixed equipment schedule, representative-figure scope notes and truthful
mixed site-composition overview. Uniform and governed report paths remain intact.
`calb_diagrams/typical_ac_block_arrangement.py` remains the sole shape/title owner
for the page and report; manual mixed rows override a stale pre-adjustment product
label there, without changing geometry or engine selection.
`ui/report_download_panel.py` owns the common direct-download presentation used
by the existing container and cabinet report pages. Generation, readiness and
document provenance remain with their existing services/pages. No new pipeline
step, sizing responsibility or production release is introduced. See
`MIXED_AC_REPORT_LOCAL_REVIEW_2026-10-19.md` for validation and remaining limits.

### Customer report readability — 2026-10-19 follow-up

`reporting/customer_presentation.py` owns customer-visible text cleanup, issue-date
formatting, quantity grammar and removal of internal decision-history wording.
`reporting/report_v2.py` prints project/case/alternative/date information without
database run identifiers or storage state. Internal ReportContext and database
linkage remain unchanged. Customer report prose distinguishes the selected model
assessment year from a contractual commitment; sizing formulas, input values,
numeric schedules, drawing engines and alternative selection are unchanged.
