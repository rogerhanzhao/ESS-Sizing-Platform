"""Independent D1b edge-case regressions using synthetic equipment only."""

import pytest

from calb_sizing_tool.services import dc_ac_equipment_assessment_service as service
from tests.dc_ac_equipment_fixture import (
    make_equipment_fixture,
    replace_equipment_package,
)


@pytest.fixture
def study(tmp_path):
    return make_equipment_fixture(tmp_path / "synthetic-equipment-recheck.sqlite")


def _assess(study):
    return service.assess_dc_ac_equipment(
        study.lib.revisions,
        study.comparison,
        study.allocation,
        study.capability_service,
        expected_comparison_sha256=study.expected_comparison_sha256,
        duty_basis=study.duty_basis,
        variant_service=study.lib.variants,
    )


def _check(result, name, identity):
    rows = [
        row
        for row in result["checks"]
        if row["check"] == name and row["equipment_id"] == identity
    ]
    assert len(rows) == 1, rows
    return rows[0]


@pytest.mark.parametrize("identity", ["PCS-01", "TX-01"])
@pytest.mark.parametrize(
    "minimum,maximum,ambient,expected",
    [
        (None, 50, 60, "fail"),
        (-20, None, -30, "fail"),
        (None, 50, 25, "pending"),
        (-20, None, 25, "pending"),
    ],
)
def test_partial_temperature_range_preserves_known_failure_and_missing_evidence(
    study, identity, minimum, maximum, ambient, expected
):
    replace_equipment_package(
        study,
        identity,
        lambda package: package["conditions"].update(
            temperature_min_c=minimum, temperature_max_c=maximum
        ),
    )
    study.duty_basis["ambient_temperature_c"] = ambient

    result = _assess(study)

    assert _check(result, "equipment_ambient_temperature", identity)["status"] == expected
    if expected == "fail":
        assert _check(result, "equipment_temperature_range_completeness", identity)["status"] == "pending"
    assert result["status"] == (
        "fails_discharge_checks" if expected == "fail" else "pending_engineering_evidence"
    )
    assert result["downstream_ready"] is False


def test_unknown_pf_cannot_hide_pcs_apparent_rating_below_known_active_power(study):
    study.duty_basis["power_factor_abs"] = None
    replace_equipment_package(
        study,
        "PCS-01",
        lambda package: package["pcs"].update(
            ac_discharge_power_kw=None, ac_apparent_power_kva=500
        ),
    )

    result = _assess(study)

    duty = next(row for row in result["pcs_duties"] if row["pcs_id"] == "PCS-01")
    assert duty["pcs_ac_reference_kw"] == pytest.approx(1090.9090909090908)
    assert duty["pcs_ac_reference_kva"] is None
    assert _check(result, "pcs_ac_active_power", "PCS-01")["status"] == "pending"
    assert _check(result, "pcs_ac_apparent_power", "PCS-01")["status"] == "pending"
    lower_bound = _check(result, "pcs_ac_apparent_power_active_lower_bound", "PCS-01")
    assert lower_bound["status"] == "fail"
    assert lower_bound["required"] == pytest.approx(duty["pcs_ac_reference_kw"])
    assert lower_bound["declared"] == 500
    assert result["status"] == "fails_discharge_checks"
    assert result["downstream_ready"] is False


def test_unknown_pf_cannot_hide_winding_and_total_transformer_shortfalls(study):
    study.duty_basis["power_factor_abs"] = None
    replace_equipment_package(
        study,
        "TX-01",
        lambda package: package["transformer"].update(
            total_kva=500,
            windings=[dict(winding_id="LV-1", voltage_v=690, continuous_kva=500)],
        ),
    )

    result = _assess(study)

    winding = result["winding_duties"][0]
    transformer = result["transformer_duties"][0]
    assert winding["lv_ac_reference_kw"] == pytest.approx(2000)
    assert transformer["lv_ac_reference_kw"] == pytest.approx(2000)
    assert winding["lv_ac_reference_kva"] is None
    assert transformer["lv_ac_reference_kva"] is None
    for name, identity in (
        ("lv_winding_apparent_power", "TX-01/LV-1"),
        ("total_transformer_apparent_power", "TX-01"),
    ):
        assert _check(result, name, identity)["status"] == "pending"
        lower_bound = _check(result, name + "_active_lower_bound", identity)
        assert lower_bound["status"] == "fail"
        assert lower_bound["required"] == pytest.approx(2000)
        assert lower_bound["declared"] == 500
    assert result["status"] == "fails_discharge_checks"
    assert result["downstream_ready"] is False


def test_retirement_during_final_dc_source_check_invalidates_equipment_result(
    study, monkeypatch
):
    original = service.revalidate_allocation_source
    withdrawals = []

    def withdraw_after_source_check(*args, **kwargs):
        source = original(*args, **kwargs)
        study.capability_service.transition(
            study.capability_revision_ids["PCS-01"],
            "candidate_only",
            "retired",
            "SYNTHETIC withdrawal during final source revalidation",
        )
        withdrawals.append(True)
        return source

    monkeypatch.setattr(service, "revalidate_allocation_source", withdraw_after_source_check)

    with pytest.raises(ValueError, match="review changed"):
        _assess(study)
    assert withdrawals == [True]


def test_diagnostic_declares_separate_read_checkpoints_and_atomic_adoption_gate(study):
    result = _assess(study)

    assert result["review_consistency"] == "separate_read_checkpoints"
    assert result["adoption_requires_atomic_revalidation"] is True
    assert result["comparison_only"] is True
    assert result["downstream_ready"] is False
