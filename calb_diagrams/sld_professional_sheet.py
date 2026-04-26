from __future__ import annotations

from dataclasses import dataclass

from calb_diagrams.sld_engineering_v2_layout import SldV2LayoutBox, SldV2LayoutPlan


@dataclass(frozen=True)
class ProfessionalNotesSection:
    title: str
    lines: tuple[str, ...]
    height: float


@dataclass(frozen=True)
class ProfessionalNotesPanel:
    x: float
    y: float
    width: float
    title: str
    sections: tuple[ProfessionalNotesSection, ...]

    @property
    def height(self) -> float:
        return sum(section.height for section in self.sections)


@dataclass(frozen=True)
class ProfessionalMvGeometry:
    main_left: float
    main_right: float
    center_x: float
    ring_in_x: float
    ring_out_x: float
    top_y: float
    bus_y: float
    transformer_y: float
    lv_bus_y: float


@dataclass(frozen=True)
class ProfessionalLvDcGeometry:
    bus_x1: float
    bus_x2: float
    pcs_y: float
    dc_device_y: float
    block_y: float
    converter_width: float
    converter_height: float
    battery_width: float
    battery_height: float
    multi_block_spacing_base: float
    multi_block_spacing_max: float


@dataclass(frozen=True)
class ProfessionalSldSheet:
    template_id: str
    width: int
    height: int
    notes: ProfessionalNotesPanel
    mv: ProfessionalMvGeometry
    lvdc: ProfessionalLvDcGeometry


def boxes_by_type(plan: SldV2LayoutPlan, node_type: str) -> list[SldV2LayoutBox]:
    return sorted(
        [box for box in plan.boxes if box.node_type == node_type],
        key=lambda box: (box.feeder_index or 0, box.dc_block_index or 0, box.node_id),
    )


def first_box(plan: SldV2LayoutPlan, node_type: str) -> SldV2LayoutBox | None:
    boxes = boxes_by_type(plan, node_type)
    return boxes[0] if boxes else None


def equipment_row_map(plan: SldV2LayoutPlan) -> dict[str, str]:
    return {row.item: row.spec for row in plan.equipment_rows}


def format_number(value: object, *, decimals: int = 0) -> str:
    try:
        number = float(value)  # type: ignore[arg-type]
    except Exception:
        return "TBD"
    if decimals <= 0:
        return f"{number:.0f}"
    return f"{number:.{decimals}f}"


def compact_voltage_label(text: str) -> str:
    cleaned = str(text or "").replace(" ", "")
    if cleaned.endswith(".0kV"):
        cleaned = cleaned.replace(".0kV", "kV")
    if cleaned.endswith(".0V"):
        cleaned = cleaned.replace(".0V", "V")
    return cleaned or "TBD"


def build_professional_sld_sheet(plan: SldV2LayoutPlan) -> ProfessionalSldSheet:
    """Build the professional drawing sheet contract consumed by the renderer.

    This layer owns sheet-level engineering presentation: the left note panel,
    MV/RMU reference geometry, LV busbar span, and PCS-to-DC drawing cadence.
    It intentionally consumes only the resolved layout plan.
    """

    rows = equipment_row_map(plan)
    pcs_boxes = boxes_by_type(plan, "pcs")
    dc_blocks = boxes_by_type(plan, "dc_block")
    transformer = first_box(plan, "transformer")
    first_pcs = pcs_boxes[0] if pcs_boxes else None
    first_dc = dc_blocks[0] if dc_blocks else None

    pcs_rating = format_number((first_pcs.attributes if first_pcs else {}).get("pcs_rating_kw"), decimals=0)
    lv_voltage = format_number((first_pcs.attributes if first_pcs else {}).get("lv_voltage_v_ll"), decimals=0)
    frequency = format_number((first_pcs.attributes if first_pcs else {}).get("project_frequency_hz"), decimals=0)
    dc_voltage = format_number((first_pcs.attributes if first_pcs else {}).get("dc_block_voltage_v"), decimals=0)
    dc_energy = first_dc.text_lines[1] if first_dc and len(first_dc.text_lines) > 1 else "TBD"
    rmu = rows.get("MV Switchgear / RMU", "TBD")
    ct = rows.get("MV CT", "TBD")
    transformer_lines = tuple(transformer.text_lines[1:] if transformer else ())
    if not transformer_lines:
        transformer_lines = (rows.get("Transformer", "TBD"),)

    notes_sections = (
        ProfessionalNotesSection(
            "Cable Connection Vault",
            (
                f"CB:{rmu}",
                f"DS:{rmu}",
                f"CT:{ct}",
                "With DC, ES, & Live Displayer",
            ),
            166.0,
        ),
        ProfessionalNotesSection(
            f"Power Cable-{compact_voltage_label(rows.get('MV System', 'MV'))}",
            (rows.get("MV Cable", "MISSING: MV cable spec"),),
            60.0,
        ),
        ProfessionalNotesSection("Step-up Transformer (OIL)", transformer_lines, 92.0),
        ProfessionalNotesSection(
            "Connecting Cable Type",
            (rows.get("LV Cable", "MISSING: LV cable spec"),),
            60.0,
        ),
        ProfessionalNotesSection(
            "Power Converter System",
            (
                f"PCS-{pcs_rating}kW*{len(pcs_boxes)}",
                f"AC{lv_voltage}V {frequency}Hz, DC{dc_voltage}V",
            ),
            96.0,
        ),
        ProfessionalNotesSection("Power Cable", (rows.get("DC Cable", "MISSING: DC cable spec"),), 60.0),
        ProfessionalNotesSection(
            "Battery Energy Storage System",
            (
                f"1~{len(dc_blocks)} BESS ({dc_energy}*{len(dc_blocks)})"
                if len(dc_blocks) > 1
                else f"1 BESS ({dc_energy})",
                f"Cell: {rows.get('BESS Cell', 'MISSING: BESS cell spec')}",
            ),
            112.0,
        ),
    )

    main_left = 540.0
    main_right = 1700.0
    center_x = (main_left + main_right) / 2.0
    mv = ProfessionalMvGeometry(
        main_left=main_left,
        main_right=main_right,
        center_x=center_x,
        ring_in_x=center_x - 205.0,
        ring_out_x=center_x + 205.0,
        top_y=62.0,
        bus_y=270.0,
        transformer_y=440.0,
        lv_bus_y=540.0,
    )

    centers = [box.x + box.width / 2.0 for box in pcs_boxes]
    if centers:
        bus_x1 = min(centers) - 130.0
        bus_x2 = max(centers) + 130.0
    else:
        bus_x1 = mv.main_left
        bus_x2 = mv.main_right

    lvdc = ProfessionalLvDcGeometry(
        bus_x1=bus_x1,
        bus_x2=bus_x2,
        pcs_y=mv.lv_bus_y + 54.0,
        dc_device_y=mv.lv_bus_y + 166.0,
        block_y=mv.lv_bus_y + 244.0,
        converter_width=72.0,
        converter_height=52.0,
        battery_width=96.0,
        battery_height=78.0,
        multi_block_spacing_base=112.0,
        multi_block_spacing_max=132.0,
    )

    return ProfessionalSldSheet(
        template_id="professional_sheet_v1",
        width=plan.width,
        height=plan.height,
        notes=ProfessionalNotesPanel(
            x=38.0,
            y=40.0,
            width=424.0,
            title="Equipment List",
            sections=notes_sections,
        ),
        mv=mv,
        lvdc=lvdc,
    )
