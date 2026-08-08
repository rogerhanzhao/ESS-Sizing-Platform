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

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

from calb_sizing_tool.config import PROJECT_ROOT


class BrandAssetMissingError(RuntimeError):
    """A required brand asset (e.g. logo file) is missing; export must not proceed.

    White-label exports must never fall back to another brand's assets.
    """


def _confidentiality_notice(owner: str) -> str:
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
    if value is None:
        return ""
    original = str(value)
    text = original
    if not brand.neutralize_equipment_names:
        return text
    for term in brand.scrub_terms:
        # \b fails on 'CALB_5MWh' (underscore is a word char), so use explicit
        # letter lookarounds and swallow trailing separators.
        text = re.sub(
            rf"(?<![A-Za-z]){re.escape(term)}(?![A-Za-z])[ _-]*",
            "",
            text,
            flags=re.IGNORECASE,
        )
    cleaned = text.strip(" _-")
    return cleaned if cleaned else original
