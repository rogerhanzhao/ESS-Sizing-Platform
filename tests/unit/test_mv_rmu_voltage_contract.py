from __future__ import annotations

from pathlib import Path

import pytest

from calb_diagrams.sld_engineering_v2_layout import build_sld_engineering_v2_layout_plan
from calb_diagrams.sld_engineering_v2_renderer import render_sld_engineering_v2_svg
from calb_diagrams.specs import SldGroupSpec
from calb_sizing_tool.schemas.diagram_inputs import SldRenderOptions
from calb_sizing_tool.schemas.sld_render_input import SldInputOverride, legacy_sld_override_preset
from calb_sizing_tool.services.sld_input_builder import build_sld_canonical_input
from calb_sizing_tool.services.sld_engineering_v2_builder import build_sld_engineering_v2_graph
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
    plan = build_sld_engineering_v2_layout_plan(build_sld_engineering_v2_graph(topology), theme="dark")
    result_path, warning = render_sld_engineering_v2_svg(plan, svg_path)

    assert result_path == svg_path
    assert warning is None
    svg_text = svg_path.read_text(encoding="utf-8")
    assert "33 kV" in svg_text
