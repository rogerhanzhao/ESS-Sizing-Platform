from __future__ import annotations

from html import escape
from math import ceil
from typing import Any

from calb_sizing_tool.plugins.base import ArtifactPayload, json_bytes
from calb_sizing_tool.schemas.diagram_inputs import AcSnapshot
from calb_sizing_tool.schemas.run_bundle import DcRunBundle


_STATUS_LABELS = {
    "official": "FORMAL / RELEASED",
    "concept": "CONCEPT ONLY - NOT FOR CONSTRUCTION",
    "draft_override": "DRAFT / OVERRIDE - NOT FOR CONSTRUCTION",
}


def _as_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value: Any) -> int | None:
    numeric = _as_float(value)
    if numeric is None:
        return None
    return int(numeric)


def _number(value: Any, *, digits: int = 1, unit: str = "") -> str:
    numeric = _as_float(value)
    if numeric is None:
        return "Not specified"
    rendered = f"{numeric:,.{digits}f}"
    return f"{rendered} {unit}".strip()


def _value_for_block(values: Any, index: int, fallback: int | None = None) -> int | None:
    if isinstance(values, list) and index < len(values):
        return _as_int(values[index])
    return fallback


def _block_rows(ac_output: dict[str, Any]) -> list[dict[str, Any]]:
    block_count = max(0, _as_int(ac_output.get("num_blocks")) or 0)
    pcs_counts = ac_output.get("pcs_count_by_block")
    dc_counts = ac_output.get("dc_blocks_total_by_block") or ac_output.get("dc_blocks_per_ac")
    allocation = ac_output.get("dc_allocation_plan")
    if not isinstance(dc_counts, list) and isinstance(allocation, list):
        dc_counts = [
            entry.get("dc_blocks_total") if isinstance(entry, dict) else None
            for entry in allocation
        ]

    pcs_fallback = _as_int(ac_output.get("pcs_per_block"))
    transformer_total = _as_int(ac_output.get("transformer_count"))
    transformers_per_block = (
        transformer_total // block_count
        if transformer_total is not None and block_count and transformer_total % block_count == 0
        else None
    )
    rows: list[dict[str, Any]] = []
    for zero_index in range(block_count):
        rows.append(
            {
                "block_index": zero_index + 1,
                "block_id": f"AC-{zero_index + 1:02d}",
                "pcs_count": _value_for_block(pcs_counts, zero_index, pcs_fallback),
                "dc_blocks": _value_for_block(dc_counts, zero_index),
                "transformers": transformers_per_block,
                "source": "AC runtime snapshot",
            }
        )
    return rows


def build_site_electrical_index_payload(
    *,
    run_bundle: DcRunBundle,
    ac_snapshot: AcSnapshot,
    document_status: str,
    typical_group_index: int,
) -> dict[str, Any]:
    """Create a full-station index without claiming site-plan geometry.

    This is deliberately a system/electrical index. It lists every AC block
    from the persisted AC allocation, and points to the separately rendered
    typical block schematic. It must never be interpreted as a site layout.
    """
    output = dict(ac_snapshot.output or {})
    rows = _block_rows(output)
    pcs_total = _as_int(output.get("pcs_count_total"))
    if pcs_total is None:
        pcs_total = sum(item["pcs_count"] or 0 for item in rows) or None
    dc_blocks_total = _as_int(output.get("dc_blocks_total"))
    if dc_blocks_total is None:
        dc_blocks_total = sum(item["dc_blocks"] or 0 for item in rows) or None

    return {
        "document_type": "Site Electrical Index",
        "sheet_id": "SLD-01",
        "document_status": document_status,
        "not_for_construction": document_status != "official",
        "scope": {
            "included": "Full-station AC Block index and sizing-derived electrical quantities.",
            "excluded": (
                "Site boundary, equipment coordinates, access roads, fire lanes, cable routing, "
                "protection settings, and construction clearances."
            ),
            "typical_sld_reference": f"SLD-02 Typical AC Block SLD (AC Block {typical_group_index}).",
        },
        "project": {
            "project_code": run_bundle.project_code,
            "project_name": run_bundle.project_name,
            "case_code": run_bundle.case_code,
            "case_name": run_bundle.case_name,
            "run_id": run_bundle.run_id,
        },
        "quantity_summary": {
            "poi_power_mw": _as_float(output.get("poi_power_mw")),
            "poi_energy_mwh": _as_float(output.get("poi_energy_mwh")),
            "mv_voltage_kv": _as_float(output.get("mv_voltage_kv") or output.get("grid_kv")),
            "lv_voltage_v": _as_float(output.get("lv_voltage_v") or output.get("inverter_lv_v")),
            "ac_block_count": len(rows),
            "pcs_total": pcs_total,
            "dc_blocks_total": dc_blocks_total,
            "transformer_count": _as_int(output.get("transformer_count")),
        },
        "ac_block_index": rows,
    }


def build_design_basis_schedule_payload(
    *,
    site_index: dict[str, Any],
    ac_snapshot: AcSnapshot,
    formal_readiness: dict[str, Any],
    document_status: str,
) -> dict[str, Any]:
    output = dict(ac_snapshot.output or {})
    summary = dict(site_index.get("quantity_summary") or {})
    basis_items = [
        {
            "category": "Sizing basis",
            "item": "POI power",
            "value": _number(summary.get("poi_power_mw"), unit="MW"),
            "source": "AC runtime snapshot",
            "status": "calculated",
        },
        {
            "category": "Sizing basis",
            "item": "POI energy",
            "value": _number(summary.get("poi_energy_mwh"), unit="MWh"),
            "source": "AC runtime snapshot",
            "status": "calculated",
        },
        {
            "category": "Electrical basis",
            "item": "MV nominal voltage",
            "value": _number(summary.get("mv_voltage_kv"), unit="kV"),
            "source": "AC runtime snapshot",
            "status": "calculated",
        },
        {
            "category": "Electrical basis",
            "item": "LV nominal voltage",
            "value": _number(summary.get("lv_voltage_v"), digits=0, unit="V"),
            "source": "AC runtime snapshot",
            "status": "calculated",
        },
        {
            "category": "AC architecture",
            "item": "AC Blocks / PCS / DC Blocks",
            "value": (
                f"{summary.get('ac_block_count') or 'Not specified'} / "
                f"{summary.get('pcs_total') or 'Not specified'} / "
                f"{summary.get('dc_blocks_total') or 'Not specified'}"
            ),
            "source": "AC runtime snapshot",
            "status": "calculated",
        },
        {
            "category": "AC architecture",
            "item": "PCS rating (each)",
            "value": _number(output.get("pcs_kw"), digits=0, unit="kW"),
            "source": "AC runtime snapshot",
            "status": "calculated",
        },
        {
            "category": "AC architecture",
            "item": "Transformer rating (each)",
            "value": _number(output.get("transformer_mva"), digits=3, unit="MVA"),
            "source": "AC runtime snapshot",
            "status": "calculated",
        },
        {
            "category": "Document issue",
            "item": "Current document status",
            "value": _STATUS_LABELS.get(document_status, document_status),
            "source": "SLD readiness gate",
            "status": document_status,
        },
    ]
    formal_issue_register = []
    for issue in list(formal_readiness.get("issues") or []):
        issue_payload = dict(issue) if isinstance(issue, dict) else {"message": str(issue)}
        issue_id = str(issue_payload.get("issue_id") or "")
        issue_payload["display_message"] = _friendly_readiness_message(issue_id, issue_payload.get("message"))
        formal_issue_register.append(issue_payload)
    return {
        "document_type": "Electrical Design Basis Schedule",
        "sheet_id": "SLD-03",
        "document_status": document_status,
        "not_for_construction": document_status != "official",
        "project": site_index.get("project"),
        "basis_items": basis_items,
        "formal_readiness": formal_readiness,
        "formal_issue_register": formal_issue_register,
        "scope_note": (
            "Sizing-derived values are recorded as calculated. Cable, protection, grounding and site-specific "
            "requirements remain governed by the formal readiness gate and are not inferred by this schedule."
        ),
    }


def build_concept_interface_scope_payload(
    *,
    site_index: dict[str, Any],
    document_status: str,
) -> dict[str, Any]:
    """Describe package interfaces without asserting contractual ownership.

    The sizing tool can identify the electrical hand-off surfaces it renders,
    but it has no authority to allocate utility, EPC, owner or vendor duties.
    This sheet makes that limitation visible rather than hiding it in a diagram.
    """
    summary = dict(site_index.get("quantity_summary") or {})
    return {
        "document_type": "Concept Interface and Scope Diagram",
        "sheet_id": "SLD-04",
        "document_status": document_status,
        "not_for_construction": document_status != "official",
        "project": site_index.get("project"),
        "scope_status": "Responsibility allocation is project-specific and must be confirmed outside this sizing tool.",
        "scope_zones": [
            {
                "zone_id": "external_poi",
                "label": "External Grid / POI Interface",
                "included": "POI and upstream MV system are shown only as an interface direction.",
                "excluded": "Utility protection philosophy, grid studies, POI equipment and routing.",
                "responsibility": "To be confirmed by project agreement.",
            },
            {
                "zone_id": "typical_ac_block",
                "label": "Typical BESS AC Block Package",
                "included": (
                    f"Sizing-derived architecture: {summary.get('ac_block_count') or 'Not specified'} AC Blocks, "
                    f"{summary.get('pcs_total') or 'Not specified'} PCS and "
                    f"{summary.get('dc_blocks_total') or 'Not specified'} DC Blocks."
                ),
                "excluded": "Final cable selection, protection settings, grounding and construction details.",
                "responsibility": "Interface definition only; contract allocation not declared.",
            },
            {
                "zone_id": "project_integration",
                "label": "Project Integration / By-Project Works",
                "included": "Civil, communications, auxiliary, access and site integration interfaces.",
                "excluded": "Site layout, civil design, cable route geometry and construction staging.",
                "responsibility": "To be confirmed by project agreement.",
            },
        ],
        "interface_register": [
            {
                "interface": "POI / MV feeder to AC Block RMU",
                "visible_in_package": "Direction and electrical relationship only",
                "confirmation_required": "POI location, MV routing, protection coordination and utility requirements",
            },
            {
                "interface": "Transformer / LV bus / PCS / DC Blocks",
                "visible_in_package": "Typical AC Block topology on SLD-02",
                "confirmation_required": "Equipment final ratings, cable schedules, protection and grounding",
            },
            {
                "interface": "Control, auxiliary, civil and communications",
                "visible_in_package": "Scope boundary only",
                "confirmation_required": "Architecture, locations, interfaces and responsibility allocation",
            },
        ],
    }


def _friendly_readiness_message(issue_id: str, fallback: Any) -> str:
    missing_field_labels = {
        "mv_cable_spec": "MV cable specification",
        "lv_cable_spec": "LV cable specification",
        "dc_cable_spec": "DC cable specification",
        "battery_cell_spec": "Battery cell specification",
    }
    if issue_id.startswith("missing_professional_field:"):
        field_name = issue_id.split(":", 1)[1]
        label = missing_field_labels.get(field_name, field_name.replace("_", " ").title())
        return f"{label}: engineering confirmation is required before formal issue."
    replacements = {
        "not_strict_formal_mode": "Strict validation without engineering override is required before formal issue.",
        "missing_ac_snapshot_provenance": "The AC runtime snapshot must be linked to its source run before formal issue.",
        "ac_snapshot_run_mismatch": "The AC runtime snapshot must match the active run before formal issue.",
        "missing_ac_dc_allocation_total": "The total DC Block allocation must be confirmed before formal issue.",
        "dc_ac_block_total_mismatch": "DC and AC Block allocation totals must reconcile before formal issue.",
        "sld_group_allocation_mismatch": "The selected AC Block allocation must reconcile before formal issue.",
        "dc_ac_energy_total_mismatch": "DC and AC energy totals must reconcile before formal issue.",
        "sld_dc_energy_representation_mismatch": "SLD DC Block energy representation must reconcile before formal issue.",
        "missing_persisted_project_settings": "Persisted case-level SLD engineering settings should be recorded before formal issue.",
        "non_professional_renderer_mode": "Use the engineering_v2 renderer for the formal professional template.",
    }
    return replacements.get(issue_id, str(fallback or "Formal readiness item requires engineering review."))


def _document_header(*, title: str, subtitle: str, sheet_id: str, payload: dict[str, Any]) -> list[str]:
    project = dict(payload.get("project") or {})
    status = str(payload.get("document_status") or "concept")
    status_label = _STATUS_LABELS.get(status, status.upper())
    run_id = str(project.get("run_id") or "")
    run_short = run_id[-8:] if len(run_id) >= 8 else run_id or "Not specified"
    return [
        '<rect width="1800" height="112" fill="#0E2240"/>',
        f'<text x="70" y="52" class="title">{escape(title)}</text>',
        f'<text x="70" y="84" class="subtitle">{escape(subtitle)}</text>',
        f'<text x="1730" y="46" text-anchor="end" class="status">{escape(status_label)}</text>',
        f'<text x="1730" y="80" text-anchor="end" class="sheet">{escape(sheet_id)} | Run {escape(run_short)}</text>',
    ]


def _document_footer(*, payload: dict[str, Any], height: int) -> list[str]:
    project = dict(payload.get("project") or {})
    project_name = project.get("project_name") or project.get("project_code") or "Not specified"
    case_name = project.get("case_name") or project.get("case_code") or "Not specified"
    status = _STATUS_LABELS.get(str(payload.get("document_status") or "concept"), "CONCEPT")
    top = height - 94
    return [
        f'<rect x="50" y="{top}" width="1700" height="54" fill="#F3F7FB" stroke="#9FB3C8"/>',
        f'<text x="70" y="{top + 24}" class="footer">Project: {escape(str(project_name))}</text>',
        f'<text x="70" y="{top + 44}" class="footer">Case: {escape(str(case_name))}</text>',
        f'<text x="920" y="{top + 24}" class="footer">Document status: {escape(status)}</text>',
        '<text x="920" y="' + str(top + 44) + '" class="footer">Generated from persisted sizing and AC allocation snapshots</text>',
    ]


def _status_watermark(document_status: str, *, width: int, y: int) -> str:
    if document_status == "official":
        return ""
    label = _STATUS_LABELS.get(document_status, "NOT FOR CONSTRUCTION")
    return (
        f'<text x="{width // 2}" y="{y}" text-anchor="middle" class="watermark">'
        f"{escape(label)}</text>"
    )


def render_site_electrical_index_svg(payload: dict[str, Any]) -> bytes:
    rows = list(payload.get("ac_block_index") or [])
    columns = 5
    row_count = max(1, ceil(len(rows) / columns))
    grid_y = 366
    height = max(980, grid_y + row_count * 68 + 150)
    summary = dict(payload.get("quantity_summary") or {})
    metrics = [
        ("POI POWER", _number(summary.get("poi_power_mw"), unit="MW")),
        ("POI ENERGY", _number(summary.get("poi_energy_mwh"), unit="MWh")),
        ("MV VOLTAGE", _number(summary.get("mv_voltage_kv"), unit="kV")),
        ("AC BLOCKS", str(summary.get("ac_block_count") or "Not specified")),
        ("PCS TOTAL", str(summary.get("pcs_total") or "Not specified")),
        ("DC BLOCKS", str(summary.get("dc_blocks_total") or "Not specified")),
    ]
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="1800" height="{height}" viewBox="0 0 1800 {height}">',
        "<style>.title{font:700 30px Arial;fill:#fff}.subtitle{font:400 16px Arial;fill:#D7E5F3}.status{font:700 15px Arial;fill:#FFD7D1}.sheet{font:400 14px Arial;fill:#D7E5F3}.section{font:700 18px Arial;fill:#173B63}.note{font:400 14px Arial;fill:#536579}.metric-label{font:700 12px Arial;fill:#536579}.metric-value{font:700 24px Arial;fill:#102A43}.block-title{font:700 15px Arial;fill:#173B63}.block-detail{font:400 12px Arial;fill:#334E68}.footer{font:400 13px Arial;fill:#334E68}.watermark{font:700 34px Arial;fill:#B42318;fill-opacity:.25}</style>",
        '<rect width="100%" height="100%" fill="#FFFFFF"/>',
        *_document_header(
            title="SITE ELECTRICAL INDEX",
            subtitle="Full-station AC Block index - the typical AC Block SLD is a separate package sheet",
            sheet_id="SLD-01",
            payload=payload,
        ),
        '<text x="70" y="154" class="section">Sizing-derived station summary</text>',
    ]
    for index, (label, value) in enumerate(metrics):
        x = 70 + index * 285
        parts.extend(
            [
                f'<rect x="{x}" y="174" width="255" height="104" rx="6" fill="#F3F7FB" stroke="#C6D5E5"/>',
                f'<text x="{x + 18}" y="204" class="metric-label">{escape(label)}</text>',
                f'<text x="{x + 18}" y="244" class="metric-value">{escape(value)}</text>',
            ]
        )
    scope = dict(payload.get("scope") or {})
    parts.extend(
        [
            '<text x="70" y="322" class="section">AC Block allocation index</text>',
            f'<text x="70" y="344" class="note">{escape(str(scope.get("typical_sld_reference") or ""))}</text>',
        ]
    )
    for index, row in enumerate(rows):
        column = index % columns
        row_number = index // columns
        x = 70 + column * 336
        y = grid_y + row_number * 68
        pcs = row.get("pcs_count") if row.get("pcs_count") is not None else "Not specified"
        dc_blocks = row.get("dc_blocks") if row.get("dc_blocks") is not None else "Not specified"
        transformers = row.get("transformers") if row.get("transformers") is not None else "Not specified"
        parts.extend(
            [
                f'<rect x="{x}" y="{y}" width="312" height="50" rx="5" fill="#FFFFFF" stroke="#8FA9C2"/>',
                f'<text x="{x + 14}" y="{y + 22}" class="block-title">{escape(str(row.get("block_id") or "AC Block"))}</text>',
                f'<text x="{x + 14}" y="{y + 40}" class="block-detail">PCS {escape(str(pcs))} | DC Blocks {escape(str(dc_blocks))} | MVT {escape(str(transformers))}</text>',
            ]
        )
    parts.append(_status_watermark(str(payload.get("document_status") or "concept"), width=1800, y=grid_y + max(1, row_count // 2) * 68))
    parts.extend(_document_footer(payload=payload, height=height))
    parts.append("</svg>")
    return "".join(parts).encode("utf-8")


def render_design_basis_schedule_svg(payload: dict[str, Any]) -> bytes:
    basis_items = list(payload.get("basis_items") or [])
    issue_items = list(payload.get("formal_issue_register") or [])
    table_y = 230
    row_height = 40
    issue_y = table_y + (len(basis_items) + 1) * row_height + 58
    height = max(940, issue_y + max(1, min(len(issue_items), 6)) * 36 + 160)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="1800" height="{height}" viewBox="0 0 1800 {height}">',
        "<style>.title{font:700 30px Arial;fill:#fff}.subtitle{font:400 16px Arial;fill:#D7E5F3}.status{font:700 15px Arial;fill:#FFD7D1}.sheet{font:400 14px Arial;fill:#D7E5F3}.section{font:700 18px Arial;fill:#173B63}.note{font:400 14px Arial;fill:#536579}.header-cell{font:700 13px Arial;fill:#fff}.cell{font:400 13px Arial;fill:#243B53}.cell-strong{font:700 13px Arial;fill:#173B63}.issue{font:400 13px Arial;fill:#7A271A}.footer{font:400 13px Arial;fill:#334E68}.watermark{font:700 34px Arial;fill:#B42318;fill-opacity:.25}</style>",
        '<rect width="100%" height="100%" fill="#FFFFFF"/>',
        *_document_header(
            title="ELECTRICAL DESIGN BASIS SCHEDULE",
            subtitle="Sizing-derived values and formal issue register - values are not a construction specification",
            sheet_id="SLD-03",
            payload=payload,
        ),
        '<text x="70" y="158" class="section">Sizing and electrical basis</text>',
        f'<text x="70" y="184" class="note">{escape(str(payload.get("scope_note") or ""))}</text>',
        f'<rect x="70" y="{table_y - row_height}" width="1660" height="{row_height}" fill="#173B63"/>',
        f'<text x="88" y="{table_y - 14}" class="header-cell">CATEGORY</text>',
        f'<text x="390" y="{table_y - 14}" class="header-cell">BASIS</text>',
        f'<text x="820" y="{table_y - 14}" class="header-cell">VALUE</text>',
        f'<text x="1280" y="{table_y - 14}" class="header-cell">SOURCE / STATUS</text>',
    ]
    for index, item in enumerate(basis_items):
        y = table_y + index * row_height
        fill = "#F7FAFC" if index % 2 == 0 else "#FFFFFF"
        parts.extend(
            [
                f'<rect x="70" y="{y - 25}" width="1660" height="{row_height}" fill="{fill}" stroke="#D8E2EC"/>',
                f'<text x="88" y="{y}" class="cell">{escape(str(item.get("category") or ""))}</text>',
                f'<text x="390" y="{y}" class="cell-strong">{escape(str(item.get("item") or ""))}</text>',
                f'<text x="820" y="{y}" class="cell">{escape(str(item.get("value") or ""))}</text>',
                f'<text x="1280" y="{y}" class="cell">{escape(str(item.get("source") or ""))} | {escape(str(item.get("status") or ""))}</text>',
            ]
        )
    parts.append(f'<text x="70" y="{issue_y}" class="section">Formal issue register</text>')
    shown_issues = issue_items[:6]
    if shown_issues:
        for index, issue in enumerate(shown_issues):
            y = issue_y + 30 + index * 36
            parts.append(
                f'<text x="88" y="{y}" class="issue">{escape(str(issue.get("severity") or "").upper())}: '
                f'{escape(str(issue.get("display_message") or issue.get("message") or issue.get("issue_id") or ""))}</text>'
            )
        hidden_count = len(issue_items) - len(shown_issues)
        if hidden_count > 0:
            y = issue_y + 30 + len(shown_issues) * 36
            parts.append(
                f'<text x="88" y="{y}" class="note">... and {hidden_count} more unresolved item(s) - '
                "see the SLD readiness manifest for the full register.</text>"
            )
    else:
        parts.append(f'<text x="88" y="{issue_y + 30}" class="cell">No unresolved readiness issue was recorded.</text>')
    parts.append(_status_watermark(str(payload.get("document_status") or "concept"), width=1800, y=issue_y + 80))
    parts.extend(_document_footer(payload=payload, height=height))
    parts.append("</svg>")
    return "".join(parts).encode("utf-8")


def render_concept_interface_scope_svg(payload: dict[str, Any]) -> bytes:
    zones = list(payload.get("scope_zones") or [])
    interfaces = list(payload.get("interface_register") or [])
    height = 1020
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="1800" height="{height}" viewBox="0 0 1800 {height}">',
        "<style>.title{font:700 30px Arial;fill:#fff}.subtitle{font:400 16px Arial;fill:#D7E5F3}.status{font:700 15px Arial;fill:#FFD7D1}.sheet{font:400 14px Arial;fill:#D7E5F3}.section{font:700 18px Arial;fill:#173B63}.note{font:400 14px Arial;fill:#536579}.zone-title{font:700 20px Arial;fill:#173B63}.zone-text{font:400 13px Arial;fill:#243B53}.zone-muted{font:400 12px Arial;fill:#536579}.interface{font:700 13px Arial;fill:#7A271A}.table-head{font:700 13px Arial;fill:#fff}.table-text{font:400 12px Arial;fill:#243B53}.footer{font:400 13px Arial;fill:#334E68}.watermark{font:700 34px Arial;fill:#B42318;fill-opacity:.25}</style>",
        '<rect width="100%" height="100%" fill="#FFFFFF"/>',
        *_document_header(
            title="CONCEPT INTERFACE / SCOPE DIAGRAM",
            subtitle="Electrical interface surfaces and unresolved project boundaries - no contractual responsibility allocation",
            sheet_id="SLD-04",
            payload=payload,
        ),
        '<defs><marker id="arrow" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto"><path d="M0,0 L0,6 L9,3 z" fill="#5B7897"/></marker></defs>',
        '<text x="70" y="160" class="section">Scope architecture</text>',
        f'<text x="70" y="186" class="note">{escape(str(payload.get("scope_status") or ""))}</text>',
    ]
    zone_positions = [(70, "#F8FAFC"), (640, "#EDF5FB"), (1210, "#F8FAFC")]
    for index, (x, fill) in enumerate(zone_positions):
        zone = zones[index] if index < len(zones) else {}
        parts.extend(
            [
                f'<rect x="{x}" y="240" width="520" height="258" rx="8" fill="{fill}" stroke="#9FB8D1" stroke-width="2"/>',
                f'<text x="{x + 24}" y="278" class="zone-title">{escape(str(zone.get("label") or "Interface zone"))}</text>',
                f'<text x="{x + 24}" y="322" class="zone-text">Included: {escape(str(zone.get("included") or ""))}</text>',
                f'<text x="{x + 24}" y="366" class="zone-muted">Excluded: {escape(str(zone.get("excluded") or ""))}</text>',
                f'<text x="{x + 24}" y="428" class="interface">Responsibility: {escape(str(zone.get("responsibility") or ""))}</text>',
            ]
        )
    parts.extend(
        [
            '<line x1="592" y1="369" x2="632" y2="369" stroke="#5B7897" stroke-width="3" marker-end="url(#arrow)"/>',
            '<line x1="1162" y1="369" x2="1202" y2="369" stroke="#5B7897" stroke-width="3" marker-end="url(#arrow)"/>',
            '<text x="612" y="344" text-anchor="middle" class="zone-muted">MV interface</text>',
            '<text x="1182" y="344" text-anchor="middle" class="zone-muted">Project interface</text>',
            '<text x="70" y="562" class="section">Interface register</text>',
            '<rect x="70" y="586" width="1660" height="38" fill="#173B63"/>',
            '<text x="88" y="611" class="table-head">INTERFACE</text>',
            '<text x="560" y="611" class="table-head">VISIBLE IN THIS PACKAGE</text>',
            '<text x="1160" y="611" class="table-head">PROJECT CONFIRMATION REQUIRED</text>',
        ]
    )
    for index, item in enumerate(interfaces[:3]):
        y = 624 + index * 72
        fill = "#F7FAFC" if index % 2 == 0 else "#FFFFFF"
        parts.extend(
            [
                f'<rect x="70" y="{y}" width="1660" height="72" fill="{fill}" stroke="#D8E2EC"/>',
                f'<text x="88" y="{y + 28}" class="table-text">{escape(str(item.get("interface") or ""))}</text>',
                f'<text x="560" y="{y + 28}" class="table-text">{escape(str(item.get("visible_in_package") or ""))}</text>',
                f'<text x="1160" y="{y + 28}" class="table-text">{escape(str(item.get("confirmation_required") or ""))}</text>',
            ]
        )
    parts.append(_status_watermark(str(payload.get("document_status") or "concept"), width=1800, y=850))
    parts.extend(_document_footer(payload=payload, height=height))
    parts.append("</svg>")
    return "".join(parts).encode("utf-8")


def build_sld_proposal_package_artifacts(
    *,
    run_bundle: DcRunBundle,
    ac_snapshot: AcSnapshot,
    formal_readiness: dict[str, Any],
    document_status: str,
    typical_group_index: int,
    svg_to_png,
) -> list[ArtifactPayload]:
    """Build the P1 proposal-package sheets around the typical SLD drawing."""
    site_index = build_site_electrical_index_payload(
        run_bundle=run_bundle,
        ac_snapshot=ac_snapshot,
        document_status=document_status,
        typical_group_index=typical_group_index,
    )
    design_basis = build_design_basis_schedule_payload(
        site_index=site_index,
        ac_snapshot=ac_snapshot,
        formal_readiness=formal_readiness,
        document_status=document_status,
    )
    interface_scope = build_concept_interface_scope_payload(
        site_index=site_index,
        document_status=document_status,
    )
    suffix = {"official": "", "concept": ".concept", "draft_override": ".draft"}.get(document_status, ".concept")
    site_svg = render_site_electrical_index_svg(site_index)
    design_basis_svg = render_design_basis_schedule_svg(design_basis)
    interface_scope_svg = render_concept_interface_scope_svg(interface_scope)
    return [
        ArtifactPayload(
            artifact_kind="site_electrical_index_json",
            file_name=f"site_electrical_index{suffix}.json",
            media_type="application/json",
            content=json_bytes(site_index),
            metadata={"package_sheet": "SLD-01", "package_role": "site_electrical_index"},
        ),
        ArtifactPayload(
            artifact_kind="site_electrical_index_svg",
            file_name=f"site_electrical_index{suffix}.svg",
            media_type="image/svg+xml",
            content=site_svg,
            metadata={"package_sheet": "SLD-01", "package_role": "site_electrical_index"},
        ),
        ArtifactPayload(
            artifact_kind="site_electrical_index_png",
            file_name=f"site_electrical_index{suffix}.png",
            media_type="image/png",
            content=svg_to_png(site_svg),
            metadata={"package_sheet": "SLD-01", "package_role": "site_electrical_index"},
        ),
        ArtifactPayload(
            artifact_kind="sld_design_basis_schedule_json",
            file_name=f"sld_design_basis_schedule{suffix}.json",
            media_type="application/json",
            content=json_bytes(design_basis),
            metadata={"package_sheet": "SLD-03", "package_role": "design_basis_schedule"},
        ),
        ArtifactPayload(
            artifact_kind="sld_design_basis_schedule_svg",
            file_name=f"sld_design_basis_schedule{suffix}.svg",
            media_type="image/svg+xml",
            content=design_basis_svg,
            metadata={"package_sheet": "SLD-03", "package_role": "design_basis_schedule"},
        ),
        ArtifactPayload(
            artifact_kind="sld_design_basis_schedule_png",
            file_name=f"sld_design_basis_schedule{suffix}.png",
            media_type="image/png",
            content=svg_to_png(design_basis_svg),
            metadata={"package_sheet": "SLD-03", "package_role": "design_basis_schedule"},
        ),
        ArtifactPayload(
            artifact_kind="sld_interface_scope_json",
            file_name=f"sld_interface_scope{suffix}.json",
            media_type="application/json",
            content=json_bytes(interface_scope),
            metadata={"package_sheet": "SLD-04", "package_role": "interface_scope"},
        ),
        ArtifactPayload(
            artifact_kind="sld_interface_scope_svg",
            file_name=f"sld_interface_scope{suffix}.svg",
            media_type="image/svg+xml",
            content=interface_scope_svg,
            metadata={"package_sheet": "SLD-04", "package_role": "interface_scope"},
        ),
        ArtifactPayload(
            artifact_kind="sld_interface_scope_png",
            file_name=f"sld_interface_scope{suffix}.png",
            media_type="image/png",
            content=svg_to_png(interface_scope_svg),
            metadata={"package_sheet": "SLD-04", "package_role": "interface_scope"},
        ),
    ]
