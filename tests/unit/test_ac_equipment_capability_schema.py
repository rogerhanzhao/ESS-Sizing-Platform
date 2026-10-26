"""Capability declarations are strict, incomplete evidence rather than approval."""

from __future__ import annotations

from copy import deepcopy
import json

import pytest
from pydantic import ValidationError

from calb_sizing_tool.schemas.ac_equipment_capability import (
    CapabilityConditions,
    DischargeDutyBasis,
    EquipmentCapabilityPackage,
    capability_package_sha256,
)


def _pcs_package() -> dict:
    return {
        "package_code": "SYNTHETIC-PCS",
        "revision": "R1",
        "kind": "pcs",
        "model": "SYNTHETIC PCS",
        "manufacturer": "SYNTHETIC ONLY",
        "source_ref": "SYNTHETIC / no manufacturer approval",
        "conditions": {"temperature_min_c": -20, "temperature_max_c": 40, "frequency_hz": 50},
        "pcs": {
            "dc_voltage_min_v": 1000,
            "dc_voltage_max_v": 1500,
            "continuous_dc_current_a": 1500,
            "dc_discharge_power_kw": 1500,
            "ac_discharge_power_kw": 1400,
            "ac_apparent_power_kva": 1500,
            "ac_voltage_v": 690,
            "ports": [{
                "port_id": "P1",
                "dc_bus_group": "BUS1",
                "voltage_min_v": 1000,
                "voltage_max_v": 1500,
                "continuous_current_a": 1500,
                "discharge_power_kw": 1500,
            }],
            "dc_buses": [{"dc_bus_group": "BUS1"}],
        },
    }


def _transformer_package() -> dict:
    package = _pcs_package()
    del package["pcs"]
    package.update({
        "package_code": "SYNTHETIC-TX",
        "kind": "transformer",
        "transformer": {
            "total_kva": 3000,
            "hv_voltage_kv": 22,
            "vector_group": "Dyn11",
            "windings": [
                {"winding_id": "LV1", "voltage_v": 690, "continuous_kva": 1800},
                {"winding_id": "LV2", "voltage_v": 690},
            ],
        },
    })
    return package


def test_pcs_active_and_apparent_ratings_cannot_contradict_same_conditions():
    package = _pcs_package()
    package['pcs']['ac_apparent_power_kva'] = 1300
    with pytest.raises(ValidationError, match='active power cannot exceed apparent power'):
        EquipmentCapabilityPackage.model_validate(package)


def test_unknown_values_stay_unknown_without_inferred_winding_capacity_or_duty():
    package = EquipmentCapabilityPackage.model_validate(_transformer_package())
    assert package.transformer.windings[1].continuous_kva is None
    duty = DischargeDutyBasis.model_validate({})
    assert duty.power_factor_abs is None
    assert duty.ambient_temperature_c is None
    assert duty.mv_bus_voltage_kv is None
    assert duty.passive_dc_path_confirmed is False
    assert package.model_dump(mode="json")["pcs"] is None


def test_explicit_shared_bus_is_retained_without_inventing_parallel_permission():
    data = _pcs_package()
    data["pcs"]["ports"].append({"port_id": "P2", "dc_bus_group": "BUS1"})
    package = EquipmentCapabilityPackage.model_validate(data)
    assert len(package.pcs.ports) == 2
    bus = package.pcs.dc_buses[0]
    assert bus.max_parallel_domains is None
    assert bus.compatible_revision_sha256 == []
    assert bus.compatible_output_partition_sha256 == []
    assert bus.parallel_evidence_ref is None
    assert package.pcs.aggregate_current_basis is None


@pytest.mark.parametrize("value", [True, False, "1", 1.0, 2, None])
def test_schema_version_requires_the_integer_one(value):
    data = _pcs_package()
    data["schema_version"] = value
    with pytest.raises(ValidationError):
        EquipmentCapabilityPackage.model_validate(data)


@pytest.mark.parametrize("value", [True, False, "1500", 0, -1, float("nan"), float("inf"), -float("inf"), 10 ** 400])
@pytest.mark.parametrize("path", ["pcs", "port", "transformer", "winding"])
def test_ratings_require_positive_finite_actual_numbers(path, value):
    data = _transformer_package() if path in {"transformer", "winding"} else _pcs_package()
    target, field = {
        "pcs": (data.get("pcs"), "dc_discharge_power_kw"),
        "port": ((data.get("pcs") or {"ports": [None]})["ports"][0], "continuous_current_a"),
        "transformer": (data.get("transformer"), "total_kva"),
        "winding": ((data.get("transformer") or {"windings": [None]})["windings"][0], "continuous_kva"),
    }[path]
    target[field] = value
    with pytest.raises(ValidationError):
        EquipmentCapabilityPackage.model_validate(data)


def test_huge_integer_json_produces_validation_error_instead_of_overflow():
    data = _pcs_package()
    data["pcs"]["ports"][0]["continuous_current_a"] = 10 ** 400
    with pytest.raises(ValidationError):
        EquipmentCapabilityPackage.model_validate_json(json.dumps(data))
    data = _pcs_package()
    data["pcs"]["dc_buses"][0]["max_parallel_domains"] = 10 ** 400
    with pytest.raises(ValidationError):
        EquipmentCapabilityPackage.model_validate_json(json.dumps(data))


@pytest.mark.parametrize("field", ["temperature_min_c", "temperature_max_c"])
@pytest.mark.parametrize("value", [True, "-10", float("nan"), float("inf"), 10 ** 400])
def test_temperature_is_finite_and_strict_while_negative_temperatures_are_valid(field, value):
    with pytest.raises(ValidationError):
        CapabilityConditions.model_validate({field: value})
    assert CapabilityConditions(temperature_min_c=-30).temperature_min_c == -30


def test_ranges_reject_inverted_temperature_and_non_open_voltage_windows():
    with pytest.raises(ValidationError):
        CapabilityConditions(temperature_min_c=40, temperature_max_c=30)
    assert CapabilityConditions(temperature_min_c=40, temperature_max_c=40)
    for scope in ("pcs", "port"):
        for upper in (999, 1000):
            data = _pcs_package()
            if scope == "pcs":
                data["pcs"]["dc_voltage_max_v"] = upper
            else:
                data["pcs"]["ports"][0]["voltage_max_v"] = upper
            with pytest.raises(ValidationError):
                EquipmentCapabilityPackage.model_validate(data)
    partial = _pcs_package()
    partial["pcs"]["dc_voltage_min_v"] = None
    partial["pcs"]["ports"][0]["voltage_max_v"] = None
    assert EquipmentCapabilityPackage.model_validate(partial)


@pytest.mark.parametrize("field", ["package_code", "revision", "model", "manufacturer", "source_ref"])
@pytest.mark.parametrize("value", ["", "  \n", 123, True])
def test_identity_and_evidence_text_cannot_be_blank_or_coerced(field, value):
    data = _pcs_package()
    data[field] = value
    with pytest.raises(ValidationError):
        EquipmentCapabilityPackage.model_validate(data)


@pytest.mark.parametrize("field,maximum", [("package_code", 128), ("revision", 64), ("source_ref", 2000)])
def test_identity_and_evidence_have_bounded_text(field, maximum):
    data = _pcs_package()
    data[field] = "a" * (maximum + 1)
    with pytest.raises(ValidationError):
        EquipmentCapabilityPackage.model_validate(data)


@pytest.mark.parametrize("location", ["package", "conditions", "pcs", "port", "bus", "transformer", "winding"])
def test_unknown_fields_never_silently_create_a_capability(location):
    data = _transformer_package() if location in {"transformer", "winding"} else _pcs_package()
    target = {
        "package": data,
        "conditions": data["conditions"],
        "pcs": data.get("pcs"),
        "port": (data.get("pcs") or {"ports": [None]})["ports"][0],
        "bus": (data.get("pcs") or {"dc_buses": [None]})["dc_buses"][0],
        "transformer": data.get("transformer"),
        "winding": (data.get("transformer") or {"windings": [None]})["windings"][0],
    }[location]
    target["approved"] = True
    with pytest.raises(ValidationError):
        EquipmentCapabilityPackage.model_validate(data)


@pytest.mark.parametrize("mutation", ["missing_pcs", "wrong_kind", "both"])
def test_equipment_kind_binds_exactly_one_matching_object(mutation):
    data = _pcs_package()
    if mutation == "missing_pcs":
        del data["pcs"]
    elif mutation == "wrong_kind":
        data["kind"] = "transformer"
    else:
        data["transformer"] = _transformer_package()["transformer"]
    with pytest.raises(ValidationError):
        EquipmentCapabilityPackage.model_validate(data)


@pytest.mark.parametrize("mutation", ["duplicate_port", "duplicate_bus", "unknown_bus", "unused_bus", "empty_ports", "empty_buses"])
def test_port_and_bus_identity_coverage_is_explicit(mutation):
    data = _pcs_package()
    pcs = data["pcs"]
    if mutation == "duplicate_port":
        pcs["ports"].append(deepcopy(pcs["ports"][0]))
    elif mutation == "duplicate_bus":
        pcs["dc_buses"].append(deepcopy(pcs["dc_buses"][0]))
    elif mutation == "unknown_bus":
        pcs["ports"][0]["dc_bus_group"] = "missing"
    elif mutation == "unused_bus":
        pcs["dc_buses"].append({"dc_bus_group": "unused"})
    elif mutation == "empty_ports":
        pcs["ports"] = []
    else:
        pcs["dc_buses"] = []
    with pytest.raises(ValidationError):
        EquipmentCapabilityPackage.model_validate(data)


@pytest.mark.parametrize("windings", [[], [{"winding_id": "LV1"}, {"winding_id": "LV1"}]])
def test_transformer_windings_are_nonempty_and_unique(windings):
    data = _transformer_package()
    data["transformer"]["windings"] = windings
    with pytest.raises(ValidationError):
        EquipmentCapabilityPackage.model_validate(data)


@pytest.mark.parametrize("value", [True, False, 1.0, "1", 0, -1])
def test_max_parallel_domains_is_a_positive_strict_integer(value):
    data = _pcs_package()
    data["pcs"]["dc_buses"][0]["max_parallel_domains"] = value
    with pytest.raises(ValidationError):
        EquipmentCapabilityPackage.model_validate(data)


@pytest.mark.parametrize("field", ["compatible_revision_sha256", "compatible_output_partition_sha256"])
@pytest.mark.parametrize("value", [["A" * 64], ["a" * 63], ["g" * 64], ["a" * 64, "a" * 64]])
def test_parallel_compatibility_hashes_are_unique_lowercase_sha256(field, value):
    data = _pcs_package()
    data["pcs"]["dc_buses"][0][field] = value
    with pytest.raises(ValidationError):
        EquipmentCapabilityPackage.model_validate(data)


@pytest.mark.parametrize("value", [0, -0.1, 1.01, True, "0.95", float("nan"), float("inf"), 10 ** 400])
def test_duty_power_factor_is_explicit_finite_and_bounded(value):
    with pytest.raises(ValidationError):
        DischargeDutyBasis(power_factor_abs=value)
    assert DischargeDutyBasis(power_factor_abs=0.95).power_factor_abs == 0.95


@pytest.mark.parametrize("value", [1, 0, "true", None])
def test_passive_dc_path_is_an_explicit_boolean(value):
    with pytest.raises(ValidationError):
        DischargeDutyBasis(passive_dc_path_confirmed=value)


def test_capability_hash_uses_validated_typed_values_and_survives_json_roundtrip():
    raw = _pcs_package()
    typed = EquipmentCapabilityPackage.model_validate(raw)
    restored = EquipmentCapabilityPackage.model_validate_json(typed.model_dump_json())
    digest = capability_package_sha256(raw)
    assert digest == capability_package_sha256(typed) == capability_package_sha256(restored)
    reordered = dict(reversed(list(raw.items())))
    reordered["pcs"]["dc_discharge_power_kw"] = 1500.0
    assert capability_package_sha256(reordered) == digest
    changed = deepcopy(raw)
    changed["pcs"]["dc_discharge_power_kw"] = 1400
    assert capability_package_sha256(changed) != digest


def test_hash_revalidates_mutated_models_instead_of_signing_invalid_data():
    package = EquipmentCapabilityPackage.model_validate(_pcs_package())
    package.pcs.ports[0].continuous_current_a = float("nan")
    with pytest.raises(ValidationError):
        capability_package_sha256(package)
