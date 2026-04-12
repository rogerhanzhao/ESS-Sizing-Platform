# SLD Regression Strategy V1

## Goal

Freeze SLD behavior at two levels:

- topology baseline
- render baseline

This avoids future regressions where the diagram still renders but the engineering structure or visual structure has drifted.

## Baseline Types

### Topology Baseline

Stored as:

- normalized topology JSON

What it covers:

- node count
- edge count
- feeder relationships
- PCS / DC block allocation
- semantic node / edge / equipment structure

### Render Baseline

Stored as:

- normalized render JSON

Current normalized render payload includes:

- renderer metadata
- normalized spec payload
- normalized SVG structure
  - viewBox / width / height
  - element counts
  - class counts
  - text nodes
  - normalized geometry signature

This is intentionally stronger than screenshot-only checks.

## Baseline Source

Baseline cases live under:

- `tests/fixtures/sld_cases/`

Current case:

- `tests/fixtures/sld_cases/case01_container_only_group1/`

Artifacts:

- `case_definition.json`
- `topology_baseline.json`
- `render_baseline.json`

## How Baselines Are Generated

Use:

```powershell
python scripts/generate_sld_regression_baseline.py --case-dir tests/fixtures/sld_cases/case01_container_only_group1
```

The generator:

1. loads the frozen case definition
2. rebuilds the DC run bundle from sample Excel
3. prepares the SLD pipeline
4. writes normalized topology baseline
5. writes normalized render baseline

## Test Strategy

### Topology Regression

`tests/integration/test_sld_topology_regression.py`

Verifies:

- same case => same topology on repeated runs
- generated topology == stored baseline

### Render Regression

`tests/integration/test_sld_render_regression.py`

Verifies:

- same topology => same normalized render output on repeated runs
- generated render payload == stored baseline

### UI Pipeline Regression

`tests/integration/test_sld_ui_pipeline.py`

Verifies:

- UI delegates to the pipeline service
- UI no longer owns canonical/topology/spec logic

## Update Rule

Do not regenerate baselines casually.

Only update a baseline when:

- the topology contract changed intentionally
- the layout/symbol output changed intentionally
- the change was reviewed and approved

If a baseline must change, regenerate it with the script and explain why in the PR or change log.
