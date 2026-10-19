# Mixed AC proposal presentation — local review, 2026-10-19

Scope: report presentation, shared arrangement title/shape reading and report
download UI. The supplied project is a functional test case, not an approved
project design. No input correction or sizing rerun is part of this change.
The owner subsequently authorized publication and deployment after verification;
release execution and operational evidence are recorded in the local runbook logs.

## Defects and corrections

- A saved manual allocation of 4+4+2 DC Blocks was re-described as 4+3+3 by the
  report's generic balancing summary. Mixed reports now display the saved rows.
- A heterogeneous station was labelled as if every block used the Head model.
  The executive summary and Stage 4 schedule now distinguish models, actual block
  references, quantities, DC/PCS subtotals and installed PCS nameplate power.
- The original dropdown model name can survive manual equipment changes. The
  shared arrangement resolver now reads actual manual mixed rows for the selected
  block. Both web and report use that rule; geometry and engine choice remain
  unchanged. Tail-first and distinct PCS-unit-rating cases are covered.
- A whole-site drawing repeated Head footprints for Tail blocks and rounded
  12.50 MW to 12 MW. Manual mixed reports now provide the actual equipment
  composition and explicitly leave the dimensioned mixed site layout pending.
  Existing uniform and governed site-layout paths are retained.
- SLD and typical arrangement scope is identified as representative Head only.
  Neither is presented as a complete mixed-station engineering drawing.
- When a manual mixed case leaves POI frequency TBD but its saved AC input uses
  a frequency, the report and page disclose the assumption. They do not select a
  project frequency or alter the stored SLD.
- The isolated Downloads heading and empty button area are replaced by one
  shared Technical Proposal card and the existing direct English download action.
  No separate Generate step is introduced. Existing retrieval/readiness gates,
  brand handling, document bytes and filenames are retained.

## Validation

- `python -m compileall -q app.py calb_sizing_tool calb_diagrams`: passed.
- `python -m pytest tests -q`: **1018 passed**, 310.12 seconds.
- Frozen-canon hash checks pass; no protected formula module changed.
- A uniform container sample produced identical contents for all 23 DOCX package
  members using the old and revised report generators.
- The actual saved test alternative was reconstructed locally from a read-only
  production snapshot, without running sizing. Five DC Stage 1/2/3 tables,
  including all 21 annual rows, exactly match the original supplied DOCX.
- Saved SLD and arrangement files were checked against registry SHA-256 hashes.
  The new DOCX and PDF render were reviewed on all 11 pages.
- Shared page/report arrangement equality and original cabinet/container export
  interaction/retrieval tests pass in the full suite.

Customer documents, database copies, exact run identities and render evidence
remain in the local output directory and are not release source files.

## Practical limits

Native Computer Use could not connect to its Windows pipe after the documented
recovery attempt. This review therefore does not claim a fresh click-through of
the user's external browser or a visual acceptance of the live export card.
Streamlit interaction tests cover its behavior; final appearance can be reviewed
on the refreshed local system. Existing complete mixed-station SLD and physical
site-layout limitations remain explicit rather than being hidden by Head repeats.
