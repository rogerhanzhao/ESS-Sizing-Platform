"""Select an immutable visual pair for an already-resolved typical arrangement.

This module never sizes equipment or chooses a layout engine. Uncovered products,
spacing profiles and missing/corrupt assets fall back to the existing drawing.
"""
from __future__ import annotations

import hashlib
import json
import math
import secrets
from dataclasses import asdict, dataclass
from pathlib import Path

from calb_diagrams.typical_ac_block_arrangement import arrangement_equipment_placements

ASSET_ROOT = Path(__file__).parent / "assets" / "layout_renders" / "v1"
NEUTRAL_ASSET_ROOT = ASSET_ROOT.parent / "neutral_v1"
OBLIQUE_VIEWS = ("SW", "SE", "NE", "NW")


@dataclass(frozen=True)
class RenderPair:
    template_id: str
    version: str
    oblique_view: str
    top_png: bytes
    oblique_png: bytes
    orientation_note: str = ""


def placement_signature(arrangement, profile):
    fields = ("x_m", "y_m", "width_m", "height_m", "door_orientation", "equipment_end")
    return [dict(kind="ac" if p["equipment_type"] == "ac_station" else "dc",
                 **{k: round(p[k], 6) if isinstance(p.get(k), (float, int)) else p.get(k)
                    for k in fields})
            for p in arrangement_equipment_placements(arrangement, profile)]


def select_render_pair(ctx, arrangement, profile, *, root=None, choose=None, neutral=False):
    """Return TOP plus one randomly selected oblique, or None for legacy fallback.

Unbound container studies use a representative CALB exterior by geometry.
An explicitly bound AC product needs its exact code in the asset manifest;
same power/length alone never establishes physical product compatibility.

For a mixed AC Block station the arrangement passed in is already the
representative Head block geometry (resolved by _arrangement_shape in
report_v2). The visual template is matched against that Head geometry
exactly as for a uniform station; the tail block(s) are described in
Section 6.1 and are not shown in the arrangement drawing.
Governed multi-group runs still require per-group asset bindings and
continue to fall back to the engineering drawing.
"""
    if arrangement is None or getattr(ctx, "scenario_id", "") != "container_only":
        return None
    try:
        output = ctx.ac_output or {}
        if output.get("governed_ac_groups"):
            return None  # governed multi-group: per-group asset bindings required
        bound = output.get("governed_product_block_code") or output.get("ac_block_product_block_code")
        if getattr(ctx, "configuration_code", None) and not bound:
            return None
        root = Path(root) if root else (NEUTRAL_ASSET_ROOT if neutral else ASSET_ROOT)
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        if neutral and manifest.get("branding") != "neutral":
            return None  # Never substitute branded images for a neutral export.
        signature = placement_signature(arrangement, profile)
        profile_signature = json.loads(json.dumps(asdict(profile)))
        for entry in manifest["templates"]:
            if not entry.get("released"):
                continue
            if bound and bound not in entry.get("bound_product_codes", []):
                continue
            if not bound and not entry.get("allow_unbound_concept", False):
                continue
            if entry["dc_count"] != arrangement.dc_blocks or entry["variant"] != arrangement.layout_variant:
                continue
            if not math.isclose(entry["ac_length_m"], arrangement.station_length_m, abs_tol=1e-6):
                continue
            # Visual templates represent cabinet size and layout, not MW rating.
            if entry["profile"] != profile_signature or entry["source_placements"] != signature:
                continue
            # Verify all five assets before allowing random selection; a damaged view
            # must not create intermittent success depending on the chosen angle.
            images = {}
            for view in ("TOP", *OBLIQUE_VIEWS):
                asset = entry["views"][view]
                path = (root / asset["file"]).resolve()
                if not path.is_relative_to(root.resolve()):
                    return None
                data = path.read_bytes()
                if hashlib.sha256(data).hexdigest() != asset["sha256"]:
                    return None
                images[view] = data
            view = (choose or secrets.choice)(OBLIQUE_VIEWS)
            if view not in OBLIQUE_VIEWS:
                return None
            return RenderPair(entry["id"], manifest["version"], view,
                              images["TOP"], images[view], entry.get("orientation_note", ""))
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return None
    return None
