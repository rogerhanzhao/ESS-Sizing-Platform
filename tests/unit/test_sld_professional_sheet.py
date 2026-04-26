import inspect

from calb_diagrams.sld_engineering_v2_layout import build_sld_engineering_v2_layout_plan
from calb_diagrams.sld_professional_sheet import build_professional_sld_sheet, compact_voltage_label
from calb_sizing_tool.services.sld_engineering_v2_builder import build_sld_engineering_v2_graph
from tests.unit.test_sld_layout_engine import _build_topology


def _build_sheet(sample_excel_path):
    topology = _build_topology(sample_excel_path)
    graph = build_sld_engineering_v2_graph(topology)
    plan = build_sld_engineering_v2_layout_plan(graph)
    return build_professional_sld_sheet(plan)


def test_professional_sheet_builds_reference_note_panel(sample_excel_path):
    sheet = _build_sheet(sample_excel_path)

    assert sheet.template_id == "professional_sheet_v1"
    assert sheet.notes.title == "Equipment List"
    assert [section.title for section in sheet.notes.sections] == [
        "Cable Connection Vault",
        "Power Cable-33kV",
        "Step-up Transformer (OIL)",
        "Connecting Cable Type",
        "Power Converter System",
        "Power Cable",
        "Battery Energy Storage System",
    ]
    assert sheet.notes.height == 646.0

    pcs_section = sheet.notes.sections[4]
    assert pcs_section.lines == ("PCS-1250kW*4", "AC690V 50Hz, DC1500V")

    bess_section = sheet.notes.sections[6]
    assert bess_section.lines[0].startswith("1~4 BESS (")
    assert bess_section.lines[0].endswith("MWh*4)")


def test_professional_sheet_owns_drawing_geometry(sample_excel_path):
    sheet = _build_sheet(sample_excel_path)

    assert sheet.mv.ring_in_x < sheet.mv.center_x < sheet.mv.ring_out_x
    assert sheet.mv.bus_y < sheet.mv.transformer_y < sheet.mv.lv_bus_y
    assert sheet.lvdc.bus_x1 < sheet.lvdc.bus_x2
    assert sheet.lvdc.pcs_y < sheet.lvdc.dc_device_y < sheet.lvdc.block_y
    assert sheet.lvdc.converter_width > 0
    assert sheet.lvdc.battery_height > sheet.lvdc.converter_height


def test_professional_sheet_source_is_layout_only():
    source = inspect.getsource(build_professional_sld_sheet)

    assert "SldTopology" not in source
    assert "SldEngineeringV2Graph" not in source
    assert "ac_output" not in source
    assert "stage13_output" not in source
    assert "session_state" not in source
    assert "st.session_state" not in source


def test_compact_voltage_label_keeps_visible_voltage_not_equipment_class():
    assert compact_voltage_label("33.0 kV") == "33kV"
    assert compact_voltage_label("690.0 V") == "690V"
