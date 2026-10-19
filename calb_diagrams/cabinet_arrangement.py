"""Symbolic cabinet Block Arrangement, isolated from controlled container geometry.

Coordinates in this module are page-layout units, never physical dimensions.
Equipment membership is authoritative; footprints, orientation and required
clearances remain unknown. This renderer cannot estimate a site envelope.
"""

from __future__ import annotations

import math
import json
import re
from html import escape
from typing import Any, Mapping

from calb_diagrams.cabinet_sld import render_cabinet_sld


RENDERER_VERSION = "cabinet-arrangement-concept-v1"
_PAGE_W, _PAGE_H = 1680, 1188
_WARNINGS = [
    "CONCEPT / NOT FOR CONSTRUCTION. Symbol positions show relative equipment zones only.",
    "NOT TO SCALE / NO SITE AREA ESTIMATE. Cabinet, PCS and station footprints are not confirmed.",
    "Service, isolation, replacement and emergency access reserves have no confirmed width or orientation.",
    "Fire separation, cable routes, cooling, drainage, earthing, civil works and local rule compliance require project design.",
    "Transformer / MV station may be separate or integrated; its architecture and physical interfaces remain TBC.",
]


def _validated_installation_basis(basis: Mapping[str, Any] | None) -> dict | None:
    if basis is None:
        return None
    if (not isinstance(basis, Mapping) or basis.get("status") not in {"unverified", "documented"}
            or "cabinet_dimensions_mm" not in basis
            or not isinstance(basis.get("clearances"), list)
            or not isinstance(basis.get("notes"), list)
            or any(not isinstance(note, str) for note in basis["notes"])):
        raise ValueError("Installation basis must contain status, cabinet_dimensions_mm, clearances and notes")
    dimensions = basis["cabinet_dimensions_mm"]
    if dimensions is not None:
        if not isinstance(dimensions, Mapping) or set(dimensions) != {"width", "depth", "height"}:
            raise ValueError("Installation basis cabinet dimensions require width, depth and height in mm")
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0
               for v in dimensions.values()):
            raise ValueError("Installation basis cabinet dimensions must be finite and positive")
    if basis["status"] == "documented" and dimensions is not None:
        source = basis.get("dimension_source")
        if (not isinstance(source, Mapping) or not isinstance(source.get("source_title"), str)
                or not source["source_title"].strip() or type(source.get("page")) is not int or source["page"] < 1
                or ("revision" in source and not isinstance(source["revision"], str))):
            raise ValueError("Installation basis documented dimensions require dimension_source title and page")
        if re.match(r"^(?:[A-Za-z]:[\\/]|[\\/]|file:)", source["source_title"].strip(), re.IGNORECASE):
            raise ValueError("Installation basis dimension_source must identify a document title, not a local path")
    for ref in basis["clearances"]:
        if (not isinstance(ref, Mapping) or not isinstance(ref.get("relation"), str) or not ref["relation"].strip()
                or ref.get("evidence_kind") not in {"manufacturer_requirement", "test_configuration"}
                or not isinstance(ref.get("source_title"), str) or not ref["source_title"].strip()
                or type(ref.get("page")) is not int or ref["page"] < 1
                or not isinstance(ref.get("conditions"), (str, list))):
            raise ValueError("Installation basis clearances require relation, evidence kind, source, page and conditions")
        value = ref.get("value_mm")
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise ValueError("Installation basis clearance values must be finite non-negative mm")
    if basis["status"] == "documented" and dimensions is None and not basis["clearances"]:
        raise ValueError("Installation basis documented status requires dimensional or clearance evidence")
    try:
        # A detached JSON copy keeps source evidence intact without mutating a
        # caller object. No dimension or clearance default is fabricated here.
        return json.loads(json.dumps(dict(basis), allow_nan=False))
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("Installation basis must be finite JSON-serializable evidence") from exc


def _schedule(output: Mapping[str, Any], validated_sld: dict, installation_basis: dict | None) -> dict:
    plan = output["cabinet_group_contract"]
    blocks = []
    for summary in validated_sld["topology"]["ac_blocks"]:
        index = summary["ac_block_index"]
        row = output["ac_block_rows"][index - 1]
        groups = sorted((g for g in plan["groups"] if g["ac_block_index"] == index),
                        key=lambda g: g["pcs_index"])
        blocks.append(dict(
            ac_block_index=index, cabinet_count=summary["cabinet_count"],
            group_count=len(groups), pcs_count=summary["pcs_count"],
            nameplate_mwh=summary["nameplate_mwh"], pcs_nameplate_mw=summary["pcs_nameplate_mw"],
            pcs_unit_kw=float(row["pcs_kw"]),
            groups=[dict(group_index=g["group_index"], cabinet_indices=list(g["cabinet_indices"]),
                         cabinet_count=g["cabinet_count"], nameplate_mwh=g["nameplate_mwh"],
                         pcs_index=g["pcs_index"], pcs_label=f"PCS {index:02d}-{g['pcs_index']:02d}")
                    for g in groups],
            reserved_zones=[
                dict(kind="service_isolation_and_replacement", dimensions=None, orientation=None),
                dict(kind="cable_route_and_interfaces", dimensions=None, route=None),
                dict(kind="transformer_mv_station_interface", dimensions=None, station_type=None),
            ],
        ))
    return dict(
        renderer_version=RENDERER_VERSION, contract_version=plan["contract_version"],
        document_status="concept", physical_cabinet_count=plan["physical_cabinet_count"],
        total_nameplate_mwh=plan["total_nameplate_mwh"], ac_block_count=len(blocks),
        group_count_total=len(plan["groups"]), pcs_count_total=sum(b["pcs_count"] for b in blocks),
        maximum_cabinets_per_group=plan["cabinet_group_max_count"],
        dimensions_confirmed=False, clearances_confirmed=False,
        equipment_orientation_confirmed=False, fire_separation_verified=False,
        station_type=None, site_area_m2=None, equipment_footprints=None,
        geometry_basis="symbolic_page_positions_only", installation_basis=installation_basis,
        cabinet_dimensions_documented=bool(installation_basis and installation_basis["status"] == "documented"
                                          and installation_basis["cabinet_dimensions_mm"] is not None),
        dimension_source=installation_basis.get("dimension_source") if installation_basis else None,
        ac_blocks=blocks,
    )


def _page_svg(block: dict, project_name: str, total_blocks: int, installation_basis: dict | None = None) -> str:
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="420mm" height="297mm" viewBox="0 0 {_PAGE_W} {_PAGE_H}">',
             '<style>text{font-family:Arial,sans-serif;fill:#193c57}.muted{fill:#546c7c}.warn{fill:#94480e}</style>',
             '<rect width="1680" height="1188" fill="white"/>',
             '<rect x="28" y="28" width="1624" height="1132" fill="none" stroke="#193c57" stroke-width="2"/>']

    def text(x, y, value, size=16, **attrs):
        options = " ".join(f'{escape(k, quote=True)}="{escape(str(v), quote=True)}"' for k, v in attrs.items())
        parts.append(f'<text x="{x:g}" y="{y:g}" font-size="{size}" {options}>{escape(str(value))}</text>')

    def rect(x, y, width, height, **attrs):
        options = " ".join(f'{escape(k, quote=True)}="{escape(str(v), quote=True)}"' for k, v in attrs.items())
        parts.append(f'<rect x="{x:g}" y="{y:g}" width="{width:g}" height="{height:g}" {options}/>')

    index, groups = block["ac_block_index"], block["groups"]
    basis_supplied = bool(installation_basis and installation_basis["status"] == "documented")
    name = " ".join(str(project_name).split())
    text(55, 68, "CALB  |  CABINET CONCEPT BLOCK ARRANGEMENT", 25, **{"font-weight": "bold"})
    text(55, 100, f"Project: {name[:125]}" + ("..." if len(name) > 125 else ""), 17)
    text(55, 132, f"AC Block {index} / {total_blocks}  |  {block['cabinet_count']} cabinets  |  "
         f"{block['group_count']} independent groups / {block['pcs_count']} PCS  |  {block['nameplate_mwh']:.3f} MWh DC nameplate", 18)
    dimensions = installation_basis["cabinet_dimensions_mm"] if basis_supplied else None
    if dimensions is not None:
        dimension_text = " x ".join(f"{dimensions[key]:g}" for key in ("width", "depth", "height"))
        basis_line = f"Documented cabinet W x D x H: {dimension_text} mm. SYMBOLIC POSITIONS - project access / station geometry remain TBC."
    elif basis_supplied:
        basis_line = "Relative equipment zones only. Documented clearance evidence is referenced; remaining interfaces require confirmation."
    else:
        basis_line = "Equipment grouping and relative zones only. Footprints, access sides and all clearances: TBC."
    text(55, 160, basis_line, 16)
    if dimensions is not None:
        source = installation_basis["dimension_source"]
        source_title = " ".join(source["source_title"].split())
        source_title = source_title[:100] + ("..." if len(source_title) > 100 else "")
        revision = " ".join(source.get("revision", "").split())
        revision = revision[:20] + ("..." if len(revision) > 20 else "")
        reference = f"Dimension source: {source_title}, p. {source['page']}" + (f", rev. {revision}" if revision else "")
        text(55, 179, reference, 11, **{"id": "dimension-source-reference", "class": "muted"})
    text(55, 199 if dimensions is not None else 190,
         "BLUE = cabinet symbols   |   GREEN = PCS zone   |   R = cable/interface reserve   |   GREY = service reserve", 14)

    columns = 1 if len(groups) == 1 else 2
    rows = math.ceil(len(groups) / columns)
    gap = 20 if rows < 4 else 16
    card_w = 1120 if columns == 1 else 773
    card_h = (660 - (rows - 1) * gap) / rows
    compact = card_h < 190

    for position, group in enumerate(groups):
        x = 55 + (position % columns) * (card_w + 24)
        y = 210 + (position // columns) * (card_h + gap)
        gid, pcs = group["group_index"], group["pcs_label"]
        rect(x, y, card_w, card_h, fill="#f5f9fc", stroke="#7798b1", rx=5,
             id=f"group-{gid}-boundary", **{"data-kind": "group_boundary", "data-group-index": gid})
        text(x + 18, y + (22 if compact else 31), f"GROUP {gid:02d}  /  {pcs}",
             16 if compact else 22, **{"font-weight": "bold"})
        text(x + 18, y + (41 if compact else 55),
             f"{group['cabinet_count']} x 418 kWh  |  {group['nameplate_mwh']:.3f} MWh  |  "
             + ("installation evidence referenced" if basis_supplied else "footprints / spacing TBC"),
             12 if compact else 15)

        header_h = 50 if compact else 75
        service_h = 22 if compact else 48
        service_y = y + card_h - (30 if compact else 78)
        body_y = y + header_h
        body_h = service_y - body_y - 10
        side_w = 148 if card_w < 1000 else 205
        battery_x = x + 18
        battery_w = card_w - side_w - 65
        desired_cols = 6 if compact or card_w > 1000 else 4
        cabinet_cols = min(desired_cols, group["cabinet_count"])
        cabinet_rows = math.ceil(group["cabinet_count"] / cabinet_cols)
        tile_w = min(140, (battery_w - (cabinet_cols - 1) * 8) / cabinet_cols)
        tile_h = min(115, (body_h - (cabinet_rows - 1) * 8) / cabinet_rows)
        grid_w = cabinet_cols * tile_w + (cabinet_cols - 1) * 8
        grid_h = cabinet_rows * tile_h + (cabinet_rows - 1) * 8
        grid_x = battery_x + (battery_w - grid_w) / 2
        grid_y = body_y + (body_h - grid_h) / 2
        for tile, cabinet in enumerate(group["cabinet_indices"]):
            cx = grid_x + (tile % cabinet_cols) * (tile_w + 8)
            cy = grid_y + (tile // cabinet_cols) * (tile_h + 8)
            rect(cx, cy, tile_w, tile_h, fill="#e5f0f9", stroke="#476d8f", rx=2,
                 id=f"cabinet-{cabinet}", **{"data-kind": "cabinet", "data-group-index": gid})
            label_size = 11 if compact else (18 if tile_h > 75 else 14)
            label_y = cy + tile_h / 2 + (4 if compact or tile_h < 42 else -5)
            text(cx + tile_w / 2, label_y, f"C{cabinet:03d}", label_size,
                 **{"text-anchor": "middle", "font-weight": "bold"})
            if not compact and tile_h >= 42:
                text(cx + tile_w / 2, label_y + 21, "418 kWh", 13 if tile_h > 75 else 11,
                     **{"text-anchor": "middle"})

        reserve_x = battery_x + battery_w + 9
        rect(reserve_x, body_y, 18, body_h, fill="#f5e9c8", stroke="#c1a45d",
             id=f"group-{gid}-cable-reserve", **{"data-kind": "cable_reserve", "data-group-index": gid})
        text(reserve_x + 9, body_y + 14, "R", 11, **{"text-anchor": "middle"})
        pcs_x = reserve_x + 29
        pcs_h = min(185, body_h)
        pcs_y = body_y + (body_h - pcs_h) / 2
        rect(pcs_x, pcs_y, side_w, pcs_h, fill="#e5f2eb", stroke="#598271", rx=3,
             id=f"ac-{index}-pcs-{group['pcs_index']}-zone",
             **{"data-kind": "pcs_zone", "data-group-index": gid})
        pcs_center = pcs_y + pcs_h / 2
        text(pcs_x + side_w / 2, pcs_center - (6 if compact else 22), pcs,
             13 if compact else 18, **{"text-anchor": "middle", "font-weight": "bold"})
        text(pcs_x + side_w / 2, pcs_center + (12 if compact else 5), f"{block['pcs_unit_kw']:g} kW",
             12 if compact else 16, **{"text-anchor": "middle"})
        if not compact:
            text(pcs_x + side_w / 2, pcs_center + 32, "Footprint: TBC", 13, **{"text-anchor": "middle"})

        rect(x + 18, service_y, card_w - 36, service_h, fill="#e8edf1", stroke="#a5b5c1",
             id=f"group-{gid}-service-reserve", **{"data-kind": "service_reserve", "data-group-index": gid})
        text(x + 29, service_y + (15 if compact else 29),
             "Service / replacement reserve - confirm project access and clearance"
             if basis_supplied else
             "Service / isolation / replacement reserve - access side and clearance TBC",
             11 if compact else 15)
        if not compact:
            text(x + 18, y + card_h - 11, "Cabinet doors, HV box and cooling access orientation: TBC", 13,
                 **{"class": "muted"})

    if columns == 1:
        # A single group does not need an enormous empty equipment symbol.
        # Use the remainder for constructability inputs still needed to design it.
        px, py, pw, ph = 1199, 210, 426, 660
        rect(px, py, pw, ph, fill="#fafbfc", stroke="#b4c1ca", rx=4, id="open-layout-inputs")
        text(px + 20, py + 34, "LAYOUT INPUTS TO CONFIRM", 19, **{"font-weight": "bold"})
        notes = [
            ("Equipment footprints", "Cabinet / PCS / station dimensions: TBC"),
            ("Operation and replacement", "Door swing, HV access and withdrawal: TBC"),
            ("Safety and emergency access", "Fire basis, isolation and access route: TBC"),
            ("Installation interfaces", "Cable, cooling, drainage and earth: TBC"),
            ("Transformer / MV station", "Separate or integrated equipment: TBC"),
            ("Project constraints", "Site boundary, levels and authority basis: TBC"),
        ]
        for line, (heading, description) in enumerate(notes):
            text(px + 20, py + 94 + line * 87, heading, 17, **{"font-weight": "bold"})
            text(px + 20, py + 120 + line * 87, description, 13)

    rect(55, 890, 1570, 80, fill="#f8f0e3", stroke="#bfa57d", rx=4,
         id=f"ac-{index}-transformer-mv-reserve", **{"data-kind": "transformer_mv_reserve"})
    text(75, 919, "TRANSFORMER / MV INTERFACE RESERVE - station type, footprint and equipment separation: TBC", 18,
         **{"font-weight": "bold"})
    text(75, 947, "Separate or integrated station: TBC. Auxiliary, fire, drainage and earthing interfaces require project coordination.", 15)
    rect(55, 988, 1570, 60, fill="#fff3e2", stroke="#d9ac6c")
    text(74, 1014, "CONCEPT / NOT FOR CONSTRUCTION", 22, **{"font-weight": "bold", "class": "warn"})
    text(74, 1037, "NOT TO SCALE / NO SITE AREA ESTIMATE - no equipment dimensions or minimum clearances are implied.", 16,
         **{"class": "warn"})
    text(55, 1079, "Group outlines show saved electrical membership, not fire compartments. Relative positions are illustrative, not an approved installation.", 15)
    text(55, 1106,
         ("Clearance evidence retained in schedule: TEST SETUP / NOT INSTALLATION MINIMUM. Project design remains required."
          if any(ref["evidence_kind"] == "test_configuration" for ref in installation_basis["clearances"])
          else "Documented installation basis retained in schedule. No scaled geometry, project clearance or site fit is certified.")
         if basis_supplied else
         "One intact independent cabinet group is assigned to one PCS. No cable, busbar, civil, fire or earthing design is shown.", 15)
    text(55, 1135, f"{RENDERER_VERSION}  |  Sheet {index}/{total_blocks}  |  Symbolic equipment zones only", 13)
    parts.append("</svg>")
    return "".join(parts)


def render_cabinet_arrangement(ac_output: Mapping[str, Any], project_name: str = "CALB ESS Project",
                               installation_basis: Mapping[str, Any] | None = None) -> dict:
    """Return concept pages, a physical membership schedule, and English warnings.

    The existing cabinet SLD validation owns the authoritative count, energy and
    AC/PCS assignment checks. No sizing, allocation or physical-spacing rule is
    reimplemented here. Optional installation evidence carries ``status``
    (``unverified`` or ``documented``), ``cabinet_dimensions_mm``, ``clearances``
    and ``notes``. Documented dimensions additionally require a document title
    and page in ``dimension_source``. Only documented values may be annotated;
    test configurations never become installation minima or scaled geometry.
    Invalid inputs raise before any page is returned.
    """
    validated = render_cabinet_sld(ac_output, project_name=project_name)
    basis = _validated_installation_basis(installation_basis)
    schedule = _schedule(ac_output, validated, basis)
    pages = [dict(ac_block_index=block["ac_block_index"],
                  svg=_page_svg(block, project_name, schedule["ac_block_count"], basis))
             for block in schedule["ac_blocks"]]
    warnings = list(_WARNINGS)
    if basis and basis["status"] == "documented":
        warnings[1] = "NOT TO SCALE / NO SITE AREA ESTIMATE. Documented installation evidence is retained separately from symbolic equipment positions."
        if any(ref["evidence_kind"] == "test_configuration" for ref in basis["clearances"]):
            warnings.append("TEST SETUP / NOT INSTALLATION MINIMUM. A tested equipment separation is not automatically an installation requirement.")
    return dict(pages=pages, schedule=schedule, warnings=warnings)
