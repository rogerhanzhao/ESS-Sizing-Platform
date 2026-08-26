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

"""Brand profiles for the V2.2 report export.

Every customer-visible branded string in the report MUST come from a
BrandProfile field.  Do not add per-call-site fallback strings in
report_v2.py: new branded copy is added HERE, to every profile, so a
white-label variant can never silently fall back to CALB wording.
The two profiles are kept side by side so their differences can be
reviewed with a single diff.

Regression guard: tests/unit/test_report_branding.py renders both variants
and asserts that no scrub term of one brand leaks into the other.
"""

from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional, Tuple
from xml.etree import ElementTree as ET

from calb_sizing_tool.config import PROJECT_ROOT


class BrandAssetMissingError(RuntimeError):
    """A required brand asset (e.g. logo file) is missing; export must not proceed.

    White-label exports must never fall back to another brand's assets.
    """


class BrandLeakError(RuntimeError):
    """A white-label export still contains a forbidden brand token."""


def _confidentiality_notice(owner: str) -> str:
    owner = owner.rstrip(".")
    return (
        f"CONFIDENTIAL — This document contains proprietary information of {owner}. "
        "It is provided for evaluation purposes only and shall not be reproduced or "
        "disclosed to third parties without prior written consent. Sizing results are "
        "preliminary and subject to detailed engineering confirmation."
    )


@dataclass(frozen=True)
class BrandProfile:
    key: str
    display_name: str  # UI template selector label
    company_legal_name: str
    header_title: str
    header_lines: Tuple[str, ...]
    footer_lines: Tuple[str, ...]  # empty tuple = no branded footer text
    cover_title: str
    issuer_lines: Tuple[str, ...]  # cover "Prepared by" block
    confidentiality_notice: str
    logo_path: Optional[Path]  # None = default logo resolution (CALB)
    logo_required: bool  # True: missing logo file blocks export
    tool_version_label: str
    filename_prefix: str
    version_tag: str
    neutralize_equipment_names: bool
    scrub_terms: Tuple[str, ...]  # brand tokens that must not appear in this variant's output


CALB_BRAND = BrandProfile(
    key="calb",
    display_name="V2.2 (Beta)",
    company_legal_name="CALB Group Co., Ltd.",
    header_title="Confidential Sizing Report (V2.2 Beta)",
    header_lines=(
        "CALB Group Co., Ltd.",
        "Utility-Scale Energy Storage Systems",
        "Confidential Sizing Report (V2.2 Beta)",
    ),
    footer_lines=(),
    cover_title="CALB Utility-Scale ESS Sizing Report (V2.2 Beta)",
    issuer_lines=(
        "Prepared by: CALB Group Co., Ltd.",
        "Utility-Scale Energy Storage Systems",
    ),
    confidentiality_notice=_confidentiality_notice("CALB Group Co., Ltd."),
    logo_path=None,
    logo_required=False,
    tool_version_label="V2.2 Beta",
    filename_prefix="CALB",
    version_tag="V2.2",
    neutralize_equipment_names=False,
    scrub_terms=("Guoxia", "GUOXIA", "Hanchu", "HANCHU"),
)

GUOXIA_BRAND = BrandProfile(
    key="guoxia",
    display_name="V2.2 (Guoxia)",
    company_legal_name="Guoxia Technology Co., Ltd.",
    header_title="Confidential Sizing Report (V2.2 Guoxia)",
    header_lines=(
        "Guoxia Technology Co., Ltd.",
        "HKEX: 02655 (GUOXIA TECH)",
        "Confidential Sizing Report (V2.2 Guoxia)",
    ),
    footer_lines=(
        "(c) 2026 Guoxia Technology Co., Ltd. All rights reserved.",
        "HKEX: 02655 (GUOXIA TECH) | Document Classification: Confidential",
    ),
    cover_title="Guoxia Technology Utility-Scale ESS Sizing Report (V2.2)",
    issuer_lines=(
        "Prepared by: Guoxia Technology Co., Ltd.",
        "HKEX: 02655 (GUOXIA TECH)",
    ),
    confidentiality_notice=_confidentiality_notice("Guoxia Technology Co., Ltd."),
    # Dual-brand (Guoxia Technology + HANCHU ESS) horizontal logo.
    logo_path=PROJECT_ROOT / "GUOXIA-LOGO2.png",
    logo_required=True,
    tool_version_label="V2.2 Guoxia",
    filename_prefix="GUOXIA",
    version_tag="V2.2-GUOXIA",
    neutralize_equipment_names=True,
    scrub_terms=("CALB",),
)

BRAND_PROFILES = {profile.display_name: profile for profile in (CALB_BRAND, GUOXIA_BRAND)}


def require_brand_assets(brand: BrandProfile) -> None:
    """Raise BrandAssetMissingError if a mandatory brand asset is absent."""
    if brand.logo_required:
        if brand.logo_path is None or not Path(brand.logo_path).exists():
            raise BrandAssetMissingError(
                f"Brand '{brand.display_name}' requires logo file "
                f"'{brand.logo_path}', which was not found. Export blocked: "
                "white-label reports must not fall back to the default logo."
            )


def neutralize_equipment_text(value, brand: BrandProfile) -> str:
    """Scrub supplier brand tokens from equipment codes/names for white-label output.

    'CALB_5MWh_20FT_12R' -> '5MWh_20FT_12R';
    'CALB 5MWh 20ft Container - 12 Racks' -> '5MWh 20ft Container - 12 Racks'.
    Returns the original text unchanged for profiles that do not neutralize.
    """
    return neutralize_brand_text(value, brand, fallback="Unbranded equipment")


def _term_pattern(term: str) -> re.Pattern[str]:
    # ``\b`` does not split ``CALB_5MWh`` because underscore is a word
    # character. The explicit letter guards cover spaces, underscores and
    # punctuation while leaving an unrelated word such as ``SCALB`` intact.
    return re.compile(
        rf"(?<![A-Za-z]){re.escape(term)}(?![A-Za-z])[ _-]*",
        flags=re.IGNORECASE,
    )


def _brand_terms_in_text(value: Any, brand: BrandProfile) -> list[str]:
    text = "" if value is None else str(value)
    return [term for term in brand.scrub_terms if _term_pattern(term).search(text)]


def neutralize_brand_text(
    value: Any,
    brand: BrandProfile,
    *,
    fallback: str = "Unbranded",
) -> str:
    """Return customer-visible text with the other publisher's tokens removed.

    This is an output alias only. It never edits the stored project, case or
    product identity. If the whole value is a forbidden token, a neutral label
    is returned instead of reintroducing the original token.
    """
    if value is None:
        return ""
    original = str(value)
    if not brand.neutralize_equipment_names:
        return original
    if not _brand_terms_in_text(original, brand):
        return original

    text = original
    for term in brand.scrub_terms:
        text = _term_pattern(term).sub("", text)
    cleaned = text.strip(" _-")
    return cleaned if cleaned else fallback


def neutralize_brand_payload(value: Any, brand: BrandProfile) -> Any:
    """Copy a report payload while neutralizing every customer-visible string."""
    if not brand.neutralize_equipment_names:
        return value
    if isinstance(value, str):
        return neutralize_brand_text(value, brand)
    if isinstance(value, Mapping):
        return {key: neutralize_brand_payload(item, brand) for key, item in value.items()}
    if isinstance(value, list):
        return [neutralize_brand_payload(item, brand) for item in value]
    if isinstance(value, tuple):
        return tuple(neutralize_brand_payload(item, brand) for item in value)
    if isinstance(value, set):
        return {neutralize_brand_payload(item, brand) for item in value}

    # Stage 2/3 tables are pandas objects, but keep this module import-light and
    # detect them locally. Only string cells are aliases; numeric engineering
    # values and dtypes remain unchanged.
    try:
        import pandas as pd

        if isinstance(value, pd.DataFrame):
            result = value.copy(deep=True)
            for column in result.columns:
                result[column] = result[column].map(
                    lambda item: neutralize_brand_text(item, brand)
                    if isinstance(item, str)
                    else item
                )
            return result
        if isinstance(value, pd.Series):
            return value.map(
                lambda item: neutralize_brand_text(item, brand)
                if isinstance(item, str)
                else item
            )
    except ImportError:
        pass
    return value


_HUMAN_XML_ATTRIBUTES = {
    "alt",
    "description",
    "descr",
    "label",
    "name",
    "title",
}


def neutralize_svg_visible_text(svg_bytes: bytes, brand: BrandProfile) -> bytes:
    """Neutralize visible SVG text before a white-label figure is rasterized."""
    if not brand.neutralize_equipment_names:
        return svg_bytes
    try:
        root = ET.fromstring(svg_bytes)
    except (ET.ParseError, ValueError) as exc:
        raise BrandLeakError(
            f"Brand-safe export requires a readable SVG source ({exc})."
        ) from exc

    for element in root.iter():
        local_tag = element.tag.rsplit("}", 1)[-1].lower()
        # CSS selectors and script identifiers are implementation details, not
        # customer-visible copy. Rewriting them can disconnect a selector from
        # its class/id and damage the figure.
        if element.text and local_tag not in {"style", "script"}:
            element.text = neutralize_brand_text(element.text, brand)
        if element.tail:
            element.tail = neutralize_brand_text(element.tail, brand, fallback="")
        for attr_name, attr_value in list(element.attrib.items()):
            local_name = attr_name.rsplit("}", 1)[-1].lower()
            if local_name in _HUMAN_XML_ATTRIBUTES:
                element.attrib[attr_name] = neutralize_brand_text(attr_value, brand)
    return ET.tostring(root, encoding="utf-8")


def assert_brand_clean_docx(report_bytes: bytes, brand: BrandProfile) -> None:
    """Fail closed if a generated DOCX still exposes another publisher brand.

    Every textual OOXML/SVG part is parsed so body copy, headers, footers,
    document properties and accessibility labels are covered without mistaking
    relationship IDs or internal element IDs for visible branding. Raster
    figures are controlled earlier by requiring and sanitizing their SVG source.
    """
    if not brand.neutralize_equipment_names or not brand.scrub_terms:
        return

    leaks: list[str] = []
    try:
        with zipfile.ZipFile(io.BytesIO(report_bytes)) as archive:
            for name in archive.namelist():
                if not name.lower().endswith((".xml", ".rels", ".svg")):
                    continue
                payload = archive.read(name)
                try:
                    root = ET.fromstring(payload)
                except ET.ParseError:
                    text_values = [payload.decode("utf-8", errors="replace")]
                else:
                    text_values = []
                    for element in root.iter():
                        local_tag = element.tag.rsplit("}", 1)[-1].lower()
                        if element.text and local_tag not in {"style", "script"}:
                            text_values.append(element.text)
                        if element.tail:
                            text_values.append(element.tail)
                        for attr_name, attr_value in element.attrib.items():
                            local_name = attr_name.rsplit("}", 1)[-1].lower()
                            if local_name in _HUMAN_XML_ATTRIBUTES:
                                text_values.append(attr_value)
                for text_value in text_values:
                    for term in _brand_terms_in_text(text_value, brand):
                        leaks.append(f"{name}: {term}")
                        if len(leaks) >= 5:
                            break
                    if len(leaks) >= 5:
                        break
                if len(leaks) >= 5:
                    break
    except (zipfile.BadZipFile, OSError) as exc:
        raise BrandLeakError(f"Generated report package could not be audited ({exc}).") from exc

    if leaks:
        raise BrandLeakError(
            "White-label report blocked because forbidden brand text remains: "
            + "; ".join(leaks)
        )
