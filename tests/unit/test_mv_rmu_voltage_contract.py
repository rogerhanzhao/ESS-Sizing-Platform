from __future__ import annotations

from pathlib import Path

import pytest

from calb_diagrams.sld_pro_renderer import render_sld_pro_svg, render_sld_svg
from calb_diagrams.specs import SldGroupSpec
from calb_sizing_tool.schemas.diagram_inputs import SldRenderOptions
from calb_sizing_tool.schemas.sld_render_input import SldInputOverride, legacy_sld_override_preset
from calb_sizing_tool.services.sld_input_builder import build_sld_canonical_input
from calb_sizing_tool.services.sld_topology_builder import build_sld_topology
from calb_sizing_tool.sld.voltage_contract import resolve_mv_rmu_voltage_contract
from tests.unit.test_sld_input_contract import _build_run_bundle, _make_ac_snapshot


def _override_payload(*, rmu_rated_kv: float) -> dict:
    payload = legacy_sld_override_preset()
    payload["dc_block_voltage_v"] = 1500.0
    payload["dc_blocks_per_feeder"] = [1, 1, 1, 1]
    payload["equipment_ratings"]["rmu"]["rated_kv"] = rmu_rated_kv
    return payload


def test_voltage_contract_uses_single_authoritative_mv_value_for_rmu():
    contract = resolve_mv_rmu_voltage_contract(mv_nominal_voltage_kv=33.0)
    assert contract.authoritative_mv_voltage_kv == pytest.approx(33.0)
    assert contract.rmu_rated_voltage_kv == pytest.approx(33.0)


@pytest.mark.parametrize("mv_kv", [22.0, 33.0, 34.5])
def test_voltage_contract_does_not_map_mv_to_separate_equipment_class(mv_kv: float):
    contract = resolve_mv_rmu_voltage_contract(mv_nominal_voltage_kv=mv_kv)

    assert contract.authoritative_mv_voltage_kv == pytest.approx(mv_kv)
    assert contract.rmu_rated_voltage_kv == pytest.approx(mv_kv)


def test_builder_forces_rmu_rated_voltage_to_match_poi_mv_voltage(sample_excel_path):
    canonical = build_sld_canonical_input(
        run_bundle=_build_run_bundle(sample_excel_path),
        ac_snapshot=_make_ac_snapshot(),
        options=SldRenderOptions(
            group_index=1,
            override_mode=True,
            overrides=SldInputOverride.model_validate(_override_payload(rmu_rated_kv=24.0)),
        ),
        validation_mode="strict",
    )

    assert canonical.mv_voltage_kv == pytest.approx(33.0)
    assert canonical.equipment_ratings.rmu.rated_kv == pytest.approx(33.0)
    assert any("authoritative POI / MV voltage 33 kV" in message for message in canonical.draft_warnings)


def test_renderer_uses_same_rmu_voltage_as_authoritative_mv_input(sample_excel_path, tmp_path: Path):
    pytest.importorskip("svgwrite")

    canonical = build_sld_canonical_input(
        run_bundle=_build_run_bundle(sample_excel_path),
        ac_snapshot=_make_ac_snapshot(),
        options=SldRenderOptions(
            group_index=1,
            override_mode=True,
            overrides=SldInputOverride.model_validate(_override_payload(rmu_rated_kv=24.0)),
        ),
        validation_mode="strict",
    )

    assert canonical.equipment_ratings.rmu.rated_kv == pytest.approx(33.0)

    topology = build_sld_topology(canonical)
    svg_path = tmp_path / "rmu_tracks_mv_voltage.svg"
    result_path, warning = render_sld_svg(
        topology,
        layout_profile="engineering_readable",
        theme="dark",
        out_svg=svg_path,
    )

    assert result_path == svg_path
    assert warning is None
    svg_text = svg_path.read_text(encoding="utf-8")
    assert "33 kV" in svg_text


def test_renderer_compatibility_wrapper_rejects_missing_rmu_rated_kv(tmp_path: Path):
    spec = SldGroupSpec(
        group_index=1,
        ac_blocks_total=1,
        mv_voltage_kv=33.0,
        lv_voltage_v_ll=690.0,
        transformer_mva=6.0,
        transformer_vector_group="Dyn11",
        transformer_uk_percent=7.0,
        pcs_count=1,
        pcs_rating_kw_list=[1250.0],
        dc_block_energy_mwh=1.0,
        dc_blocks_total_in_group=1,
        dc_blocks_per_feeder=[1],
        equipment_list={
            "mv_labels": {"to_switchgear": "To Switchgear", "to_other_rmu": "To Other RMU"},
            "rmu": {
                "rated_a": 630.0,
                "short_circuit_ka_3s": 25.0,
                "ct_ratio": "200/1",
                "ct_class": "5P20",
                "ct_va": 10.0,
            },
            "transformer": {"vector_group": "Dyn11", "uk_percent": 7.0, "cooling": "ONAN"},
            "lv_busbar": {"rated_a": 2500.0, "short_circuit_ka": 25.0},
            "cables": {"mv_cable_spec": "TBD", "lv_cable_spec": "TBD", "dc_cable_spec": "TBD"},
            "dc_fuse": {"fuse_spec": "DC isolator/fuse"},
            "dc_block_voltage_v": 1500.0,
        },
        layout_params={"theme": "dark"},
    )

    with pytest.raises(ValueError, match="Renderer will not infer RMU equipment class"):
        render_sld_pro_svg(spec, tmp_path / "missing_rmu_rated_kv.svg")
