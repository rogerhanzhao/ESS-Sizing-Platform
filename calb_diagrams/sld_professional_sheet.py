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
class ProfessionalTitleBlock:
    """Geometry for the ANSI-style title block at the bottom of the drawing."""
    x: float
    y: float
    width: float
    height: float
    # Column boundaries (x coordinates of dividers)
    desc_col_right: float   # end of main description column
    drg_col_right: float    # end of drawing-number column
    rev_col_right: float    # end of revision column
    # Populated drawing fields
    drawing_title: str
    drawing_subtitle: str
    drg_number: str
    revision: str
    scale: str
    date: str


@dataclass(frozen=True)
class ProfessionalSldSheet:
    template_id: str
    width: int
    height: int
    notes: ProfessionalNotesPanel
    mv: ProfessionalMvGeometry
    lvdc: ProfessionalLvDcGeometry
    title_block: ProfessionalTitleBlock


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
                f"CB: {rmu}",
                f"DS: {rmu}",
                f"CT: {ct}",
                "With DC, ES, & Live Displayer",
            ),
            166.0,
        ),
        ProfessionalNotesSection(
            f"Power Cable — {compact_voltage_label(rows.get('MV System', 'MV'))}",
            (rows.get("MV Cable", "MISSING: MV cable spec"),),
            60.0,
        ),
        ProfessionalNotesSection("Step-up Transformer (OIL)", transformer_lines, 92.0),
        ProfessionalNotesSection(
            "LV Connecting Cable",
            (rows.get("LV Cable", "MISSING: LV cable spec"),),
            60.0,
        ),
        ProfessionalNotesSection(
            "Power Converter System (PCS)",
            (
                f"PCS — {pcs_rating} kW × {len(pcs_boxes)}",
                f"AC {lv_voltage} V  {frequency} Hz  DC {dc_voltage} V",
            ),
            96.0,
        ),
        ProfessionalNotesSection("DC Power Cable", (rows.get("DC Cable", "MISSING: DC cable spec"),), 60.0),
        ProfessionalNotesSection(
            "Battery Energy Storage System",
            (
                f"{len(dc_blocks)} BESS containers ({dc_energy} × {len(dc_blocks)})"
                if len(dc_blocks) > 1
                else f"1 BESS container ({dc_energy})",
                f"Cell: {rows.get('BESS Cell', 'MISSING: BESS cell spec')}",
            ),
            112.0,
        ),
    )

    # MV geometry — calibrated to layout box positions:
    # rmu_x = ac_section.x(495) + 312 = 807
    # bay_w = 620/3 = 206.67
    # ring_in center_x  = 807 + 103.33 = 910.33
    # tx_center_x       = 807 + 206.67 + 103.33 = 1117
    # ring_out center_x = 807 + 413.33 + 103.33 = 1323.67
    main_left = 495.0
    main_right = 1960.0
    center_x = 1117.0
    mv = ProfessionalMvGeometry(
        main_left=main_left,
        main_right=main_right,
        center_x=center_x,
        ring_in_x=910.0,
        ring_out_x=1324.0,
        top_y=62.0,
        bus_y=290.0,
        transformer_y=480.0,
        lv_bus_y=610.0,
    )

    centers = [box.x + box.width / 2.0 for box in pcs_boxes]
    if centers:
        bus_x1 = min(centers) - 140.0
        bus_x2 = max(centers) + 140.0
    else:
        bus_x1 = mv.main_left
        bus_x2 = mv.main_right

    lvdc = ProfessionalLvDcGeometry(
        bus_x1=bus_x1,
        bus_x2=bus_x2,
        pcs_y=mv.lv_bus_y + 90.0,
        dc_device_y=mv.lv_bus_y + 195.0,
        block_y=mv.lv_bus_y + 260.0,
        converter_width=80.0,
        converter_height=60.0,
        battery_width=90.0,
        battery_height=70.0,
        multi_block_spacing_base=104.0,
        multi_block_spacing_max=128.0,
    )

    # Title block: flush with outer-border bottom (border = plan.height − 20)
    tb_y = float(plan.height) - 120.0
    tb_w = float(plan.width) - 80.0  # leave margins
    tb_x = 40.0
    mv_sys = compact_voltage_label(rows.get("MV System", ""))
    tx_mva = rows.get("Transformer", "")
    drawing_title = "SINGLE LINE DIAGRAM — BATTERY ENERGY STORAGE SYSTEM (BESS)"
    drawing_subtitle = f"{mv_sys} MV Grid Connection  |  {tx_mva}" if mv_sys else tx_mva

    title_block = ProfessionalTitleBlock(
        x=tb_x,
        y=tb_y,
        width=tb_w,
        height=100.0,
        desc_col_right=tb_x + tb_w * 0.56,
        drg_col_right=tb_x + tb_w * 0.72,
        rev_col_right=tb_x + tb_w * 0.82,
        drawing_title=drawing_title,
        drawing_subtitle=drawing_subtitle,
        drg_number="SLD-BESS-001",
        revision="A",
        scale="NTS",
        date="",
    )

    return ProfessionalSldSheet(
        template_id="professional_sheet_v2",
        width=plan.width,
        height=plan.height,
        notes=ProfessionalNotesPanel(
            x=38.0,
            y=40.0,
            width=424.0,
            title="EQUIPMENT LIST",
            sections=notes_sections,
        ),
        mv=mv,
        lvdc=lvdc,
        title_block=title_block,
    )
