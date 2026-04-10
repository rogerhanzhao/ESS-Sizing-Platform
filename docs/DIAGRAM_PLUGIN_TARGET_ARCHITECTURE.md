# Diagram and Layout Plugin Target Architecture

Date: 2026-04-10
Scope: Target architecture only (no implementation in this phase)

## SLD Plugin Contract (Target)
- Inputs:
  - run_id
  - run snapshot bundle (DC/AC/Stage outputs)
  - rendering options (template, voltage level, labeling)
- Outputs:
  - artifact files: SVG, PNG, PDF
  - artifact metadata: checksum, dimensions, version, renderer_id
  - summary metrics for report export
- Validation:
  - schema validation on inputs
  - unit/format validation on outputs

## Layout Plugin Contract (Target)
- Inputs:
  - run_id
  - run snapshot bundle
  - site constraints (land shape, setback, aisle width)
  - layout strategy parameters (orientation, packing rule)
- Outputs:
  - layout spec JSON (canonical)
  - render artifacts: SVG, PNG
  - placement summary (counts, clearances, footprint)
- Validation:
  - geometry validity
  - clearance constraints
  - count parity with run snapshot

## External AI Layout Plugin Contract (Target)
- Inputs:
  - run snapshot bundle
  - prompt parameters
  - optional constraints (geometry, cost bias)
- Outputs:
  - layout spec JSON
  - rationale/trace notes
  - artifact renderables (optional)
- Governance:
  - AI output must pass deterministic validators
  - human review required before publish

## Artifact Registry and Review Workflow
- All plugin outputs are stored in `artifact_registry` tied to `run_id`.
- Validators run before artifacts are marked as `published`.
- Review workflow:
  - draft -> validated -> reviewed -> published
- Report export reads from published artifacts only.

## Versioning Strategy
- Each plugin artifact is versioned with:
  - plugin_id
  - plugin_version
  - run_snapshot_hash
  - created_at
