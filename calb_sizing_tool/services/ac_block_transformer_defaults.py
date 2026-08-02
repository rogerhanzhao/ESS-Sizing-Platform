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

"""Normalize AC Block product transformer fields (topology / vector group / LV
arrangement).

Product datasheets carry a transformer vector group; from it the winding count,
transformer topology and LV busbar arrangement are *derived* deterministically
(non-fabricating). Where a datasheet states none of these, a conservative
standard default is applied — a single LV winding (`Dyn11`,
`common_single_lv_busbar`), never a PCS-count-based three-winding guess (that
guess is explicitly disallowed; the operator selects the secondary arrangement).
Every filled value carries a ``*_basis`` marker so downstream code and reviewers
can tell a datasheet value from a derived one from an assumed default.

Basis values:
- ``datasheet`` — stated by the vendor datasheet.
- ``derived_from_vector_group`` — computed from the datasheet vector group.
- ``standard_default_pending_confirmation`` — assumed; requires owner/OEM
  confirmation before use as a formal engineering result.
- ``unconfirmed`` — the datasheet value is ambiguous and could not be parsed.
"""

from __future__ import annotations

from typing import Any

from calb_sizing_tool.sld.transformer_vector_group import (
    TransformerVectorGroupError,
    parse_transformer_vector_group,
)

STANDARD_DEFAULT_VECTOR_GROUP: dict[int, str] = {1: "Dyn11", 2: "Dyn11yn11"}
STANDARD_LV_ARRANGEMENT: dict[int, str] = {
    1: "common_single_lv_busbar",
    2: "independent_lv_busbars",
}

BASIS_DATASHEET = "datasheet"
BASIS_DERIVED = "derived_from_vector_group"
BASIS_DEFAULT = "standard_default_pending_confirmation"
BASIS_UNCONFIRMED = "unconfirmed"


def standard_default_vector_group(lv_winding_count: int) -> str:
    """Standard IEC vector group for an already-decided LV winding count.

    The group must declare exactly ONE LV token per independent LV winding — the
    formal-readiness gate parses it against ``lv_winding_count``. The authoritative
    input only admits 1 or 2 windings, but do NOT fall back to a fixed two-LV
    string for anything else: that returns a group whose arity silently
    contradicts the topology. Generate the matching arity instead.
    """
    count = max(1, int(lv_winding_count))
    known = STANDARD_DEFAULT_VECTOR_GROUP.get(count)
    if known is not None:
        return known
    return "Dyn11" + "yn11" * (count - 1)


def standard_lv_arrangement(lv_winding_count: int) -> str:
    return STANDARD_LV_ARRANGEMENT.get(max(1, int(lv_winding_count)), "independent_lv_busbars")


def _lv_token_count(vector_group: Any) -> int | None:
    """LV token count of a vector group, or None if it cannot be parsed."""
    text = str(vector_group or "").strip()
    if not text:
        return None
    for candidate in (1, 2, 3):
        try:
            parsed = parse_transformer_vector_group(text, lv_winding_count=candidate)
        except TransformerVectorGroupError:
            continue
        return len(parsed.lv_tokens)
    return None


def normalize_ac_product_transformer_fields(metadata: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of the product metadata with topology / vector group / LV
    arrangement filled and each source recorded via a ``*_basis`` marker.

    Never overwrites a stated datasheet value; derives from the vector group when
    it parses; falls back to a conservative single-LV-winding default otherwise.
    """
    out = dict(metadata or {})
    vector_group = out.get("transformer_vector_group")
    topology = out.get("transformer_topology")
    lv_count = _lv_token_count(vector_group)

    if lv_count is not None:
        # Real, parseable datasheet vector group — derive the rest from it.
        out.setdefault("lv_winding_count", lv_count)
        out.setdefault("transformer_vector_group_basis", BASIS_DATASHEET)
        if not topology:
            out["transformer_topology"] = "two_winding" if lv_count == 1 else "three_winding"
            out["transformer_topology_basis"] = BASIS_DERIVED
        else:
            out.setdefault("transformer_topology_basis", BASIS_DATASHEET)
        if not out.get("lv_arrangement"):
            out["lv_arrangement"] = standard_lv_arrangement(lv_count)
            out["lv_arrangement_basis"] = BASIS_DERIVED
        return out

    if vector_group:
        # Ambiguous datasheet text (e.g. "Dy1 or Dy11"): do not fabricate — flag
        # for confirmation and leave the values as stated.
        out.setdefault("transformer_vector_group_basis", BASIS_UNCONFIRMED)
        out.setdefault("transformer_topology_basis", BASIS_UNCONFIRMED)
        out.setdefault("lv_arrangement_basis", BASIS_UNCONFIRMED)
        return out

    # Nothing stated: conservative standard default. Honour an explicit topology
    # if present; otherwise assume a single LV winding (two-winding) — never a
    # PCS-count-based three-winding guess.
    if topology in ("two_winding", "three_winding"):
        lv = 1 if topology == "two_winding" else 2
        out.setdefault("transformer_topology_basis", BASIS_DATASHEET)
    else:
        lv = 1
        out["transformer_topology"] = "two_winding"
        out["transformer_topology_basis"] = BASIS_DEFAULT
    out["lv_winding_count"] = lv
    out["transformer_vector_group"] = standard_default_vector_group(lv)
    out["transformer_vector_group_basis"] = BASIS_DEFAULT
    out["lv_arrangement"] = standard_lv_arrangement(lv)
    out["lv_arrangement_basis"] = BASIS_DEFAULT
    return out


__all__ = [
    "STANDARD_DEFAULT_VECTOR_GROUP",
    "STANDARD_LV_ARRANGEMENT",
    "BASIS_DATASHEET",
    "BASIS_DERIVED",
    "BASIS_DEFAULT",
    "BASIS_UNCONFIRMED",
    "standard_default_vector_group",
    "standard_lv_arrangement",
    "normalize_ac_product_transformer_fields",
]
