"""The DC page must size each mode once, and persist the run it displayed.

`show()` used to call the pipeline twice for the winning mode: once through
`dc_view.size_with_guarantee` to build the tuple it renders, and again through
`dc_pipeline_service.size_with_guarantee` to build the snapshot it writes to the
DB. Two independent executions of the same inputs — they agreed, but nothing
made them agree, and the page's heaviest computation ran twice.

Now the snapshot is computed once and the displayed tuple is derived from it by
`snapshot_to_legacy_tuple`. This file pins both halves: the tuple still carries
exactly what it used to, and the page really does size once per mode.
"""
from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pandas as pd
import pytest

from calb_sizing_tool.config import DC_DATA_PATH
from calb_sizing_tool.schemas.master_data import DcExcelMasterDataBundle
from calb_sizing_tool.schemas.stage1 import Stage1Result
from calb_sizing_tool.services.dc_pipeline_service import size_with_guarantee as service_sizer
from calb_sizing_tool.services.stage2_service import K_MAX_FIXED
from calb_sizing_tool.ui import dc_view


def _assert_same_stage2(left: dict, right: dict) -> None:
    """Stage 2 carries `block_config_table` as a DataFrame, so `==` is ambiguous."""
    assert set(left) == set(right)
    for key in left:
        if isinstance(left[key], pd.DataFrame):
            pd.testing.assert_frame_equal(left[key], right[key])
        else:
            assert left[key] == right[key], key


def _bundle(defaults: dict) -> DcExcelMasterDataBundle:
    _defaults, df_blocks, df_soh_p, df_soh_c, df_rte_p, df_rte_c = dc_view.load_data(
        Path(DC_DATA_PATH)
    )
    return DcExcelMasterDataBundle(
        workbook_path=Path(DC_DATA_PATH),
        defaults=defaults,
        df_blocks=df_blocks.copy(),
        df_soh_profile=df_soh_p.copy(),
        df_soh_curve=df_soh_c.copy(),
        df_rte_profile=df_rte_p.copy(),
        df_rte_curve=df_rte_c.copy(),
        raw_sheets={},
    )


@pytest.fixture(scope="module")
def stage1() -> dict:
    defaults, *_ = dc_view.load_data(Path(DC_DATA_PATH))
    return dc_view.run_stage1(
        {
            "project_name": "Sizes Once",
            "poi_power_req_mw": 100.0,
            "poi_energy_req_mwh": 400.0,
            "eff_dc_cables": 99.5,
            "eff_pcs": 98.5,
            "eff_mvt": 99.5,
            "eff_ac_cables_sw_rmu": 99.2,
            "eff_hvt_others": 100.0,
            "sc_time_months": 3,
            "sc_loss_frac": dc_view.calc_sc_loss_pct(3) / 100.0,
            "dod_pct": 95.0,
            "dc_round_trip_efficiency_pct": 94.0,
            "rte_curve_adjust_pp": 0.0,
            "rte_monotonic_enforce": True,
            "project_life_years": 20,
            "cycles_per_year": 365,
            "poi_guarantee_year": 10,
        },
        defaults,
    )


def test_the_displayed_tuple_is_the_snapshot_the_db_gets(stage1):
    """One run, two views of it — not two runs."""
    defaults, *_ = dc_view.load_data(Path(DC_DATA_PATH))
    snapshot = service_sizer(
        Stage1Result.model_validate(stage1),
        "container_only",
        _bundle(defaults),
        k_max=K_MAX_FIXED,
    )

    s2, s3_df, s3_meta, iterations, poi_g, converged = dc_view.snapshot_to_legacy_tuple(snapshot)

    _assert_same_stage2(s2, snapshot.stage2.to_legacy_dict())
    assert s3_meta == snapshot.stage3.meta.to_legacy_dict()
    assert iterations == snapshot.iteration_count
    assert poi_g == snapshot.poi_usable_energy_mwh_at_guarantee_year
    assert converged is snapshot.converged
    pd.testing.assert_frame_equal(s3_df, snapshot.stage3.dataframe())


def test_the_tuple_still_matches_the_public_wrapper(stage1):
    """`size_with_guarantee` is called by tests and by report code; its shape is a contract."""
    defaults, df_blocks, df_soh_p, df_soh_c, df_rte_p, df_rte_c = dc_view.load_data(
        Path(DC_DATA_PATH)
    )
    wrapper = dc_view.size_with_guarantee(
        stage1, "container_only", df_blocks, df_soh_p, df_soh_c, df_rte_p, df_rte_c,
        k_max=K_MAX_FIXED,
    )
    direct = dc_view.snapshot_to_legacy_tuple(
        service_sizer(
            Stage1Result.model_validate(stage1),
            "container_only",
            _bundle(defaults),
            k_max=K_MAX_FIXED,
        )
    )

    assert len(wrapper) == 6
    _assert_same_stage2(wrapper[0], direct[0])
    assert wrapper[2] == direct[2]
    assert wrapper[3:] == direct[3:]
    pd.testing.assert_frame_equal(wrapper[1], direct[1])


def test_the_defaults_the_bundle_carries_do_not_change_the_result(stage1):
    """Why reusing the display run for the DB is safe.

    The two old calls built their bundle differently — the display one passed
    `defaults={}`, the persistence one passed the real workbook defaults. They
    agreed because the guaranteed-sizing path never reads `bundle.defaults`
    (only `run_dc_pipeline` does, for Stage 1, which is already computed here).
    If that ever stops being true, this test says so.
    """
    defaults, *_ = dc_view.load_data(Path(DC_DATA_PATH))
    with_defaults = service_sizer(
        Stage1Result.model_validate(stage1), "container_only", _bundle(defaults), k_max=K_MAX_FIXED
    )
    without = service_sizer(
        Stage1Result.model_validate(stage1), "container_only", _bundle({}), k_max=K_MAX_FIXED
    )
    _assert_same_stage2(with_defaults.stage2.to_legacy_dict(), without.stage2.to_legacy_dict())
    assert with_defaults.summary == without.summary


def test_show_calls_the_sizer_once_per_mode():
    """A second pipeline call in show() is the defect this replaced."""
    tree = ast.parse(inspect.getsource(dc_view.show))
    sizer_calls = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in ("service_size_with_guarantee", "size_with_guarantee")
    ]
    assert len(sizer_calls) == 1, (
        f"show() calls the DC sizing pipeline {len(sizer_calls)} times; it must size "
        f"each mode once and reuse the snapshot for persistence"
    )
