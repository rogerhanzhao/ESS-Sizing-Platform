"""One Typical AC Block Arrangement: report and page must draw the SAME thing.

Owner instruction 2026-08-03: "无论是导出的报告还是页面展示的 typical ac block
arrangement 都要一致的逻辑排布和绘制."

The report and the page used to carry their own copy of the engine-selection
rule, the title rule, the power/station resolution and the CONCEPT marking. Four
duplicated rules, four ways to drift. These tests hold the drawing identical and
lock the rules to one implementation.
"""
from __future__ import annotations

import pytest

from calb_diagrams.ac_block_arrangement_v2 import US_NFPA_OIL
from calb_diagrams.typical_ac_block_arrangement import (
    CENTRAL_STATION_VARIANT,
    DOCUMENT_STATUS_GROUP_ID,
    LINEAR_VARIANT,
    AcBlockShape,
    apply_concept_watermark,
    arrangement_spec,
    render_typical_ac_block,
    resolve_block_power_mw,
    resolve_dc_blocks_for_block,
    resolve_pcs_for_block,
    strip_document_status,
    uses_central_station,
)

_AC_OUTPUT_8x8 = {
    "num_blocks": 13, "pcs_per_block": 8, "pcs_kw": 1250.0, "block_size_mw": 10.0,
    "total_ac_mw": 130.0, "dc_blocks_total": 104,
    "dc_allocation_plan": [
        {"ac_block_index": i, "dc_blocks_total": 8} for i in range(1, 14)
    ],
}


def _page_svg(ac_output: dict, block_index: int = 1) -> str:
    from calb_sizing_tool.plugins.layout_arrangement_v2_plugin import LayoutArrangementV2Plugin
    from calb_sizing_tool.schemas.diagram_inputs import AcSnapshot
    from calb_sizing_tool.schemas.layout_inputs import LayoutRenderInput, LayoutRenderOptions
    from calb_sizing_tool.schemas.run_bundle import DcRunBundle

    render_input = LayoutRenderInput.model_construct(
        run_id="run-1",
        run_bundle=DcRunBundle.model_construct(
            run_id="run-1", project_code="P", project_name="Proj",
            case_code="C", case_name="Case",
        ),
        ac_snapshot=AcSnapshot(inputs={}, output=ac_output, results={}),
        topology_snapshot=None, layout_rules=None,
        options=LayoutRenderOptions(block_index=block_index),
    )
    return LayoutArrangementV2Plugin().render(render_input)["svg_bytes"].decode("utf-8")


def _report_svg(ac_output: dict) -> str:
    from calb_sizing_tool.reporting.report_context import build_report_context
    from calb_sizing_tool.reporting.report_v2 import (
        ARRANGEMENT_PROFILE, _arrangement_shape,
    )

    ctx = build_report_context(
        session_state={},
        stage_outputs={
            "stage13_output": {
                "project_name": "Consistency", "poi_power_req_mw": 115.0,
                "poi_energy_req_mwh": 400.0, "project_life_years": 20,
                "poi_guarantee_year": 4, "cycles_per_year": 365,
            },
            "ac_output": ac_output,
            "stage2": {"container_count": ac_output.get("dc_blocks_total", 104),
                       "dc_nameplate_bol_mwh": 521.6},
        },
        project_inputs={},
    )
    return render_typical_ac_block(_arrangement_shape(ctx), ARRANGEMENT_PROFILE).svg


# ---------------------------------------------------------------------------
# The invariant the owner asked for
# ---------------------------------------------------------------------------


def test_report_and_page_emit_the_identical_drawing():
    """Byte-for-byte, once the page's own document-status overlay is set aside.

    The overlay is not a difference in the DRAWING: the page hands out a
    standalone SVG so it stamps the SVG, while the report rasterises and stamps
    the raster through the fail-closed watermark path. Everything else — engine,
    title, geometry, glyphs, dimensions — has to match exactly.
    """
    page = strip_document_status(_page_svg(_AC_OUTPUT_8x8))
    report = _report_svg(_AC_OUTPUT_8x8)
    assert page == report


def test_report_and_page_agree_for_a_smaller_block_too():
    ac_output = {
        "num_blocks": 10, "pcs_per_block": 4, "pcs_kw": 1250.0,
        "block_size_mw": 5.0, "total_ac_mw": 50.0, "dc_blocks_total": 40,
        "dc_allocation_plan": [
            {"ac_block_index": i, "dc_blocks_total": 4} for i in range(1, 11)
        ],
    }
    assert strip_document_status(_page_svg(ac_output)) == _report_svg(ac_output)


def test_neither_surface_reimplements_the_engine_rule():
    """Both must reach the shared rule; nothing may hardcode 8-and-8 again."""
    import inspect

    from calb_sizing_tool.plugins import layout_arrangement_v2_plugin as page
    from calb_sizing_tool.reporting import report_v2 as report

    for module in (page, report):
        src = inspect.getsource(module)
        assert "render_typical_ac_block" in src, module.__name__
        # The old duplicated shape test must not come back in either surface.
        assert "pcs_count == 8 and dc_blocks_total == 8" not in src, module.__name__
        assert "== 8 and _dc_per_ac_shape == 8" not in src, module.__name__


# ---------------------------------------------------------------------------
# The rules themselves
# ---------------------------------------------------------------------------


def test_engine_rule_keys_off_shape_and_governed_variant_alike():
    assert uses_central_station(8, 8) is True
    assert uses_central_station(8, 8, "") is True
    # A governed run forces it even if the shape were read some other way.
    assert uses_central_station(4, 4, CENTRAL_STATION_VARIANT) is True
    # Anything else is the linear row.
    assert uses_central_station(4, 4) is False
    assert uses_central_station(8, 7) is False
    assert uses_central_station(6, 8) is False
    assert uses_central_station(None, None) is False


def test_a_governed_model_name_titles_the_drawing():
    shape = AcBlockShape(dc_blocks=8, pcs_count=8, block_power_mw=10.0,
                         model_name="ACBLK-10MW-8PCS-8DC-40FT-BILATERAL")
    arrangement = render_typical_ac_block(shape)
    assert arrangement.label == "ACBLK-10MW-8PCS-8DC-40FT-BILATERAL"
    assert arrangement.label in arrangement.svg


def test_a_generic_run_gets_a_descriptive_title():
    arrangement = render_typical_ac_block(
        AcBlockShape(dc_blocks=8, pcs_count=8, block_power_mw=10.0, block_index=3)
    )
    assert arrangement.label == "TYPICAL AC BLOCK 3 · 8 PCS / 8 DC · 40 FT CENTRAL STATION"


def test_the_central_station_block_is_the_forty_foot_product():
    arrangement = render_typical_ac_block(
        AcBlockShape(dc_blocks=8, pcs_count=8, block_power_mw=10.0)
    )
    assert arrangement.layout_variant == CENTRAL_STATION_VARIANT
    assert arrangement.station_length_m == pytest.approx(12.192, abs=0.001)
    assert arrangement.envelope_w_m == pytest.approx(18.790, abs=0.001)
    assert arrangement.envelope_d_m == pytest.approx(13.016, abs=0.001)
    assert arrangement.envelope_area_m2 == pytest.approx(244.6, abs=0.2)
    assert len(arrangement.placements) == 9
    assert arrangement.provisional_notes


def test_a_smaller_block_is_the_linear_row_with_its_own_station_class():
    arrangement = render_typical_ac_block(
        AcBlockShape(dc_blocks=4, pcs_count=4, block_power_mw=5.0)
    )
    assert arrangement.layout_variant == LINEAR_VARIANT
    assert arrangement.station_length_m == pytest.approx(6.058, abs=0.001)
    assert arrangement.envelope_w_m == pytest.approx(22.074, abs=0.001)
    assert arrangement.placements == ()


def test_an_empty_block_fails_closed_rather_than_drawing_nothing():
    with pytest.raises(ValueError, match="no DC Blocks"):
        render_typical_ac_block(AcBlockShape(dc_blocks=0, pcs_count=8))


def test_the_watermark_is_applied_and_removable_for_comparison():
    plain = render_typical_ac_block(AcBlockShape(dc_blocks=8, pcs_count=8,
                                                 block_power_mw=10.0))
    stamped = apply_concept_watermark(plain.svg)
    assert DOCUMENT_STATUS_GROUP_ID in stamped
    assert "CONCEPT ONLY - NOT FOR CONSTRUCTION" in stamped
    assert strip_document_status(stamped) == plain.svg
    # Removing an overlay that is not there is a no-op, never a corruption.
    assert strip_document_status(plain.svg) == plain.svg


def test_watermark_refuses_malformed_svg():
    with pytest.raises(ValueError, match="malformed SVG"):
        apply_concept_watermark("<svg>no closing tag")


# ---------------------------------------------------------------------------
# Shared resolution helpers — the page and the report count the same way
# ---------------------------------------------------------------------------


def test_dc_and_pcs_come_from_the_per_block_plan_not_a_fleet_average():
    ac_output = {
        "num_blocks": 2, "pcs_per_block": 8, "pcs_kw": 1250.0,
        "block_size_mw": 10.0, "pcs_count_by_block": [8, 3],
        "dc_allocation_plan": [
            {"ac_block_index": 1, "dc_blocks_total": 8},
            {"ac_block_index": 2, "dc_blocks_total": 3},
        ],
    }
    assert resolve_dc_blocks_for_block(ac_output, 1) == 8
    assert resolve_dc_blocks_for_block(ac_output, 2) == 3
    assert resolve_pcs_for_block(ac_output, 1) == 8
    assert resolve_pcs_for_block(ac_output, 2) == 3
    # A tail block is a SMALLER block, never the fleet nominal.
    assert resolve_block_power_mw(ac_output, 3) == pytest.approx(3.75, abs=0.001)
    assert resolve_block_power_mw(ac_output, 8) == pytest.approx(10.0, abs=0.001)


def test_missing_plan_reports_nothing_rather_than_guessing():
    assert resolve_dc_blocks_for_block({"num_blocks": 4}, 1) == 0


def test_the_spec_carries_the_code_basis_for_every_clearance():
    arrangement = render_typical_ac_block(
        AcBlockShape(dc_blocks=8, pcs_count=8, block_power_mw=10.0)
    )
    spec = arrangement_spec(arrangement, US_NFPA_OIL)
    assert spec["layout_variant"] == CENTRAL_STATION_VARIANT
    assert spec["envelope_area_m2"] == arrangement.envelope_area_m2
    assert spec["clearances_m"]["dc_equipment_end"] == pytest.approx(3.0)
    assert spec["code_basis"] and all(entry["basis"] for entry in spec["code_basis"])
    assert len(spec["placements"]) == 9


def test_the_page_spec_is_generated_from_the_same_values_as_the_drawing():
    from calb_sizing_tool.plugins.layout_arrangement_v2_plugin import LayoutArrangementV2Plugin
    from calb_sizing_tool.schemas.diagram_inputs import AcSnapshot
    from calb_sizing_tool.schemas.layout_inputs import LayoutRenderInput, LayoutRenderOptions
    from calb_sizing_tool.schemas.run_bundle import DcRunBundle

    render_input = LayoutRenderInput.model_construct(
        run_id="run-1",
        run_bundle=DcRunBundle.model_construct(
            run_id="run-1", project_code="P", project_name="Proj",
            case_code="C", case_name="Case",
        ),
        ac_snapshot=AcSnapshot(inputs={}, output=_AC_OUTPUT_8x8, results={}),
        topology_snapshot=None, layout_rules=None,
        options=LayoutRenderOptions(block_index=1),
    )
    out = LayoutArrangementV2Plugin().render(render_input)
    shared = render_typical_ac_block(
        AcBlockShape(dc_blocks=8, pcs_count=8, block_power_mw=10.0, block_index=1)
    )
    assert out["spec"]["envelope_w_m"] == shared.envelope_w_m
    assert out["spec"]["envelope_d_m"] == shared.envelope_d_m
    assert out["spec"]["station_length_m"] == shared.station_length_m
    assert out["spec"]["label"] == shared.label
    assert out["metadata"]["envelope_area_m2"] == shared.envelope_area_m2


# ---------------------------------------------------------------------------
# AUDIT 2026-08-04 — divergences found by probing REALISTIC runs, not the
# happy path. All three were "same block, two answers" bugs hiding in the last
# thing still written twice: how the run is read.
# ---------------------------------------------------------------------------


def _matrix_case(ac_output: dict) -> tuple[str, str]:
    """Render the same run through both surfaces; return (page, report) SVG."""
    try:
        page = strip_document_status(_page_svg(ac_output))
    except Exception as exc:                                  # noqa: BLE001
        page = f"__ERROR__ {type(exc).__name__}"
    try:
        report = _report_svg(ac_output)
    except Exception as exc:                                  # noqa: BLE001
        report = f"__ERROR__ {type(exc).__name__}"
    return page, report


def test_a_generic_run_with_a_product_name_titles_both_surfaces_the_same():
    """Found by audit: the page honoured ac_block_model_name, the report did not."""
    ac_output = dict(_AC_OUTPUT_8x8, ac_block_model_name="CALB 10 MW 1:8")
    page, report = _matrix_case(ac_output)
    assert page == report
    assert "CALB 10 MW 1:8" in report


def test_the_governed_variant_is_honoured_under_either_key():
    """Found by audit: report read layout_variant, page read ac_block_arrangement.

    ac_view writes both today, so the two agreed by luck. A writer that sets only
    one would have split them — and the shape test masks it whenever the block is
    already 8-and-8, so it would have shipped unnoticed.
    """
    assert uses_central_station(4, 4, "central_40ft_bilateral_4plus4") is True
    for key in ("layout_variant", "ac_block_arrangement"):
        from calb_diagrams.typical_ac_block_arrangement import resolve_layout_variant

        assert resolve_layout_variant({key: CENTRAL_STATION_VARIANT}) == CENTRAL_STATION_VARIANT
    for key in ("layout_variant", "ac_block_arrangement"):
        page, report = _matrix_case(dict(_AC_OUTPUT_8x8, **{key: CENTRAL_STATION_VARIANT}))
        assert page == report, key


def test_a_run_without_a_per_block_plan_still_agrees():
    """Found by audit: the page hard-failed while the report drew from the average."""
    ac_output = {k: v for k, v in _AC_OUTPUT_8x8.items() if k != "dc_allocation_plan"}
    page, report = _matrix_case(ac_output)
    assert not page.startswith("__ERROR__"), page
    assert page == report
    # The fallback is the fleet average, and it must be the SAME fallback.
    assert resolve_dc_blocks_for_block(ac_output, 1) == 8


def test_a_run_with_neither_a_plan_nor_totals_still_fails_closed():
    assert resolve_dc_blocks_for_block({"num_blocks": 4}, 1) == 0
    with pytest.raises(ValueError, match="no DC Blocks"):
        render_typical_ac_block(AcBlockShape(dc_blocks=0, pcs_count=8))


def test_the_station_class_is_named_not_printed_as_a_raw_metre_value():
    """"6.06 M STATION" tells a reader nothing; "20 FT STATION" identifies it."""
    small = render_typical_ac_block(
        AcBlockShape(dc_blocks=4, pcs_count=4, block_power_mw=5.0))
    assert small.label.endswith("20 FT STATION")
    big = render_typical_ac_block(
        AcBlockShape(dc_blocks=6, pcs_count=8, block_power_mw=10.0))
    assert big.label.endswith("40 FT STATION")
    assert "M STATION" not in small.label and "M STATION" not in big.label
