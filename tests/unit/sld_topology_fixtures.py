"""Topology fixtures shared by the SLD test modules.

These lived inside tests/unit/test_sld_layout_engine.py, so three live
engineering_v2 test files imported their scaffolding from the test file of a
DIFFERENT module — which is why retiring that module broke eleven collections
at once. A fixture belongs somewhere neutral, not inside whichever test file
happened to write it first.
"""
from __future__ import annotations

from calb_sizing_tool.schemas.diagram_inputs import SldRenderOptions
from calb_sizing_tool.schemas.sld_render_input import SldInputOverride, legacy_sld_override_preset
from calb_sizing_tool.services.sld_input_builder import build_sld_canonical_input
from calb_sizing_tool.services.sld_topology_builder import build_sld_topology
from tests.unit.test_sld_topology_builder import _build_run_bundle, _make_ac_snapshot


def _build_topology(sample_excel_path):
    run_bundle = _build_run_bundle(sample_excel_path)
    override_payload = legacy_sld_override_preset()
    override_payload["transformer_vector_group"] = "Dyn11yn11"
    override_payload["dc_block_voltage_v"] = 1500.0
    override_payload["dc_blocks_per_feeder"] = [1, 1, 1, 1]
    canonical = build_sld_canonical_input(
        run_bundle=run_bundle,
        ac_snapshot=_make_ac_snapshot(),
        options=SldRenderOptions(
            group_index=1,
            override_mode=True,
            overrides=SldInputOverride.model_validate(override_payload),
        ),
        validation_mode="strict",
    )
    return build_sld_topology(canonical)

def _build_single_winding_topology(sample_excel_path):
    run_bundle = _build_run_bundle(sample_excel_path)
    ac_snapshot = _make_ac_snapshot()
    ac_output = dict(ac_snapshot.output)
    ac_output.update(
        {
            "pcs_per_block": 2,
            "pcs_kw": 2500.0,
            "block_size_mw": 5.0,
            "transformer_mva": 5.0,
            "dc_allocation_plan": [
                {"ac_block_index": 1, "dc_blocks_total": 2, "feeder_allocations": [1, 1]}
            ],
        }
    )
    override_payload = legacy_sld_override_preset()
    override_payload["dc_block_voltage_v"] = 1500.0
    override_payload["dc_blocks_per_feeder"] = [1, 1]
    canonical = build_sld_canonical_input(
        run_bundle=run_bundle,
        ac_snapshot=ac_snapshot.model_copy(update={"output": ac_output}),
        options=SldRenderOptions(
            group_index=1,
            override_mode=True,
            overrides=SldInputOverride.model_validate(override_payload),
        ),
        validation_mode="strict",
    )
    return build_sld_topology(canonical)
