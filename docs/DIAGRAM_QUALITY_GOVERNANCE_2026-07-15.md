# Diagram Quality Governance — root-cause analysis and rules (2026-07-15)

Context: repeated agent sessions (Codex and others) fully understood the SLD
requirements — topology, vector groups, split secondaries — yet the rendered
drawings kept falling short of professional expectations (the 3-winding
transformer drawn as three detached circles, duplicated `Dyn11` labels, text
colliding with wires and the title block). This document records why that
happened structurally and the rules now in force so it does not recur in SLD
or in the upcoming Master Layout (P2) work.

## 1. Root causes (with evidence)

1. **QA ran on coordinates that are never drawn.**
   `sld_engineering_v2_validation.validate_sld_engineering_v2_layout` checks
   the *layout plan* boxes (e.g. transformer at `ac_section.y + 210`), but the
   renderer draws from `ProfessionalSldSheet` geometry plus local constants
   (transformer at `mv.transformer_y = 480`). Every overlap/text-fit check ran
   against a geometry that the SVG never contained, so a clean validation
   coexisted with a broken picture.

2. **No feedback loop on the rendered output.** All renderer tests asserted
   text presence (`"Dyn11" in svg_text`, element ids) — none asserted a single
   geometric relationship. An agent could pass the full suite while the
   transformer circles floated apart, because "the circles must interlock"
   existed only as intent, never as a constraint.

3. **Symbols had no intrinsic contract.** Winding circles, marks and labels
   were placed by magic numbers per call site (`lv_cy = y + 88.0`,
   `offsets = ±92`) with no invariant tying them together. Any tweak silently
   broke the visual relationship; nothing failed.

4. **Text had no collision model at render level.** Labels were emitted at
   fixed offsets with no clearance computation, producing the duplicated
   vector-group label, the nameplate crossed by LV routing, and the
   `DC Block #N / MWh` caption clipped by the title block.

5. **Symbol semantics were not linked to inputs.** The 3-winding drawing
   always drew `HV Δ + 2×grounded-Y` regardless of the vector-group input;
   correctness was coincidental (true only for Dyn11).

## 2. What changed on 2026-07-15

All in the SLD engine / diagram renderer domain; frozen sizing core untouched.

- `_transformer_split_secondary`: standard IEC 60617/ANSI 315 three-winding
  symbol — three **equal** circles, every pair interlocked (HV top, LV-A/LV-B
  below), LV lead labels beside their own leads, nameplate clear of wiring,
  explicit `Secondaries: 2 x yn11 (LV-A, LV-B)` note.
- `_transformer_2w`: properly interlocked two-circle symbol.
- `_parse_vector_group` + `_winding_mark`: winding marks (Δ / Y) are derived
  from the vector-group input; unparsable input degrades to a text annotation
  so the symbol can never contradict the nameplate. The earlier grounded-Y
  interpretation was superseded on 2026-07-27: `n` means a neutral terminal is
  brought out, not that the neutral is earthed.
- Duplicate standalone `Dyn11` label removed (nameplate is the single source).
- Defensive gate: a transformer declaring N LV windings refuses to render if
  the PCS groups resolve to a different count.
- Branch-wire invariant: DC branch horizontals must sit below every fuse
  outlet they collect.
- BESS captions and equipment-list panel no longer touch the title block.
- **Rendered-SVG quality gate** (`validate_rendered_sld_svg`): parses the
  actual SVG and fails on (a) winding circles that do not interlock or have
  unequal radii, (b) text intruding into the title-block band, (c) text
  anchored outside the frame. Wired into `render_sld_engineering_v2_svg` (as
  a returned warning) and into unit tests (hard assertions), with a
  planted-defect test proving the gate catches regressions.

## 2.2 Shared DC Block correction (same day, follow-up)

The first pass of the shared-DC drawing violated a standing owner rule
(recorded in the 2026-07-13 Codex session): **a PCS DC input must never share
a DC busbar with another PCS.** The drawing joined both PCS fuse outlets with
a horizontal conductor and junction dots — electrically a common external DC
bus. Corrected: each PCS feeder now routes as an independent branch to its own
labelled output terminal (`OUT-1` / `OUT-2`) on the DC Block; the block's
common bus exists only inside the block. Renderer refuses to draw more PCS
connections than the block's `output_circuit_count`. Regression test
`test_pcs_dc_sides_never_share_a_dc_busbar` asserts the two branches share no
conductor point and the old branch-bus ids are gone.

## 3. Rules for all future diagram work (SLD and Layout)

0. **Electrical rules outrank visual rules.** Standing owner decisions
   (e.g. independent PCS DC inputs; two-winding = one common LV bus;
   three-winding = two independent LV buses, no tie) are binding contract:
   encode each as a regression test the first time it is stated.

1. **Every visual requirement must exist as a geometric assertion.** If a
   review says "these two shapes must touch/never overlap", encode it as a
   rendered-output check before or with the drawing change. Text-presence
   assertions are not drawing tests.
2. **Validate what you render, render what you validate.** New drawing code
   must not introduce a second geometry source. If renderer geometry must
   diverge from the layout plan, the rendered-SVG gate — not the plan check —
   owns the quality bar for that element.
3. **Symbols own their geometry.** New symbols define their bounding box and
   connection points in one function and return terminals to the caller;
   call sites never re-derive symbol-internal offsets.
4. **Input-driven semantics.** Any symbol whose shape encodes an input value
   (vector group, polarity, count) must derive the shape from that input, and
   must degrade to text when the input is outside the supported set.
5. **Look at the picture.** Before committing a renderer change, render the
   affected configurations to PNG and inspect them at zoom; automated gates
   catch the encoded invariants only.

## 4. Master Layout (P2) — same defects already present, fix before building on it

`calb_diagrams/layout_block_renderer.py` (41 k) shows the same structure that
caused the SLD failures:

- **Two full parallel implementations** — svgwrite path and `*_raw`
  string-concatenation fallback (`_draw_dc_interior` / `_draw_dc_interior_raw`,
  `_draw_ac_interior` / `_draw_ac_interior_raw`, dimension helpers ×2,
  `_render_layout_block_svg_fallback`). They will drift exactly the way the
  SLD plan/sheet geometries drifted. Consolidate to one implementation (or add
  an equivalence test rendering both and diffing normalized geometry) before
  P2 work extends this file.
- **Only a smoke test** (`tests/test_layout_block_smoke.py`) — no geometric
  assertions (clearance dimensions vs. drawn rectangles, no-overlap between
  containers, dimension-line text matching the metre inputs).
- Recommended before P2: a `validate_rendered_layout_svg` gate mirroring the
  SLD gate (scale consistency: drawn px distance / `_m_to_px` scale must equal
  the labelled metres; container boxes must not overlap; dimension text inside
  the frame), plus per-arrangement preview rendering in tests.

## 5. Verification (2026-07-15)

- `python -m pytest tests -q` → 294 passed.
- Regression baseline `case01` regenerated via
  `scripts/generate_sld_regression_baseline.py` (geometry intentionally
  changed by the fixes above).
- 3-winding and 2-winding previews rendered to PNG and visually inspected.
- `git diff` contains no changes under the frozen sizing core.
