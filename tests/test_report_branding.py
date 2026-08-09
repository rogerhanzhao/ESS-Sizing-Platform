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

from calb_sizing_tool.reporting.brand_profiles import (
    BRAND_PROFILES,
    CALB_BRAND,
    GUOXIA_BRAND,
    BrandAssetMissingError,
    neutralize_equipment_text,
    require_brand_assets,
)
from calb_sizing_tool.reporting.report_context import build_report_context
from calb_sizing_tool.reporting.report_v2 import export_report_v2_1
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

    return build_report_context(
        session_state={
            "artifacts": {
                "sld_png_bytes": png_bytes,
                "layout_png_bytes": png_bytes,
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
    # Scrub never returns an empty string even if the whole text is the brand token
    assert neutralize_equipment_text("CALB", GUOXIA_BRAND) == "CALB"


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
