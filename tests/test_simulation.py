# -----------------------------------------------------------------------------
# Personal Open-Source Notice
#
# Copyright (c) 2026 Alex.Zhao. All rights reserved.
#
# This repository is released under the MIT License (see LICENSE file).
# Intended use: learning, evaluation, and engineering reference for Utility-scale
# BESS/ESS sizing and Reporting workflows.
#
# DISCLAIMER: This software is provided "AS IS", without warranty of any kind,
# express or implied. In no event shall the author(s) be liable for any claim,
# damages, or other liability arising from, out of, or in connection with the
# software or the use or other dealings in the software.
#
# NOTE: This is a personal project. It is not an official product or statement
# of any company or organization.
# -----------------------------------------------------------------------------

import pandas as pd
import pytest

from calb_sizing_tool.sizing.simulation import DispatchValidationError, simulate_dispatch


def test_simulate_dispatch_nominal_profile():
    dc_dict = {
        "capacity_mwh": 4.0,
        "max_charge_mw": 2.0,
        "max_discharge_mw": 2.0,
        "initial_soc": 0.5,
    }
    ac_dict = {"ac_power_limit_mw": 1.5}
    params = {
        "timestep_hours": 1.0,
        "roundtrip_efficiency": 0.96,
        "expected_steps": 4,
    }
    profile = [1.5, 1.5, -1.5, -1.5]

    df = simulate_dispatch(dc_dict, ac_dict, profile, params)

    assert isinstance(df, pd.DataFrame)
    assert list(df.columns) == [
        "step",
        "requested_mw",
        "delivered_mw",
        "unserved_mw",
        "state_of_charge_mwh",
        "state_of_charge_frac",
    ]
    assert len(df) == 4

    delivered = df["delivered_mw"].tolist()
    # Discharge limited by AC power then energy, followed by two charge steps.
    assert delivered == pytest.approx([1.5, 0.4598, -1.5, -1.5], rel=1e-3, abs=1e-4)

    soc = df["state_of_charge_mwh"].tolist()
    assert soc == pytest.approx([0.4695, 0.0, 1.4697, 2.9394], rel=1e-3, abs=1e-4)

    # No unserved power when requests are within physical limits
    assert df["unserved_mw"].max() < 1.5


@pytest.mark.parametrize(
    "bad_dc_dict",
    [
        "not a dict",
        {"capacity_mwh": -1, "max_charge_mw": 1, "max_discharge_mw": 1, "initial_soc": 0.5},
        {"capacity_mwh": 1, "max_charge_mw": 1, "max_discharge_mw": 1},
    ],
)
def test_simulate_dispatch_invalid_params_raise(bad_dc_dict):
    ac_dict = {"ac_power_limit_mw": 1.0}
    params = {"timestep_hours": 1.0}
    profile = [0.1, 0.1]

    with pytest.raises(DispatchValidationError):
        simulate_dispatch(bad_dc_dict, ac_dict, profile, params)


def test_simulate_dispatch_profile_length_mismatch():
    dc_dict = {
        "capacity_mwh": 1.0,
        "max_charge_mw": 1.0,
        "max_discharge_mw": 1.0,
        "initial_soc": 0.5,
    }
    ac_dict = {"ac_power_limit_mw": 1.0}
    params = {"timestep_hours": 1.0, "expected_steps": 3}
    profile = [0.5, 0.5]  # shorter than expected_steps

    with pytest.raises(DispatchValidationError):
        simulate_dispatch(dc_dict, ac_dict, profile, params)

