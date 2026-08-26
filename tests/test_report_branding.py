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

"""Brand-separation regression tests for the V2.1 report export.

Owner rule: the white-label (Guoxia) variant must contain no CALB branding
anywhere in the rendered document (body, headers, footers), and the CALB
variant must contain no Guoxia/Hanchu branding.  Any new report copy that
bypasses BrandProfile will fail these tests.
"""

import base64
import dataclasses
import io
import json
import re
import zipfile
from pathlib import Path

import pytest
from docx import Document

from calb_sizing_tool.reporting.brand_profiles import (
    BRAND_PROFILES,
    CALB_BRAND,
    GUOXIA_BRAND,
    BrandAssetMissingError,
    BrandLeakError,
    assert_brand_clean_docx,
    neutralize_brand_text,
    neutralize_equipment_text,
    neutralize_svg_visible_text,
    require_brand_assets,
)
from calb_sizing_tool.reporting.report_context import build_report_context
from calb_sizing_tool.reporting.report_v2 import (
    _report_context_for_brand,
    export_report_v2_1,
)
from tools.regress_export import run_ac_sizing, run_dc_sizing


@pytest.fixture(scope="module")
def report_ctx():
    fixture_path = Path(__file__).parent / "fixtures" / "v1_case01_container_input.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))

    dc_results = run_dc_sizing(fixture)
    ac_output = run_ac_sizing(fixture, dc_results["stage1"], dc_results["stage2"])

    png_bytes = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4nGNgYAAAAAMAASsJTYQAAAAASUVORK5CYII="
    )
    svg_bytes = (
        b'<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10" '
        b'viewBox="0 0 10 10"><rect width="10" height="10" fill="white"/>'
        b'<text x="1" y="7">SLD</text></svg>'
    )

    return build_report_context(
        session_state={
            "artifacts": {
                "sld_png_bytes": png_bytes,
                "sld_svg_bytes": svg_bytes,
                "layout_png_bytes": png_bytes,
                "layout_svg_bytes": svg_bytes,
            }
        },
        stage_outputs={
            "stage13_output": dc_results["stage1"],
            "stage2": dc_results["stage2"],
            "stage3_df": dc_results["stage3_df"],
            "stage3_meta": dc_results["stage3_meta"],
            "ac_output": ac_output,
        },
        project_inputs={"poi_energy_guarantee_mwh": fixture["poi_energy_req_mwh"]},
        scenario_ids=fixture["scenario_id"],
    )


def _rendered_xml_parts(report_bytes: bytes) -> dict[str, str]:
    """Return decoded XML for the document body plus every header and footer part."""
    parts = {}
    with zipfile.ZipFile(io.BytesIO(report_bytes)) as archive:
        for name in archive.namelist():
            if name == "word/document.xml" or (
                name.startswith("word/header") or name.startswith("word/footer")
            ):
                parts[name] = archive.read(name).decode("utf-8")
    return parts


def test_guoxia_variant_contains_no_calb_branding(report_ctx):
    report_bytes = export_report_v2_1(report_ctx, brand=GUOXIA_BRAND)
    parts = _rendered_xml_parts(report_bytes)
    assert "word/document.xml" in parts
    for name, xml in parts.items():
        assert "CALB" not in xml, f"CALB branding leaked into Guoxia variant part {name}"

    body = parts["word/document.xml"]
    assert "Guoxia Technology Co., Ltd." in body
    assert "HKEX: 02655" in body
    header_xml = "".join(x for n, x in parts.items() if n.startswith("word/header"))
    assert "Guoxia Technology Co., Ltd." in header_xml


def test_guoxia_variant_neutralizes_runtime_project_and_case_branding(report_ctx):
    contaminated = dataclasses.replace(
        report_ctx,
        project_name="CALB ESS Project",
        case_name="CALB Demo Case",
    )
    report_bytes = export_report_v2_1(contaminated, brand=GUOXIA_BRAND)
    parts = _rendered_xml_parts(report_bytes)
    assert all("CALB" not in xml for xml in parts.values())
    body = parts["word/document.xml"]
    assert "Project: ESS Project" in body
    assert "Case: Demo Case" in body


def test_guoxia_runtime_alias_covers_product_payload_without_editing_run(report_ctx):
    table = report_ctx.stage2["block_config_table"].copy(deep=True)
    table.loc[table.index[0], "Block Code"] = "CALB-5MWh"
    contaminated = dataclasses.replace(
        report_ctx,
        project_name="CALB Project",
        stage2={**report_ctx.stage2, "block_config_table": table},
        ac_output={**report_ctx.ac_output, "bound_product_code": "CALB-PCS-01"},
    )

    customer_ctx = _report_context_for_brand(contaminated, GUOXIA_BRAND)

    assert customer_ctx.project_name == "Project"
    assert customer_ctx.stage2["block_config_table"].iloc[0]["Block Code"] == "5MWh"
    assert customer_ctx.ac_output["bound_product_code"] == "PCS-01"
    assert contaminated.stage2["block_config_table"].iloc[0]["Block Code"] == "CALB-5MWh"
    assert contaminated.ac_output["bound_product_code"] == "CALB-PCS-01"


def test_report_context_default_project_name_is_brand_neutral(report_ctx):
    stage1 = dict(report_ctx.stage1)
    stage1.pop("project_name", None)
    ac_output = dict(report_ctx.ac_output)
    ac_output.pop("project_name", None)

    rebuilt = build_report_context(
        session_state={},
        stage_outputs={
            "stage13_output": stage1,
            "stage2": report_ctx.stage2,
            "stage3_df": report_ctx.stage3_df,
            "stage3_meta": report_ctx.stage3_meta,
            "ac_output": ac_output,
        },
        project_inputs={
            "poi_energy_guarantee_mwh": report_ctx.poi_energy_guarantee_mwh,
        },
        scenario_ids=report_ctx.scenario_id,
    )
    assert rebuilt.project_name == "Untitled ESS Project"


def test_guoxia_variant_requires_auditable_svg_for_stored_sld(report_ctx):
    png_only = dataclasses.replace(report_ctx, sld_preview_svg_bytes=None)
    with pytest.raises(BrandLeakError, match="only a raster image"):
        export_report_v2_1(png_only, brand=GUOXIA_BRAND)


def test_visible_svg_brand_text_is_neutralized():
    source = (
        b'<svg xmlns="http://www.w3.org/2000/svg" width="100" height="20">'
        b'<text x="0" y="15">CALB 5MWh DC Block</text></svg>'
    )
    cleaned = neutralize_svg_visible_text(source, GUOXIA_BRAND).decode("utf-8")
    assert "CALB" not in cleaned
    assert "5MWh DC Block" in cleaned


def test_brand_neutralization_preserves_whitespace_and_internal_svg_css():
    assert neutralize_brand_text("   ", GUOXIA_BRAND) == "   "
    source = (
        b'<svg xmlns="http://www.w3.org/2000/svg">'
        b'<style>.calb-document-status{fill:red}</style>'
        b'<text class="calb-document-status">CALB STATUS</text>'
        b'</svg>'
    )

    cleaned = neutralize_svg_visible_text(source, GUOXIA_BRAND).decode("utf-8")

    assert ".calb-document-status{fill:red}" in cleaned
    assert "CALB STATUS" not in cleaned
    assert ">STATUS<" in cleaned


def test_final_docx_brand_gate_blocks_uncontrolled_text():
    doc = Document()
    doc.add_paragraph("Prepared from CALB runtime data")
    buffer = io.BytesIO()
    doc.save(buffer)
    with pytest.raises(BrandLeakError, match="forbidden brand text"):
        assert_brand_clean_docx(buffer.getvalue(), GUOXIA_BRAND)


def test_calb_variant_contains_no_guoxia_branding(report_ctx):
    report_bytes = export_report_v2_1(report_ctx, brand=CALB_BRAND)
    parts = _rendered_xml_parts(report_bytes)
    for name, xml in parts.items():
        assert "Guoxia" not in xml, f"Guoxia branding leaked into CALB variant part {name}"
        assert "GUOXIA" not in xml, f"GUOXIA branding leaked into CALB variant part {name}"
        assert "Hanchu" not in xml and "HANCHU" not in xml, (
            f"Hanchu branding leaked into CALB variant part {name}"
        )

    body = parts["word/document.xml"]
    assert "CALB Group Co., Ltd." in body


def test_default_brand_is_calb(report_ctx):
    default_bytes = export_report_v2_1(report_ctx)
    explicit_bytes = export_report_v2_1(report_ctx, brand=CALB_BRAND)
    assert _rendered_xml_parts(default_bytes).keys() == _rendered_xml_parts(explicit_bytes).keys()
    assert "CALB Group Co., Ltd." in _rendered_xml_parts(default_bytes)["word/document.xml"]


def test_report_images_have_accessible_descriptions(report_ctx):
    """Every inline picture, including the header logo, names its content."""
    report_bytes = export_report_v2_1(report_ctx, brand=CALB_BRAND)
    parts = _rendered_xml_parts(report_bytes)
    image_properties = []
    for xml in parts.values():
        image_properties.extend(re.findall(r"<wp:docPr\b[^>]*>", xml))

    assert image_properties, "expected inline images in the report"
    for props in image_properties:
        assert re.search(r'\bdescr="[^"]+"', props), props
        assert re.search(r'\btitle="[^"]+"', props), props


def test_equipment_name_neutralization():
    assert (
        neutralize_equipment_text("CALB_5MWh_20FT_12R", GUOXIA_BRAND) == "5MWh_20FT_12R"
    )
    assert (
        neutralize_equipment_text("CALB 5MWh 20ft Container - 12 Racks", GUOXIA_BRAND)
        == "5MWh 20ft Container - 12 Racks"
    )
    # CALB variant keeps supplier names untouched
    assert (
        neutralize_equipment_text("CALB_5MWh_20FT_12R", CALB_BRAND) == "CALB_5MWh_20FT_12R"
    )
    # A value made only of the forbidden publisher name must not reintroduce it.
    assert neutralize_equipment_text("CALB", GUOXIA_BRAND) == "Unbranded equipment"


def test_missing_required_logo_blocks_export():
    broken = dataclasses.replace(
        GUOXIA_BRAND, logo_path=Path("does-not-exist-logo.png")
    )
    with pytest.raises(BrandAssetMissingError):
        require_brand_assets(broken)


def test_guoxia_logo_asset_exists():
    """The dual-brand logo referenced by the profile must ship with the repo."""
    assert GUOXIA_BRAND.logo_path is not None and GUOXIA_BRAND.logo_path.exists()


@pytest.mark.parametrize("profile", (CALB_BRAND, GUOXIA_BRAND), ids=lambda value: value.key)
def test_confidentiality_notice_has_no_double_terminal_period(profile):
    assert "Ltd.." not in profile.confidentiality_notice


def test_profile_registry_matches_ui_labels():
    """Two profiles, named for the release — the number is not hand-written here.

    This used to pin the literals "V2.1 (Beta)" / "V2.1 (Guoxia)", so a release
    bump had to be applied in one more place or the suite went red for no
    engineering reason. The release now comes from VERSION, which
    test_app_version.test_the_report_cannot_drift_from_the_release_file already
    holds equal to every brand's version_tag; what this test owns is the SHAPE:
    exactly two profiles, Beta first, each labelled with the running release.
    """
    from calb_sizing_tool import app_version

    release = app_version.release_version()
    assert list(BRAND_PROFILES.keys()) == [f"{release} (Beta)", f"{release} (Guoxia)"]
