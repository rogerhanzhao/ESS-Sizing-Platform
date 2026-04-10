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

"""Simulation utilities for simple DC/AC dispatch profiles.

The `simulate_dispatch` function provides a lightweight, deterministic
time-eries simulation that can be shared across notebooks, scripts, or
Streamlit pages. The goal is not to capture every electrical nuance but to
offer a stable, validated utility that guards against invalid inputs and
returns a pandas ``DataFrame`` suitable for downstream plotting or export.
"""

from __future__ import annotations

import math
import numbers
from typing import Iterable, Mapping

import pandas as pd


class DispatchValidationError(ValueError):
    """Raised when dispatch parameters cannot be validated."""


def _require_mapping(name: str, value: object) -> Mapping[str, float]:
    if not isinstance(value, Mapping):
        raise DispatchValidationError(f"{name} must be a mapping of string keys to numeric values.")
    return value


def _require_positive(name: str, value: object, *, allow_zero: bool = False) -> float:
    try:
        numeric_value = float(value)
    except Exception as exc:  # pragma: no cover - defensive casting
        raise DispatchValidationError(f"{name} must be a numeric value.") from exc

    if allow_zero and numeric_value == 0:
        return numeric_value

    if numeric_value <= 0:
        raise DispatchValidationError(f"{name} must be greater than 0.")
    return numeric_value


def _require_fraction(name: str, value: object) -> float:
    numeric_value = _require_positive(name, value, allow_zero=True)
    if numeric_value < 0 or numeric_value > 1:
        raise DispatchValidationError(f"{name} must be between 0 and 1 inclusive.")
    return numeric_value


def _require_positive_fraction(name: str, value: object) -> float:
    numeric_value = _require_fraction(name, value)
    if numeric_value == 0:
        raise DispatchValidationError(f"{name} must be greater than 0.")
    return numeric_value


def _require_profile(profile: object, *, expected_steps: int | None) -> Iterable[float]:
    if isinstance(profile, (str, bytes)):
        raise DispatchValidationError("profile must be an iterable of numeric values, not a string.")
    if not isinstance(profile, Iterable):
        raise DispatchValidationError("profile must be an iterable of numeric values.")

    profile_list = list(profile)
    if not profile_list:
        raise DispatchValidationError("profile must contain at least one timestep.")

    if expected_steps is not None and len(profile_list) != expected_steps:
        raise DispatchValidationError(
            f"profile length {len(profile_list)} does not match expected_steps {expected_steps}."
        )

    for idx, value in enumerate(profile_list):
        if not isinstance(value, numbers.Real) or isinstance(value, bool):
            raise DispatchValidationError(f"profile entry at index {idx} is not a numeric value.")

    return profile_list


def simulate_dispatch(dc_dict, ac_dict, profile, params):
    """Simulate a deterministic dispatch profile with simple AC/DC limits.

    Args:
        dc_dict: Mapping describing the DC block. Required keys:
            - ``capacity_mwh`` (float): Usable energy capacity.
            - ``max_charge_mw`` (float): Charge power limit on the DC side.
            - ``max_discharge_mw`` (float): Discharge power limit on the DC side.
            - ``initial_soc`` (float): Initial state of charge (0-?).
        ac_dict: Mapping describing AC constraints. Required keys:
            - ``ac_power_limit_mw`` (float): Maximum AC import/export power.
        profile: Iterable of numeric power requests in MW. Positive values
            discharge to the grid; negative values represent charging from the grid.
        params: Mapping of simulation parameters. Required keys:
            - ``timestep_hours`` (float): Duration of each profile step in hours.
          Optional keys:
            - ``roundtrip_efficiency`` (float): >0-?, defaults to 1.0.
            - ``charge_efficiency`` / ``discharge_efficiency`` (float):
              Overrides derived efficiencies if provided. Each efficiency must
              be greater than 0 and no more than 1.
            - ``expected_steps`` (int): If provided, the profile length must match.

    Returns:
        pandas.DataFrame with per-tep fields: ``step``, ``requested_mw``,
        ``delivered_mw``, ``unserved_mw``, ``state_of_charge_mwh``, and
        ``state_of_charge_frac``.

    Raises:
        DispatchValidationError: If any input fails validation.
    """

    dc_dict = _require_mapping("dc_dict", dc_dict)
    ac_dict = _require_mapping("ac_dict", ac_dict)
    params = _require_mapping("params", params)

    capacity_mwh = _require_positive("dc_dict['capacity_mwh']", dc_dict.get("capacity_mwh"))
    max_charge_mw = _require_positive("dc_dict['max_charge_mw']", dc_dict.get("max_charge_mw"))
    max_discharge_mw = _require_positive("dc_dict['max_discharge_mw']", dc_dict.get("max_discharge_mw"))
    initial_soc = _require_fraction("dc_dict['initial_soc']", dc_dict.get("initial_soc"))

    ac_power_limit_mw = _require_positive("ac_dict['ac_power_limit_mw']", ac_dict.get("ac_power_limit_mw"))

    timestep_hours = _require_positive("params['timestep_hours']", params.get("timestep_hours"))
    expected_steps = params.get("expected_steps")
    if expected_steps is not None:
        try:
            expected_steps = int(expected_steps)
        except Exception as exc:  # pragma: no cover - defensive casting
            raise DispatchValidationError("params['expected_steps'] must be an integer if provided.") from exc
        if expected_steps <= 0:
            raise DispatchValidationError("params['expected_steps'] must be greater than 0 when provided.")

    profile = _require_profile(profile, expected_steps=expected_steps)

    roundtrip_efficiency = params.get("roundtrip_efficiency", 1.0)
    rte = _require_positive_fraction("params['roundtrip_efficiency']", roundtrip_efficiency)
    charge_eff = params.get("charge_efficiency", math.sqrt(rte))
    discharge_eff = params.get("discharge_efficiency", math.sqrt(rte))

    charge_eff = _require_positive_fraction("charge_efficiency", charge_eff)
    discharge_eff = _require_positive_fraction("discharge_efficiency", discharge_eff)

    energy_mwh = capacity_mwh * initial_soc

    rows = []
    for step, requested_mw in enumerate(profile):
        requested_mw = float(requested_mw)

        if requested_mw >= 0:
            # Discharge to grid
            max_power = min(requested_mw, ac_power_limit_mw, max_discharge_mw)
            max_energy_limited = energy_mwh / timestep_hours * discharge_eff
            delivered_mw = min(max_power, max_energy_limited)
            energy_mwh = max(0.0, energy_mwh - (delivered_mw * timestep_hours) / discharge_eff)
        else:
            # Charge from grid
            target_mw = abs(requested_mw)
            max_power = min(target_mw, ac_power_limit_mw, max_charge_mw)
            headroom_mwh = max(0.0, capacity_mwh - energy_mwh)
            max_energy_limited = headroom_mwh / (timestep_hours * charge_eff) if headroom_mwh else 0.0
            delivered_positive_mw = min(max_power, max_energy_limited)
            delivered_mw = -delivered_positive_mw
            energy_mwh = min(
                capacity_mwh,
                energy_mwh + (delivered_positive_mw * timestep_hours) * charge_eff,
            )

        unserved_mw = abs(requested_mw - delivered_mw)
        soc_frac = energy_mwh / capacity_mwh if capacity_mwh else 0.0

        rows.append(
            {
                "step": step,
                "requested_mw": requested_mw,
                "delivered_mw": delivered_mw,
                "unserved_mw": unserved_mw,
                "state_of_charge_mwh": energy_mwh,
                "state_of_charge_frac": soc_frac,
            }
        )

    return pd.DataFrame(rows)


