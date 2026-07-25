# Change Discipline V1 — how every fix/optimization must be done

Date: 2026-07-25
Status: **Active rule.** Applies to every bug fix, optimization and feature on
this project. Purpose: stop scope drift ("发疯走偏") and keep the system one clean
flow instead of a pile of parallel bolt-ons.

Read this before starting any change. The paired automated checks are in
`tests/test_frozen_canon_guard.py` and the report-leak guard in
`tests/unit/test_report_governed_mixed_consistency.py`.

---

## 1. The five rules

**R1 — One flow, no parallel systems.** There is ONE AC Sizing engine (auto-
recommend ratio + PCS, duration-aware, then power/energy validation → pass/hold)
and ONE DC Sizing engine. New capability is a **layer on the existing flow**
(an optional step that consumes its output), never a second primary path that
duplicates it. If a change needs a "mode toggle" between two sizing engines,
stop — that is the drift signal.

**R2 — Frozen canon is untouchable.** The modules in `SIZING_LOGIC_CANON_V1`
(Stage 1/2/3, `dc_pipeline_service`, `ac_sizing_service`, `common/ac_block`,
`common/allocation`) never change. Consumers read/validate/present their output;
they never re-implement a formula, relax a threshold or re-group blocks.
Enforced by `test_frozen_canon_guard.py` (SHA-256 pins).

**R3 — Never fabricate an engineering value.** An unconfirmed value (transformer
MVA, vector group, Uk%, footprint, product nameplate) stays an explicit `TBD`
with its confirmation source. No `MW ÷ PF` promoted to a nameplate; no auto-bound
product presented as owner-confirmed.

**R4 — The report is a customer document.** No internal code identifiers, module
names, pipeline stage-names or developer jargon ("governed", "Phase B",
"reconciliation code", `layout_variant` raw codes, `MW ÷ PF` justifications) in
the exported report. Enforced by the report-leak guard test.

**R5 — Confirm before architecture; act within scope.** A bug fix or a small
optimization: do it, test it, done. A change that adds a new subsystem, a new
primary path, a new gate, or reverses a prior decision: **state the plan and get
owner confirmation first.** Do only what the request needs — no speculative
scope.

---

## 2. The verification mechanism (run on every change)

A change is not done until ALL of these pass:

1. `python -m pytest tests/ -q` — full suite green (target-relevant tests + the
   two guard tests above must pass).
2. **Frozen check** — `test_frozen_canon_guard.py` green (no canon module edited).
   Equivalent manual check: `git diff <frozen-baseline> -- <canon files>` empty.
3. **Report-leak check** — the customer-report guard test green (no internal
   tokens in the exported DOCX).
4. **Scope check** — the diff touches only the layers the request needs; no new
   parallel sizing path introduced (R1); no fabricated values (R3).

If any fails, fix or revert before committing. A green suite that skips these
guards is not sufficient.

---

## 3. The drift signals (stop and re-read this doc)

- You are adding a second "mode" / "method" toggle between two sizing engines.
- You are freezing a specific product into a fixed "family" that then needs a
  gate to keep other inputs out.
- You are labelling the existing primary flow as "legacy" to promote a new one.
- You are recomputing in the report/SLD/layout what the sizing run already
  produced (consume the persisted run instead).
- You are about to write an internal term into a customer-facing string.

Any of these means: stop, simplify back to one flow + optional layers, and
confirm with the owner.

---

## 4. Deliberate canon change (rare, owner-approved only)

The frozen canon changes only when the owner explicitly re-approves it. In that
one commit: change the module, update its pinned SHA-256 in
`test_frozen_canon_guard.py`, bump `SIZING_LOGIC_CANON_V1`, and note the approval
here. Never edit a pinned hash merely to make the guard pass.
