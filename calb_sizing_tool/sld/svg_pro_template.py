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

import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, Iterable, Optional, Tuple


def _parse_translate(transform: str) -> Optional[Tuple[float, float]]:
    match = re.search(r"translate\(([-\d.]+)[ ,]([-\d.]+)\)", transform or "")
    if not match:
        return None
    try:
        return float(match.group(1)), float(match.group(2))
    except Exception:
        return None


def _float_or_none(value) -> Optional[float]:
    try:
        return float(value)
    except Exception:
        return None


def _iter_metadata_objects(data):
    if isinstance(data, dict):
        yield data
        for value in data.values():
            yield from _iter_metadata_objects(value)
    elif isinstance(data, list):
        for item in data:
            yield from _iter_metadata_objects(item)


def _get_metadata_id(obj: dict) -> Optional[str]:
    for key in ("id", "element_id", "elementId", "svgId", "diagramId", "componentId", "name"):
        value = obj.get(key)
        if isinstance(value, str):
            return value
    return None


def _extract_bbox(obj: dict) -> Optional[Tuple[float, float, float, float]]:
    candidates = []
    svg = obj.get("svg")
    if isinstance(svg, dict):
        candidates.append(svg)
    for key in ("bounds", "bbox", "box", "layout", "position"):
        value = obj.get(key)
        if isinstance(value, dict):
            candidates.append(value)
    candidates.append(obj)

    for data in candidates:
        x = _float_or_none(data.get("x"))
        y = _float_or_none(data.get("y"))
        w = _float_or_none(data.get("width"))
        h = _float_or_none(data.get("height"))
        if x is not None and y is not None and w is not None and h is not None:
            return x, y, w, h

        xmin = _float_or_none(data.get("xmin"))
        ymin = _float_or_none(data.get("ymin"))
        xmax = _float_or_none(data.get("xmax"))
        ymax = _float_or_none(data.get("ymax"))
        if None not in (xmin, ymin, xmax, ymax):
            return xmin, ymin, xmax - xmin, ymax - ymin

        left = _float_or_none(data.get("left"))
        top = _float_or_none(data.get("top"))
        right = _float_or_none(data.get("right"))
        bottom = _float_or_none(data.get("bottom"))
        if None not in (left, top, right, bottom):
            return left, top, right - left, bottom - top

    return None


def _collect_bboxes(metadata: dict, ids: Iterable[str]) -> list[Tuple[float, float, float, float]]:
    ids = set(ids)
    bboxes = []
    for obj in _iter_metadata_objects(metadata):
        if not isinstance(obj, dict):
            continue
        obj_id = _get_metadata_id(obj)
        if obj_id in ids:
            bbox = _extract_bbox(obj)
            if bbox:
                bboxes.append(bbox)
    return bboxes


def _union_bbox(bboxes: Iterable[Tuple[float, float, float, float]]) -> Optional[Tuple[float, float, float, float]]:
    bboxes = list(bboxes)
    if not bboxes:
        return None
    min_x = min(x for x, _, _, _ in bboxes)
    min_y = min(y for _, y, _, _ in bboxes)
    max_x = max(x + w for x, _, w, _ in bboxes)
    max_y = max(y + h for _, y, _, h in bboxes)
    return min_x, min_y, max_x - min_x, max_y - min_y


def _parse_number_attr(value: Optional[str]) -> Optional[float]:
    if not value:
        return None
    cleaned = str(value).replace("px", "").strip()
    try:
        return float(cleaned.split()[0])
    except Exception:
        return None


def _get_viewbox(root) -> Tuple[float, float, float, float]:
    view_box = root.attrib.get("viewBox")
    if view_box:
        parts = view_box.replace(",", " ").split()
        if len(parts) == 4:
            try:
                return tuple(float(part) for part in parts)
            except Exception:
                pass
    width = _parse_number_attr(root.attrib.get("width"))
    height = _parse_number_attr(root.attrib.get("height"))
    if width and height:
        return 0.0, 0.0, width, height
    return 0.0, 0.0, 1200.0, 600.0


def _set_viewbox(root, viewbox: Tuple[float, float, float, float]) -> None:
    min_x, min_y, width, height = viewbox
    root.attrib["viewBox"] = f"{min_x:.1f} {min_y:.1f} {width:.1f} {height:.1f}"
    if "width" in root.attrib:
        root.attrib["width"] = f"{width:.1f}"
    if "height" in root.attrib:
        root.attrib["height"] = f"{height:.1f}"


def _extend_viewbox(
    viewbox: Tuple[float, float, float, float],
    min_x: float,
    min_y: float,
    max_x: float,
    max_y: float,
) -> Tuple[float, float, float, float]:
    vb_min_x, vb_min_y, vb_w, vb_h = viewbox
    vb_max_x = vb_min_x + vb_w
    vb_max_y = vb_min_y + vb_h
    new_min_x = min(vb_min_x, min_x)
    new_min_y = min(vb_min_y, min_y)
    new_max_x = max(vb_max_x, max_x)
    new_max_y = max(vb_max_y, max_y)
    return new_min_x, new_min_y, new_max_x - new_min_x, new_max_y - new_min_y


def _build_equipment_list(snapshot: dict) -> list[Tuple[str, str]]:
    equipment_list = snapshot.get("equipment_list")
    if isinstance(equipment_list, list) and equipment_list:
        items = []
        for entry in equipment_list:
            if isinstance(entry, dict):
                label = entry.get("item") or entry.get("name") or entry.get("label")
                value = entry.get("value")
                if label:
                    items.append((str(label), "" if value is None else str(value)))
            elif isinstance(entry, (list, tuple)) and len(entry) >= 2:
                items.append((str(entry[0]), str(entry[1])))
            elif isinstance(entry, str):
                items.append((entry, ""))
        if items:
            return items

    items = []
    rmu = snapshot.get("rmu", {}) or {}
    rmu_parts = []
    if rmu.get("rated_voltage_kv"):
        rmu_parts.append(f"{rmu.get('rated_voltage_kv')} kV")
    if rmu.get("rated_current_a"):
        rmu_parts.append(f"{rmu.get('rated_current_a')} A")
    if rmu.get("short_circuit_ka_3s"):
        rmu_parts.append(f"{rmu.get('short_circuit_ka_3s')} kA/3s")
    if rmu.get("ct_ratio"):
        rmu_parts.append(f"CT {rmu.get('ct_ratio')}")
    if rmu.get("ct_class"):
        rmu_parts.append(str(rmu.get("ct_class")))
    if rmu.get("ct_burden_va"):
        rmu_parts.append(f"{rmu.get('ct_burden_va')} VA")
    if rmu_parts:
        items.append(("RMU", ", ".join(rmu_parts)))

    transformer = snapshot.get("transformer", {}) or {}
    tr_parts = []
    rated_kva = transformer.get("rated_kva")
    if rated_kva:
        tr_parts.append(f"{rated_kva} kVA")
    hv_kv = transformer.get("hv_kv")
    lv_v = transformer.get("lv_v")
    if hv_kv and lv_v:
        lv_kv = lv_v / 1000.0 if lv_v > 20 else lv_v
        tr_parts.append(f"{hv_kv}/{lv_kv:g} kV")
    if transformer.get("vector_group"):
        tr_parts.append(str(transformer.get("vector_group")))
    if transformer.get("impedance_percent"):
        tr_parts.append(f"{transformer.get('impedance_percent')}%")
    if transformer.get("tap_range"):
        tr_parts.append(str(transformer.get("tap_range")))
    if transformer.get("cooling"):
        tr_parts.append(str(transformer.get("cooling")))
    if tr_parts:
        items.append(("Transformer", ", ".join(tr_parts)))

    lv_busbar = snapshot.get("lv_busbar", {}) or {}
    lv_parts = []
    if lv_busbar.get("rated_current_a"):
        lv_parts.append(f"{lv_busbar.get('rated_current_a')} A")
    if lv_busbar.get("short_circuit_ka"):
        lv_parts.append(f"{lv_busbar.get('short_circuit_ka')} kA")
    if lv_parts:
        items.append(("LV Busbar", ", ".join(lv_parts)))

    feeder_breaker = snapshot.get("feeder_breaker", {}) or {}
    fdr_parts = []
    if feeder_breaker.get("rated_current_a"):
        fdr_parts.append(f"{feeder_breaker.get('rated_current_a')} A")
    if feeder_breaker.get("short_circuit_ka"):
        fdr_parts.append(f"{feeder_breaker.get('short_circuit_ka')} kA")
    if fdr_parts:
        items.append(("Feeder Breaker", ", ".join(fdr_parts)))

    ac_block = snapshot.get("ac_block", {}) or {}
    pcs_rating = ac_block.get("pcs_rating_each")
    if pcs_rating:
        items.append(("PCS", f"4 x {pcs_rating} kW"))

    cables = snapshot.get("cables", {}) or {}
    if cables.get("mv_cable_spec"):
        items.append(("MV Cable", str(cables.get("mv_cable_spec"))))
    if cables.get("lv_cable_spec"):
        items.append(("LV Cable", str(cables.get("lv_cable_spec"))))
    if cables.get("dc_cable_spec"):
        items.append(("DC Cable", str(cables.get("dc_cable_spec"))))
    if cables.get("dc_fuse_spec"):
        items.append(("DC Fuse", str(cables.get("dc_fuse_spec"))))
    elif snapshot.get("dc_blocks_by_feeder"):
        items.append(("DC Fuse", "TBD"))

    return items


def _find_text_positions(root, labels: set[str]) -> Dict[str, Tuple[float, float]]:
    positions: Dict[str, Tuple[float, float]] = {}
    parent_map = {child: parent for parent in root.iter() for child in parent}

    for elem in root.iter():
        if not elem.tag.endswith("text"):
            continue
        text_value = "".join(elem.itertext()).strip()
        if text_value not in labels:
            continue

        x_val = _parse_number_attr(elem.attrib.get("x"))
        y_val = _parse_number_attr(elem.attrib.get("y"))
        if x_val is not None and y_val is not None:
            positions[text_value] = (x_val, y_val)
            continue

        current = elem
        while current in parent_map:
            parent = parent_map[current]
            transform = parent.attrib.get("transform", "")
            pos = _parse_translate(transform)
            if pos:
                positions[text_value] = pos
                break
            current = parent

    return positions


def _add_style(root, tag_style: str) -> None:
    css = """
.sld-pro text { fill: #000000 !important; font-family: Arial, Helvetica, sans-serif !important; font-size: 11px !important; }
.sld-pro path, .sld-pro line, .sld-pro polyline, .sld-pro polygon, .sld-pro rect, .sld-pro circle, .sld-pro ellipse {
  stroke: #000000 !important;
  fill: #ffffff !important;
}
.sld-pro .sld-pro-outline { fill: none !important; stroke: #000000 !important; }
"""
    style = ET.Element(tag_style)
    style.text = css
    root.insert(0, style)
    existing_class = root.attrib.get("class", "")
    if "sld-pro" not in existing_class:
        root.attrib["class"] = f"{existing_class} sld-pro".strip()


def apply_pro_template(svg_in: Path, metadata_in, snapshot: dict, svg_out: Path) -> None:
    svg_in = Path(svg_in)
    svg_out = Path(svg_out)

    metadata = None
    if metadata_in:
        if isinstance(metadata_in, dict):
            metadata = metadata_in
        else:
            metadata_path = Path(metadata_in)
            if metadata_path.exists():
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

    tree = ET.parse(svg_in)
    root = tree.getroot()

    namespace = ""
    if root.tag.startswith("{"):
        namespace = root.tag.split("}")[0].strip("{")
    tag_g = f"{{{namespace}}}g" if namespace else "g"
    tag_rect = f"{{{namespace}}}rect" if namespace else "rect"
    tag_text = f"{{{namespace}}}text" if namespace else "text"
    tag_line = f"{{{namespace}}}line" if namespace else "line"
    tag_style = f"{{{namespace}}}style" if namespace else "style"

    _add_style(root, tag_style)

    viewbox = _get_viewbox(root)

    mv_text_positions = _find_text_positions(root, {"BBS_MV_01", "VL_MV_01"})

    parent_map = {child: parent for parent in root.iter() for child in parent}
    hide_labels = {
        "VL_MV_01",
        "VL_LV_01",
        "BBS_MV_01",
        "BBS_LV_01",
        "RMU_BUS_01",
        "SUB_MV_NODE_01",
    }
    for elem in list(root.iter()):
        if not elem.tag.endswith("text"):
            continue
        text_value = "".join(elem.itertext()).strip()
        if text_value in hide_labels or text_value.startswith("FDR_BUS_"):
            parent = parent_map.get(elem)
            if parent is not None:
                parent.remove(elem)

    mv_labels = snapshot.get("mv", {}).get("labels", {}) or {}
    to_switchgear = mv_labels.get("to_switchgear") or "To MV Switchgear"
    to_other_rmu = mv_labels.get("to_other_rmu") or "To Other RMU"

    mv_label_positions = {}
    if metadata:
        mv_bbox = _union_bbox(_collect_bboxes(metadata, {"BBS_MV_01"}))
        if mv_bbox:
            x, y, w, h = mv_bbox
            mv_label_positions = {
                "left": (x - 10, y + h / 2 - 4),
                "right": (x + w + 10, y + h / 2 - 4),
            }
    if not mv_label_positions:
        base = mv_text_positions.get("BBS_MV_01") or mv_text_positions.get("VL_MV_01")
        if base:
            mv_label_positions = {
                "left": (base[0] - 20, base[1]),
                "right": (base[0] + 140, base[1]),
            }
    if not mv_label_positions:
        min_x, min_y, width, _ = viewbox
        mv_label_positions = {
            "left": (min_x + 40, min_y + 40),
            "right": (min_x + width - 40, min_y + 40),
        }

    label_group = ET.Element(tag_g, attrib={"class": "sld-pro-labels"})
    left_text = ET.SubElement(
        label_group,
        tag_text,
        attrib={
            "x": f"{mv_label_positions['left'][0]:.1f}",
            "y": f"{mv_label_positions['left'][1]:.1f}",
            "text-anchor": "end",
        },
    )
    left_text.text = to_switchgear
    right_text = ET.SubElement(
        label_group,
        tag_text,
        attrib={
            "x": f"{mv_label_positions['right'][0]:.1f}",
            "y": f"{mv_label_positions['right'][1]:.1f}",
            "text-anchor": "start",
        },
    )
    right_text.text = to_other_rmu
    root.append(label_group)

    pcs_ids = [f.get("pcs_id") for f in snapshot.get("feeders", []) if f.get("pcs_id")]
    pcs_positions = {}
    if metadata and pcs_ids:
        for pcs_id in pcs_ids:
            bbox = _union_bbox(_collect_bboxes(metadata, {pcs_id}))
            if bbox:
                x, y, w, h = bbox
                pcs_positions[pcs_id] = (x + w / 2, y + h)

    if not pcs_positions:
        text_positions = _find_text_positions(root, set(pcs_ids))
        pcs_positions.update(text_positions)

    dc_by_feeder = {item.get("feeder_id"): item for item in snapshot.get("dc_blocks_by_feeder", [])}

    dc_box_width = 120
    dc_box_height = 28
    dc_offset_y = 28
    dc_boxes_bbox = None

    for idx, feeder in enumerate(snapshot.get("feeders", []), start=1):
        pcs_id = feeder.get("pcs_id") or f"PCS-{idx:02d}"
        feeder_id = feeder.get("feeder_id") or f"FDR-{idx:02d}"
        dc_entry = dc_by_feeder.get(feeder_id, {})
        dc_count = int(dc_entry.get("dc_block_count") or 0)
        dc_energy = dc_entry.get("dc_block_energy_mwh")

        if pcs_id in pcs_positions:
            base_x, base_y = pcs_positions[pcs_id]
        else:
            base_x = viewbox[0] + 120 + (idx - 1) * (dc_box_width + 20)
            base_y = viewbox[1] + 120

        rect_x = base_x - dc_box_width / 2
        rect_y = base_y + dc_offset_y

        label = f"DC Block x{dc_count}"
        if dc_energy is not None:
            try:
                label += f" / {float(dc_energy):.2f} MWh"
            except Exception:
                label += f" / {dc_energy} MWh"

        group = ET.Element(tag_g, attrib={"class": "dc-block"})
        ET.SubElement(
            group,
            tag_rect,
            attrib={
                "x": f"{rect_x:.1f}",
                "y": f"{rect_y:.1f}",
                "width": f"{dc_box_width}",
                "height": f"{dc_box_height}",
                "rx": "3",
                "ry": "3",
                "class": "sld-pro-outline",
            },
        )
        text = ET.SubElement(
            group,
            tag_text,
            attrib={
                "x": f"{rect_x + 4:.1f}",
                "y": f"{rect_y + 17:.1f}",
            },
        )
        text.text = label
        root.append(group)

        box_bbox = (rect_x, rect_y, dc_box_width, dc_box_height)
        dc_boxes_bbox = _union_bbox([box_bbox] if dc_boxes_bbox is None else [dc_boxes_bbox, box_bbox])

    if metadata:
        container_targets = {"TR_01", "RMU_01", "BBS_LV_01"}
        container_targets.update(pcs_ids)
        container_bbox = _union_bbox(_collect_bboxes(metadata, container_targets))
    else:
        container_bbox = None

    if container_bbox is None and pcs_positions:
        boxes = []
        for pos in pcs_positions.values():
            boxes.append((pos[0] - 10, pos[1] - 10, 20, 20))
        container_bbox = _union_bbox(boxes)

    if container_bbox:
        cx, cy, cw, ch = container_bbox
        padding = 24
        rect_x = cx - padding
        rect_y = cy - padding
        rect_w = cw + padding * 2
        rect_h = ch + padding * 2

        group = ET.Element(tag_g, attrib={"class": "pcs-container"})
        ET.SubElement(
            group,
            tag_rect,
            attrib={
                "x": f"{rect_x:.1f}",
                "y": f"{rect_y:.1f}",
                "width": f"{rect_w:.1f}",
                "height": f"{rect_h:.1f}",
                "fill": "none",
                "stroke": "#000000",
                "stroke-width": "1.2",
                "stroke-dasharray": "6,4",
                "class": "sld-pro-outline",
            },
        )
        title = ET.SubElement(
            group,
            tag_text,
            attrib={
                "x": f"{rect_x + 4:.1f}",
                "y": f"{rect_y + 14:.1f}",
            },
        )
        title.text = "PCS Container"
        root.append(group)

        viewbox = _extend_viewbox(viewbox, rect_x, rect_y, rect_x + rect_w, rect_y + rect_h)

    equipment_items = _build_equipment_list(snapshot)
    if equipment_items:
        table_width = 280
        table_margin = 20
        row_height = 16
        header_height = 18
        table_height = header_height + row_height * (len(equipment_items) + 1)

        min_x, min_y, width, _ = viewbox
        table_x = min_x - table_width - table_margin
        table_y = min_y + table_margin

        group = ET.Element(tag_g, attrib={"class": "equipment-list"})
        ET.SubElement(
            group,
            tag_rect,
            attrib={
                "x": f"{table_x:.1f}",
                "y": f"{table_y:.1f}",
                "width": f"{table_width}",
                "height": f"{table_height}",
                "fill": "none",
                "stroke": "#000000",
                "stroke-width": "1",
            },
        )

        col_split = table_x + 110
        ET.SubElement(
            group,
            tag_line,
            attrib={
                "x1": f"{col_split:.1f}",
                "y1": f"{table_y:.1f}",
                "x2": f"{col_split:.1f}",
                "y2": f"{table_y + table_height:.1f}",
                "stroke": "#000000",
                "stroke-width": "1",
            },
        )

        header_line_y = table_y + header_height
        ET.SubElement(
            group,
            tag_line,
            attrib={
                "x1": f"{table_x:.1f}",
                "y1": f"{header_line_y:.1f}",
                "x2": f"{table_x + table_width:.1f}",
                "y2": f"{header_line_y:.1f}",
                "stroke": "#000000",
                "stroke-width": "1",
            },
        )

        title = ET.SubElement(
            group,
            tag_text,
            attrib={"x": f"{table_x + 4:.1f}", "y": f"{table_y + 12:.1f}"},
        )
        title.text = "Equipment List"

        header_item = ET.SubElement(
            group,
            tag_text,
            attrib={"x": f"{table_x + 4:.1f}", "y": f"{table_y + header_height + 12:.1f}"},
        )
        header_item.text = "Item"
        header_spec = ET.SubElement(
            group,
            tag_text,
            attrib={"x": f"{col_split + 4:.1f}", "y": f"{table_y + header_height + 12:.1f}"},
        )
        header_spec.text = "Spec"

        for idx, (label, value) in enumerate(equipment_items, start=1):
            row_y = table_y + header_height + row_height * idx + 12
            item_text = ET.SubElement(
                group,
                tag_text,
                attrib={"x": f"{table_x + 4:.1f}", "y": f"{row_y:.1f}"},
            )
            item_text.text = label
            spec_text = ET.SubElement(
                group,
                tag_text,
                attrib={"x": f"{col_split + 4:.1f}", "y": f"{row_y:.1f}"},
            )
            spec_text.text = value

        root.append(group)

        viewbox = _extend_viewbox(
            viewbox,
            table_x,
            table_y,
            table_x + table_width,
            table_y + table_height + table_margin,
        )

    if dc_boxes_bbox:
        x, y, w, h = dc_boxes_bbox
        viewbox = _extend_viewbox(viewbox, x, y, x + w, y + h + 10)

    _set_viewbox(root, viewbox)

    svg_out.parent.mkdir(parents=True, exist_ok=True)
    tree.write(svg_out, encoding="utf-8", xml_declaration=True)


