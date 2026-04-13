# SLD Regression Baseline V1

## Why A Baseline Is Required

SLD regressions are often structural, not visual at first glance. A diagram can still look acceptable while the engineering relationship is already wrong.

Typical hidden regressions include:

- wrong feeder allocation
- wrong PCS count
- wrong DC blocks per feeder
- draft fallback entering a formal render path

Because of that, screenshot-only review is not enough.

## Baselines Used In Phase 3

### Topology baseline

File:

- `tests/fixtures/sld_cases/case01_container_only_group1/topology_baseline.json`

Checks:

- normalized topology payload
- validation mode
- source trace
- feeder count
- PCS count
- `dc_blocks_per_feeder`

### Render baseline

File:

- `tests/fixtures/sld_cases/case01_container_only_group1/render_baseline.json`

Checks:

- normalized render metadata
- normalized render spec payload
- key text nodes
- geometry counts
- selected mode
- topology hash
- renderer input hash
- render spec hash

## How The Baseline Is Generated

Generation flow:

1. load `case_definition.json`
2. build `DcRunBundle + AcSnapshot + project_settings + render options`
3. run `prepare_sld_pipeline_from_run_bundle(...)`
4. normalize topology or render output
5. compare against committed baseline JSON

## When Baseline Updates Are Allowed

Baseline updates are allowed only when the engineering contract or intentional renderer behavior has changed in a reviewed way.

Examples:

- authoritative field contract changed
- topology rules intentionally changed
- renderer geometry intentionally changed

Baseline updates are not allowed when the change is caused by:

- silent fallback
- accidental compatibility drift
- guessed values entering strict mode

## Minimum Test Set

Phase 3 regression coverage is anchored by:

- `tests/unit/test_sld_ac_field_contract.py`
- `tests/unit/test_sld_authoritative_builder.py`
- `tests/integration/test_sld_topology_regression.py`
- `tests/integration/test_sld_render_regression.py`

These tests are the minimum guardrail for keeping the SLD engine stable after the authoritative-path cleanup.
