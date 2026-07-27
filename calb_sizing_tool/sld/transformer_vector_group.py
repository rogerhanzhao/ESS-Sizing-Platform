"""Strict transformer vector-group parsing for the AC-to-SLD contract.

The vector group is an electrical declaration, not display text.  Its number
of LV tokens must equal the number of independently drawn LV windings. It does
not declare neutral earthing; that requires separate protection-design data.
"""
from __future__ import annotations

from dataclasses import dataclass
import re


class TransformerVectorGroupError(ValueError):
    """Raised when a vector group cannot truthfully describe the LV topology."""


@dataclass(frozen=True)
class TransformerVectorGroup:
    hv_token: str
    lv_tokens: tuple[str, ...]


_HV_TOKEN = re.compile(r"^(ZN|YN|Z|Y|D)")
_LV_TOKEN = re.compile(r"(zn|yn|z|y|d)(\d{0,2})")
_SEPARATOR = re.compile(r"^[\s\-/,;]*$")


def parse_transformer_vector_group(
    value: str,
    *,
    lv_winding_count: int,
) -> TransformerVectorGroup:
    """Parse a complete IEC-style vector group for an exact LV winding count.

    Examples: ``Dyn11`` for one LV winding, ``Dy11y11`` (or ``Dy11-y11``)
    for two independent LV windings, and ``YNd11y0`` for a delta plus a wye
    secondary. A single LV token is intentionally *not*
    copied to multiple independent windings.
    """
    if lv_winding_count < 1:
        raise TransformerVectorGroupError("lv_winding_count must be at least 1.")

    raw = str(value or "").strip()
    if not raw:
        raise TransformerVectorGroupError("transformer vector group is missing.")

    hv_match = _HV_TOKEN.match(raw)
    if not hv_match:
        raise TransformerVectorGroupError(f"invalid transformer HV token in {raw!r}.")
    hv_token = hv_match.group(1)
    remainder = raw[hv_match.end():]
    cursor = 0
    lv_tokens: list[str] = []
    for match in _LV_TOKEN.finditer(remainder):
        if not _SEPARATOR.fullmatch(remainder[cursor:match.start()]):
            raise TransformerVectorGroupError(f"invalid transformer vector-group syntax: {raw!r}.")
        lv_tokens.append(match.group(1) + match.group(2))
        cursor = match.end()
    if not lv_tokens or not _SEPARATOR.fullmatch(remainder[cursor:]):
        raise TransformerVectorGroupError(f"invalid transformer vector-group syntax: {raw!r}.")
    if len(lv_tokens) != lv_winding_count:
        raise TransformerVectorGroupError(
            f"transformer vector group {raw!r} declares {len(lv_tokens)} LV winding(s), "
            f"but the AC topology requires {lv_winding_count}."
        )
    return TransformerVectorGroup(hv_token=hv_token, lv_tokens=tuple(lv_tokens))
