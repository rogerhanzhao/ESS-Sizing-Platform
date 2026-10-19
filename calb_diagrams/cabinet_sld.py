"""Isolated concept SLD for the approved independent 418 kWh cabinet contract.

This module deliberately does not call or modify the container SLD renderer.
It renders saved physical membership and PCS assignments, not sizing formulas.
All diagrams remain conceptual; a selected transformer topology does not confirm
the equipment, protection, earthing, or a deliverable POI power rating.
"""

from __future__ import annotations

import math
from collections import defaultdict
from html import escape
from typing import Any, Mapping

from calb_sizing_tool.services.cabinet_ac_preview_service import validate_cabinet_contract


RENDERER_VERSION = "cabinet-sld-concept-v1"
_WIDTH, _HEIGHT = 1680, 1188
_BASE_WARNINGS = [
    "CONCEPT / NOT FOR CONSTRUCTION. This is an electrical connection concept, not an installation design.",
    "OEM DC voltage/current limits, cabinet protection, PCS compatibility and transformer ratings remain TBC.",
    "Transformer vector group, grounding, switching and protection are not defined by this drawing.",
    "PCS nameplate power does not establish net deliverable power at the POI.",
]


def _positive_int(value: Any, field: str) -> int:
    if type(value) is not int or value < 1:
        raise ValueError(f"{field} must be a positive integer")
    return value


def _finite_positive(value: Any, field: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{field} must be finite and positive")
    try:
        number = float(value)
    except (ValueError, TypeError, OverflowError) as exc:
        raise ValueError(f"{field} must be finite and positive") from exc
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"{field} must be finite and positive")
    return number


def _same_number(value: Any, expected: float, field: str, tolerance: float = .00051) -> None:
    number = _finite_positive(value, field)
    if not math.isclose(number, expected, rel_tol=0, abs_tol=tolerance):
        raise ValueError(f"{field} conflicts with the saved cabinet group contract")


def _validate_output(output: Mapping[str, Any]) -> tuple[dict, list[dict], dict[int, list[dict]]]:
    if not isinstance(output, Mapping) or output.get("dc_unit_kind") != "independent_cabinet_group":
        raise ValueError("The cabinet SLD requires an independent cabinet group AC output")
    plan = output.get("cabinet_group_contract")
    validate_cabinet_contract(plan, allocated=True)
    _same_number(sum(group["nameplate_mwh"] for group in plan["groups"]),
                 plan["total_nameplate_mwh"], "Summed independent group energy")
    count = _positive_int(output.get("physical_cabinet_count"), "Physical cabinet count")
    if count != plan["physical_cabinet_count"]:
        raise ValueError("Physical cabinet count conflicts with the saved cabinet group contract")
    _same_number(output.get("dc_total_mwh"), plan["total_nameplate_mwh"], "Total DC energy")
    if _positive_int(output.get("dc_blocks_total"), "Independent group count") != len(plan["groups"]):
        raise ValueError("Independent group count conflicts with the saved cabinet group contract")

    number_of_blocks = _positive_int(output.get("num_blocks"), "AC Block count")
    rows = output.get("ac_block_rows")
    if not isinstance(rows, list) or len(rows) != number_of_blocks or not all(isinstance(r, dict) for r in rows):
        raise ValueError("A complete saved AC Block row schedule is required")
    if output.get("transformer_topology_confirmation") != "confirmed_by_user":
        raise ValueError("Select and confirm the transformer LV topology in AC Sizing first")
    topology = output.get("transformer_topology")
    if topology not in {"two_winding", "three_winding"}:
        raise ValueError("Unsupported transformer topology")
    expected_windings = 1 if topology == "two_winding" else 2
    if type(output.get("lv_winding_count")) is not int or output["lv_winding_count"] != expected_windings:
        raise ValueError("LV winding count conflicts with the selected transformer topology")
    expected_lv_bus = "common_single_lv_busbar" if expected_windings == 1 else "independent_lv_busbars"
    if output.get("lv_busbar_topology", expected_lv_bus) != expected_lv_bus:
        raise ValueError("LV busbar topology conflicts with the selected transformer topology")
    if type(output.get("dc_block_output_circuits", 1)) is not int or output.get("dc_block_output_circuits", 1) != 1:
        raise ValueError("Each independent cabinet group must have exactly one PCS output domain")

    by_block: dict[int, list[dict]] = defaultdict(list)
    for group in plan["groups"]:
        _positive_int(group["group_index"], "Independent group identifier")
        if type(group["output_domain_count"]) is not int or group["output_domain_count"] != 1:
            raise ValueError("Each independent cabinet group must have exactly one PCS output domain")
        if group["ac_block_index"] > number_of_blocks:
            raise ValueError("Cabinet group references an AC Block outside the saved schedule")
        by_block[group["ac_block_index"]].append(group)
    pcs_counts, group_counts = [], []
    gross_power = 0.0
    for block_index, row in enumerate(rows, 1):
        pcs_count = _positive_int(row.get("pcs_count"), f"AC Block {block_index} PCS count")
        rating_kw = _finite_positive(row.get("pcs_kw"), f"AC Block {block_index} PCS rating")
        group_count = _positive_int(row.get("dc_blocks"), f"AC Block {block_index} group count")
        groups = sorted(by_block.get(block_index, []), key=lambda g: g["pcs_index"])
        if group_count != len(groups) or pcs_count != len(groups):
            raise ValueError("Exactly one intact independent cabinet group per PCS is required")
        if [g["pcs_index"] for g in groups] != list(range(1, pcs_count + 1)):
            raise ValueError("PCS identifiers must match the complete local AC Block PCS schedule")
        if pcs_count > 8:
            raise ValueError("The cabinet concept sheet supports up to eight PCS per AC Block")
        if expected_windings == 2 and pcs_count < 2:
            raise ValueError("Three-winding cabinet concepts require PCS on both independent LV windings")
        by_block[block_index] = groups
        pcs_counts.append(pcs_count)
        group_counts.append(group_count)
        gross_power += pcs_count * rating_kw / 1000

    counts_mirror = output.get("pcs_count_by_block")
    if not isinstance(counts_mirror, list) or any(type(n) is not int for n in counts_mirror) or counts_mirror != pcs_counts:
        raise ValueError("PCS count by block conflicts with the saved cabinet group assignment")
    for field in ("dc_blocks_per_ac", "dc_blocks_total_by_block"):
        if field in output and (not isinstance(output[field], list)
                                or any(type(n) is not int for n in output[field]) or output[field] != group_counts):
            raise ValueError(f"{field} conflicts with the saved cabinet group assignment")
    if "pcs_count_total" in output and (type(output["pcs_count_total"]) is not int or output["pcs_count_total"] != sum(pcs_counts)):
        raise ValueError("Total PCS count conflicts with the saved cabinet group assignment")
    if "transformer_count" in output and (type(output["transformer_count"]) is not int or output["transformer_count"] != number_of_blocks):
        raise ValueError("Transformer count conflicts with the saved AC Block schedule")
    if "total_ac_mw" in output:
        _same_number(output["total_ac_mw"], gross_power, "PCS nameplate power", .000001)
    _validate_allocation_mirror(output, by_block)
    return plan, rows, dict(by_block)


def _validate_allocation_mirror(output: Mapping[str, Any], by_block: dict[int, list[dict]]) -> None:
    """Check existing saved feeder mirrors; never generate a second allocation."""
    allocation = output.get("dc_allocation_plan")
    if allocation is None:
        return
    if not isinstance(allocation, list) or len(allocation) != len(by_block):
        raise ValueError("Incomplete saved DC allocation schedule")
    seen = set()
    for row in allocation:
        if not isinstance(row, dict):
            raise ValueError("Invalid saved DC allocation entry")
        block_index = row.get("ac_block_index")
        if type(block_index) is not int or block_index not in by_block or block_index in seen:
            raise ValueError("Invalid or duplicate AC Block in saved DC allocation")
        seen.add(block_index)
        groups = by_block[block_index]
        connections = row.get("dc_block_connections")
        if row.get("dc_blocks_total") != len(groups) or row.get("feeder_allocations") != [1] * len(groups):
            raise ValueError("Saved feeder allocation conflicts with independent cabinet group assignments")
        if not isinstance(connections, list) or len(connections) != len(groups):
            raise ValueError("Incomplete saved DC group connection schedule")
        terminal_pairs = []
        for connection in connections:
            if not isinstance(connection, dict):
                raise ValueError("Invalid saved DC group connection")
            local_id = connection.get("dc_block_index")
            feeders = connection.get("feeder_indices")
            if type(local_id) is not int or not isinstance(feeders, list) or len(feeders) != 1:
                raise ValueError("Independent cabinet groups require one distinct PCS connection")
            if type(feeders[0]) is not int:
                raise ValueError("Invalid PCS connection identifier")
            terminal_pairs.append((local_id, feeders[0]))
        expected_pairs = [(i, group["pcs_index"]) for i, group in
                          enumerate(sorted(groups, key=lambda g: g["group_index"]), 1)]
        if sorted(terminal_pairs) != expected_pairs:
            raise ValueError("Saved DC connection mirror conflicts with local group-to-PCS assignments")


def _voltage_text(output: Mapping[str, Any], fields: tuple[str, ...], unit: str) -> str:
    supplied = [output[f] for f in fields if output.get(f) is not None]
    if not supplied:
        return f"{unit}: TBC"
    values = [_finite_positive(v, fields[0]) for v in supplied]
    if any(not math.isclose(v, values[0], abs_tol=.001) for v in values[1:]):
        raise ValueError(f"Conflicting saved {unit} voltage values")
    return f"{values[0]:g} {unit} (AC input basis)"


def _graph(plan: dict, rows: list[dict], by_block: dict[int, list[dict]], topology: str) -> dict:
    nodes, edges, blocks = [], [], []
    for index, row in enumerate(rows, 1):
        prefix = f"ac{index}"
        groups = by_block[index]
        split = (len(groups) + 1) // 2
        buses = ["A"] if topology == "two_winding" else ["A", "B"]
        for bus in buses:
            nodes.append(dict(id=f"{prefix}-lv-{bus}", kind="lv_bus", ac_block_index=index,
                              winding=bus, independent=True))
        nodes.extend([
            dict(id=f"{prefix}-transformer", kind="concept_transformer", ac_block_index=index,
                 topology=topology, vector_group=None, grounding=None, nameplate_mva=None),
            dict(id=f"{prefix}-mv", kind="mv_interface", ac_block_index=index),
        ])
        for bus in buses:
            edges.append(dict(source=f"{prefix}-lv-{bus}", target=f"{prefix}-transformer",
                              domain="lv_winding", winding=bus))
        edges.append(dict(source=f"{prefix}-transformer", target=f"{prefix}-mv", domain="mv"))
        for position, group in enumerate(groups):
            group_id = group["group_index"]
            bus_id, pcs_id = f"group{group_id}-dc", f"{prefix}-pcs{group['pcs_index']}"
            lv_bus = "A" if topology == "two_winding" or position < split else "B"
            nodes.extend([
                dict(id=bus_id, kind="independent_dc_bus", ac_block_index=index,
                     group_index=group_id, nameplate_mwh=group["nameplate_mwh"]),
                dict(id=pcs_id, kind="pcs", ac_block_index=index, pcs_index=group["pcs_index"],
                     group_index=group_id, rating_kw=float(row["pcs_kw"]), lv_winding=lv_bus,
                     lv_allocation_confirmed=topology == "two_winding"),
            ])
            edges.append(dict(source=bus_id, target=pcs_id, domain="dc", group_index=group_id))
            edges.append(dict(source=pcs_id, target=f"{prefix}-lv-{lv_bus}", domain="lv_ac",
                              allocation_basis=("selected_common_lv_bus" if topology == "two_winding"
                                                else "concept_balanced_split_pending_oem")))
            for cabinet in group["cabinet_indices"]:
                cabinet_id = f"cabinet{cabinet}"
                nodes.append(dict(id=cabinet_id, kind="cabinet", cabinet_index=cabinet,
                                  group_index=group_id, ac_block_index=index, nameplate_kwh=418))
                edges.append(dict(source=cabinet_id, target=bus_id, domain="dc", group_index=group_id))
        blocks.append(dict(ac_block_index=index, group_indices=[g["group_index"] for g in groups],
                           cabinet_count=sum(g["cabinet_count"] for g in groups), pcs_count=len(groups),
                           nameplate_mwh=round(sum(g["nameplate_mwh"] for g in groups), 3),
                           pcs_nameplate_mw=round(len(groups) * float(row["pcs_kw"]) / 1000, 6)))
    return dict(renderer_version=RENDERER_VERSION, contract_version=plan["contract_version"],
                document_status="concept", capability_verified=False,
                physical_cabinet_count=plan["physical_cabinet_count"],
                total_nameplate_mwh=plan["total_nameplate_mwh"], transformer_topology=topology,
                lv_allocation_basis=("selected_common_lv_bus" if topology == "two_winding"
                                     else "concept_balanced_split_pending_oem"),
                nodes=nodes, edges=edges, ac_blocks=blocks)


def _svg_page(output: Mapping[str, Any], project_name: str, block: dict,
              groups: list[dict], row: dict, topology: str, total_blocks: int,
              lv_text: str, mv_text: str) -> str:
    """One geometry source: every branch uses the terminals drawn here."""
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="420mm" height="297mm" viewBox="0 0 {_WIDTH} {_HEIGHT}">',
             '<style>text{font-family:Arial,sans-serif;fill:#183550}.wire{fill:none;stroke:#263f50;stroke-width:2}.dc{stroke:#b35b18}.lv{stroke:#275b8b}.small{font-size:14px}.muted{fill:#506477}.warning{fill:#924a12}</style>',
             '<rect width="1680" height="1188" fill="white"/>',
             '<rect x="28" y="28" width="1624" height="1132" fill="none" stroke="#183550" stroke-width="2"/>']

    def text(x, y, value, size=16, **attrs):
        options = " ".join(f'{escape(k, quote=True)}="{escape(str(v), quote=True)}"' for k, v in attrs.items())
        parts.append(f'<text x="{x:g}" y="{y:g}" font-size="{size}" {options}>{escape(str(value))}</text>')

    def rect(x, y, width, height, **attrs):
        options = " ".join(f'{escape(k, quote=True)}="{escape(str(v), quote=True)}"' for k, v in attrs.items())
        parts.append(f'<rect x="{x:g}" y="{y:g}" width="{width:g}" height="{height:g}" {options}/>')

    def wire(points, element_id, domain=""):
        coordinates = " ".join(f"{x:g},{y:g}" for x, y in points)
        parts.append(f'<polyline id="{element_id}" points="{coordinates}" class="wire {domain}"/>')

    def dot(x, y):
        parts.append(f'<circle cx="{x:g}" cy="{y:g}" r="3" fill="#b35b18"/>')

    index = block["ac_block_index"]
    text(55, 68, "CALB  |  CABINET SYSTEM CONNECTION CONCEPT", 25, **{"font-weight": "bold"})
    # Split long customer labels at a safe length; SVG text is always escaped.
    name = " ".join(str(project_name).split())
    text(55, 100, f"Project: {name[:125]}" + ("..." if len(name) > 125 else ""), 17)
    text(55, 130, f"AC Block {index} / {total_blocks}  |  {block['cabinet_count']} cabinets  |  "
         f"{len(groups)} independent DC groups  |  {block['nameplate_mwh']:.3f} MWh DC nameplate", 18)
    text(55, 160, f"{len(groups)} x {float(row['pcs_kw']):g} kW PCS = {block['pcs_nameplate_mw']:.3f} MW nameplate; net POI output is not established", 15)
    rect(810, 185, 815, 780, fill="#f7fafd", stroke="#a8b9c8", **{"stroke-dasharray": "7 5"})
    text(830, 207, "AC BLOCK ELECTRICAL SCOPE - enclosure and dimensions TBC", 14)
    text(55, 207, "PARALLEL CABINETS - EACH GROUP HAS ITS OWN DC BUS", 14)

    centers = [252 + 88 * i for i in range(len(groups))]
    split = (len(groups) + 1) // 2
    bus_groups = [("A", centers)] if topology == "two_winding" else [("A", centers[:split]), ("B", centers[split:])]
    bus_x = {"A": 1190, "B": 1245}
    bus_mid = {label: (values[0] + values[-1]) / 2 for label, values in bus_groups}
    transformer_center = sum(bus_mid.values()) / len(bus_mid)
    transformer_height = max(225, max(bus_mid.values()) - min(bus_mid.values()) + 110)
    transformer_y = max(225, transformer_center - transformer_height / 2)
    transformer_center = transformer_y + transformer_height / 2
    transformer_x = 1320

    for position, (group, center) in enumerate(zip(groups, centers)):
        gid, pcs = group["group_index"], group["pcs_index"]
        rect(55, center - 39, 720, 79, fill="#fffaf3", stroke="#d7a46f", rx=5,
             id=f"group-{gid}-boundary")
        text(70, center - 21, f"GROUP {gid:02d}  |  {group['cabinet_count']} x 418 kWh  |  {group['nameplate_mwh']:.3f} MWh  |  independent DC bus", 14)
        # Every real cabinet is drawn once. Cabinet-to-bus branches join only
        # the same group's horizontal bus, never another group's bus or PCS.
        cabinet_centers = [88 + 54 * i for i in range(len(group["cabinet_indices"]))]
        bus_y = center - 9
        wire([(cabinet_centers[0], bus_y), (850, bus_y), (850, center), (965, center)],
             f"group-{gid}-to-pcs-{pcs}", "dc")
        for cabinet, cx in zip(group["cabinet_indices"], cabinet_centers):
            rect(cx - 23, center + 2, 46, 28, fill="white", stroke="#b35b18",
                 id=f"cabinet-{cabinet}")
            text(cx, center + 20, f"C{cabinet:03d}", 11, **{"text-anchor": "middle"})
            wire([(cx, center + 2), (cx, bus_y)], f"cabinet-{cabinet}-dc-branch", "dc")
            dot(cx, bus_y)
        rect(965, center - 28, 160, 56, fill="#e7f0f8", stroke="#275b8b", rx=3,
             id=f"ac-{index}-pcs-{pcs}")
        text(1045, center - 6, f"PCS {index:02d}-{pcs:02d}", 17, **{"text-anchor": "middle", "font-weight": "bold"})
        text(1045, center + 16, f"{float(row['pcs_kw']):g} kW", 14, **{"text-anchor": "middle"})
        lv = "A" if topology == "two_winding" or position < split else "B"
        wire([(1125, center), (bus_x[lv], center)], f"pcs-{pcs}-lv-{lv}", "lv")

    for label, values in bus_groups:
        x, middle = bus_x[label], bus_mid[label]
        if len(values) > 1:
            wire([(x, values[0]), (x, values[-1])], f"lv-{label}-bus", "lv")
        wire([(x, middle), (transformer_x, middle)], f"lv-{label}-to-transformer", "lv")
        text(x - 9, values[0] - 17, f"LV-{label}", 15, **{"text-anchor": "middle"})
        for cy in values:
            parts.append(f'<circle cx="{x}" cy="{cy}" r="3" fill="#275b8b"/>')

    rect(transformer_x, transformer_y, 200, transformer_height, fill="#edf2f6", stroke="#536b7f",
         id="concept-transformer", **{"stroke-width": 2})
    tx = transformer_x + 100
    for offset, label in [(-51, "TRANSFORMER"), (-26, "CONCEPT INTERFACE"), (5, "Vector / grounding: TBC"),
                          (28, "Nameplate / Uk: TBC"), (53, "Protection: TBC")]:
        text(tx, transformer_center + offset, label, 13 if offset > -26 else 16,
             **{"text-anchor": "middle"})
    for label, _ in bus_groups:
        text(transformer_x - 8, bus_mid[label] - 8, f"LV-{label}", 12,
             **{"text-anchor": "end", "id": f"transformer-lv-{label}-label"})
    wire([(1520, transformer_center), (1605, transformer_center)], "transformer-to-mv", "lv")
    text(1560, transformer_center - 20, "MV", 14, **{"text-anchor": "middle"})
    text(1580, transformer_center + 25, "Interface", 12, **{"text-anchor": "middle"})
    parts.append(f'<path d="M1596 {transformer_center - 6:g} L1605 {transformer_center:g} L1596 {transformer_center + 6:g}" fill="none" stroke="#263f50" stroke-width="2"/>')
    text(830, 917, f"LV: {lv_text}   |   MV: {mv_text}", 14)
    if topology == "three_winding":
        text(830, 941, "Two independent LV buses; concept PCS-to-winding allocation pending OEM confirmation.", 13, **{"class": "warning"})
    else:
        text(830, 941, "One common LV bus; transformer vector, neutral and earth connections remain TBC.", 13)

    rect(55, 985, 1570, 65, fill="#fff4e6", stroke="#d8ac6e")
    text(74, 1010, "CONCEPT / NOT FOR CONSTRUCTION", 22, **{"font-weight": "bold", "class": "warning"})
    text(74, 1035, "DC isolation / fusing, cable sizing, switching, interlocks, earthing and OEM limits require electrical design verification.", 15)
    text(55, 1080, "CONNECTION RULE: 1 intact independent cabinet group -> 1 PCS. No DC tie is shown between independent groups.", 16)
    text(55, 1107, "DC energy is nameplate energy. This sheet does not confirm usable energy, PCS compatibility or guaranteed POI performance.", 15)
    text(55, 1135, f"{RENDERER_VERSION}  |  {output['cabinet_group_contract']['contract_version']}  |  Sheet {index}/{total_blocks}  |  Electrical schematic - not to scale", 13)
    parts.append("</svg>")
    return "".join(parts)


def render_cabinet_sld(ac_output: Mapping[str, Any], project_name: str = "CALB BESS Project") -> dict:
    """Render all saved cabinet AC Blocks as deterministic, traceable concept SVGs.

    Returns ``pages[{ac_block_index, svg}]``, a JSON-serializable ``topology``
    graph (typed nodes and domain-labelled edges), and English ``warnings``.
    Invalid, contradictory or unconfirmed inputs raise ``ValueError`` before
    producing any page. No caller-owned dictionary is mutated.
    """
    plan, rows, by_block = _validate_output(ac_output)
    topology = ac_output["transformer_topology"]
    lv_text = _voltage_text(ac_output, ("lv_v", "lv_voltage_v", "inverter_lv_v"), "V")
    mv_text = _voltage_text(ac_output, ("grid_kv", "mv_kv", "mv_voltage_kv"), "kV")
    graph = _graph(plan, rows, by_block, topology)
    warnings = list(_BASE_WARNINGS)
    if topology == "three_winding":
        warnings.append("The separate LV-A / LV-B PCS allocation is a concept split pending OEM confirmation; no LV bus tie is included.")
    pages = [dict(ac_block_index=block["ac_block_index"],
                  svg=_svg_page(ac_output, project_name, block, by_block[block["ac_block_index"]],
                                rows[block["ac_block_index"] - 1], topology, len(rows), lv_text, mv_text))
             for block in graph["ac_blocks"]]
    return dict(pages=pages, topology=graph, warnings=warnings)
