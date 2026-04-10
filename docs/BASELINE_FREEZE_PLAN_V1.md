# Baseline Freeze Plan V1

## Objective

Freeze the current DC Stage 1 to Stage 3 sizing behavior on branch `ops/ubuntu-docker-coexist-20260311` before deeper refactor work. This baseline is the regression reference for all follow-on service, repository, and database changes.

## Frozen Scope

- Stage 1 input normalization, efficiency chain, storage charging loss, DoD, and DC RTE adjustment logic.
- Stage 2 scenario selection logic for `container_only`, `cabinet_only`, and `hybrid`.
- Stage 3 SOH profile selection, RTE profile selection, yearly energy curve expansion, and guarantee-year check.
- Iterative oversizing loop in `dc_pipeline_service.size_with_guarantee`.
- Legacy UI compatibility entry points in [dc_view.py](d:/CALB_SizingTool/calb_sizing_tool/ui/dc_view.py).

## Baseline Assets

Golden cases are stored under `tests/fixtures/golden_cases/<fixture_id>/` with the following artifacts per case:

- `case_input.json`
- `stage1_expected.json`
- `stage2_expected.json`
- `stage3_expected.csv`
- `summary_expected.json`

Generation command:

```bash
python scripts/generate_phase1_golden_cases.py
```

Regression command:

```bash
pytest tests/integration/test_dc_pipeline_regression.py -q
```

## Coverage Matrix

| Fixture | Scenario | Power / Energy | Duration | Guarantee Year | SC Months | DOD / RTE Variant | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `case01_standard_4h_container_y0` | `container_only` | 100 MW / 400 MWh | 4h | 0 | default | default | Standard 4h container baseline |
| `case02_standard_4h_hybrid_y0` | `hybrid` | 100 MW / 400 MWh | 4h | 0 | default | default | Hybrid baseline |
| `case03_standard_4h_cabinet_y0` | `cabinet_only` | 100 MW / 400 MWh | 4h | 0 | default | default | Cabinet baseline |
| `case04_two_hour_container_y0` | `container_only` | 100 MW / 200 MWh | 2h | 0 | default | default | 2h scenario |
| `case05_one_hour_hybrid_y0` | `hybrid` | 100 MW / 100 MWh | 1h | 0 | default | default | 1h scenario |
| `case06_standard_4h_container_y5` | `container_only` | 100 MW / 400 MWh | 4h | 5 | default | default | Mid-life guarantee |
| `case07_standard_4h_container_y10` | `container_only` | 100 MW / 400 MWh | 4h | 10 | default | default | Late guarantee-year oversize |
| `case08_hybrid_sc3` | `hybrid` | 100 MW / 400 MWh | 4h | 5 | 3 | default | S&C 3 months |
| `case09_hybrid_sc12` | `hybrid` | 100 MW / 400 MWh | 4h | 5 | 12 | default | S&C 12 months |
| `case10_container_dod90_rte_adj` | `container_only` | 100 MW / 400 MWh | 4h | 5 | default | `dod=90%`, `dc_rte=93%`, `rte_adjust=+1.5pp` | DOD / RTE sensitivity |

## Output Contract Frozen By Baseline

The following fields are treated as regression-critical and must not change silently:

- `eff_chain`
- `dc_power_required_mw`
- `dc_energy_capacity_required_mwh`
- `effective_c_rate`
- `soh_profile_id`
- `rte_profile_id`
- `guarantee_year_poi_usable_mwh`
- `margin_mwh`
- `iterations`
- `container_count`
- `cabinet_count`
- `dc_nameplate_bol_mwh`
- Stage 3 yearly table columns and row order

These fields are persisted in `summary_expected.json`, `stage1_expected.json`, `stage2_expected.json`, and `stage3_expected.csv`.

## Acceptance And Current Status

Acceptance criteria for Phase 0:

- Same case reruns 3 times with bitwise-stable rounded outputs.
- All golden case files are materialized on disk.
- Regression fixture is available in pytest.
- Service-layer refactor uses the same frozen outputs as baseline.

Current status on 2026-04-10:

- `10` golden cases generated successfully.
- Determinism is verified in [test_dc_pipeline_regression.py](d:/CALB_SizingTool/tests/integration/test_dc_pipeline_regression.py).
- `pytest tests/unit tests/integration -q` passes.
- `alembic upgrade head`, `alembic downgrade base`, and `alembic upgrade head` pass on SQLite.
