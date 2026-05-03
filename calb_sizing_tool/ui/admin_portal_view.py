"""Admin-only product and database management portal."""
from __future__ import annotations

from typing import Any

import streamlit as st

from calb_sizing_tool.services.product_admin_service import ProductAdminService
from calb_sizing_tool.state.auth_state import get_auth_context

_SECTIONS = [
    ("Overview", "Dashboard"),
    ("Cell Products", "Cells"),
    ("DC Block Templates", "DC Blocks"),
    ("AC Block Templates", "AC Blocks"),
    ("Product Assets", "Assets"),
    ("Degradation Library", "Degradation"),
    ("RTE Library", "RTE"),
    ("Plugin Registry", "Plugins"),
]

_ADMIN_NAV_KEY = "admin_portal_section"


def show() -> None:
    auth_context = get_auth_context()
    if auth_context is None or not auth_context.is_admin:
        st.error("Admin access required.")
        return

    service = ProductAdminService()
    snapshot = _load_snapshot(service)

    st.markdown(
        """
        <style>
        div[data-testid="stHorizontalBlock"]:first-of-type
          > div[data-testid="column"]:first-child
          > div[data-testid="stVerticalBlock"] {
            background: #F4F7FB;
            border-right: 2px solid #C2D3E8;
            border-radius: 0;
            padding: 0.25rem 0.5rem 0 !important;
            min-height: 80vh;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        '<h2 style="color:#1A2635;font-size:1.2rem;font-weight:700;margin-bottom:0.25rem">'
        "Product &amp; Database</h2>",
        unsafe_allow_html=True,
    )
    st.caption("Admin-only product libraries, performance data, and simulation plugin management.")
    st.divider()

    nav_col, content_col = st.columns([1, 4])

    with nav_col:
        section_labels = [label for _, label in _SECTIONS]
        selected_label = st.radio(
            "Section",
            section_labels,
            key=_ADMIN_NAV_KEY,
            label_visibility="collapsed",
        )
        selected = next(name for name, label in _SECTIONS if label == selected_label)

    with content_col:
        if selected == "Overview":
            _section_overview(snapshot)
        elif selected == "Cell Products":
            _section_cell_products(service, snapshot)
        elif selected == "DC Block Templates":
            _section_dc_block(service, snapshot)
        elif selected == "AC Block Templates":
            _section_ac_block(service, snapshot)
        elif selected == "Product Assets":
            _section_assets(service, snapshot)
        elif selected == "Degradation Library":
            _section_degradation(service, snapshot)
        elif selected == "RTE Library":
            _section_rte(service, snapshot)
        elif selected == "Plugin Registry":
            _section_plugins(service, snapshot)


@st.cache_data(ttl=5)
def _cached_snapshot() -> dict[str, Any]:
    return ProductAdminService().snapshot()


def _load_snapshot(service: ProductAdminService) -> dict[str, Any]:
    # Keep a service argument in call sites so tests can replace this later.
    _ = service
    return _cached_snapshot()


def _refresh() -> None:
    _cached_snapshot.clear()
    st.rerun()


def _rows(items: list[Any], fields: list[tuple[str, str]]) -> list[dict[str, Any]]:
    return [{label: _value(item, attr) for label, attr in fields} for item in items]


def _cell_options(cells: list[Any]) -> dict[str, str | None]:
    options: dict[str, str | None] = {"No linked cell": None}
    for cell in cells:
        options[f"{_value(cell, 'cell_code')} - {_value(cell, 'model_name')}"] = _value(cell, "product_cell_id")
    return options


def _asset_owner_options(snapshot: dict[str, Any]) -> dict[str, tuple[str, str | None, str]]:
    options: dict[str, tuple[str, str | None, str]] = {}
    for cell in snapshot["cells"]:
        code = str(cell.get("cell_code") or "")
        options[f"Cell - {code}"] = ("product_cell", cell.get("product_cell_id"), code)
    for block in snapshot["dc_blocks"]:
        code = str(block.get("block_code") or "")
        options[f"DC Block - {code}"] = ("product_dc_block", block.get("product_dc_block_id"), code)
    for block in snapshot["ac_blocks"]:
        code = str(block.get("block_code") or "")
        options[f"AC Block - {code}"] = ("product_ac_block", block.get("product_ac_block_id"), code)
    if not options:
        options["Manual owner"] = ("manual", None, "")
    return options


def _value(item: Any, attr: str) -> Any:
    if isinstance(item, dict):
        return item.get(attr)
    return getattr(item, attr)


def _display_options(items: list[dict[str, Any]], id_field: str, fields: list[str]) -> dict[str, str]:
    options: dict[str, str] = {}
    for item in items:
        label_parts = [str(item.get(field) or "") for field in fields]
        label = " - ".join(part for part in label_parts if part).strip() or str(item.get(id_field))
        options[label] = str(item[id_field])
    return options


def _record_by_id(items: list[dict[str, Any]], id_field: str, record_id: str) -> dict[str, Any] | None:
    return next((item for item in items if str(item.get(id_field)) == record_id), None)


def _optional_float(value: Any) -> float:
    return float(value or 0.0)


def _optional_int(value: Any) -> int:
    return int(value or 0)


def _render_edit_form(
    *,
    service: ProductAdminService,
    title: str,
    entity: str,
    items: list[dict[str, Any]],
    id_field: str,
    label_fields: list[str],
    specs: list[dict[str, Any]],
    cells: list[dict[str, Any]] | None = None,
) -> None:
    if not items:
        return

    with st.expander(f"Edit Selected {title}", expanded=False):
        options = _display_options(items, id_field, label_fields)
        selected_label = st.selectbox("Record", list(options.keys()), key=f"edit_{entity}_record")
        record_id = options[selected_label]
        record = _record_by_id(items, id_field, record_id)
        if record is None:
            st.warning("Selected record is no longer available.")
            return

        with st.form(f"admin_edit_{entity}"):
            values: dict[str, Any] = {}
            for spec in specs:
                key = spec["key"]
                label = spec["label"]
                kind = spec.get("kind", "text")
                current = record.get(key)
                if kind == "text":
                    values[key] = st.text_input(label, value=str(current or ""))
                elif kind == "textarea":
                    values[key] = st.text_area(label, value=str(current or ""), height=70)
                elif kind == "float":
                    values[key] = st.number_input(label, value=_optional_float(current), step=float(spec.get("step", 1.0)))
                elif kind == "int":
                    values[key] = st.number_input(label, value=_optional_int(current), min_value=0, step=1)
                elif kind == "select":
                    choices = spec["choices"]
                    index = choices.index(current) if current in choices else 0
                    values[key] = st.selectbox(label, choices, index=index, key=f"edit_{entity}_{key}")
                elif kind == "cell":
                    cell_map = _cell_options(cells or [])
                    reverse = {value: label for label, value in cell_map.items()}
                    current_label = reverse.get(current, "No linked cell")
                    labels = list(cell_map.keys())
                    values[key] = cell_map[
                        st.selectbox(
                            label,
                            labels,
                            index=labels.index(current_label) if current_label in labels else 0,
                            key=f"edit_{entity}_{key}",
                        )
                    ]
                elif kind == "bool":
                    values[key] = st.checkbox(label, value=bool(current))

            c1, c2 = st.columns(2)
            values["is_active"] = c1.checkbox("Active", value=bool(record.get("is_active", True)))
            values["is_published"] = c2.checkbox("Published", value=bool(record.get("is_published", False)))

            if st.form_submit_button("Save Changes", use_container_width=True):
                cleaned = {
                    key: (value.strip() if isinstance(value, str) else value)
                    for key, value in values.items()
                }
                ok = service.update_record(entity, record_id, cleaned)
                if ok:
                    st.success("Record updated.")
                    _refresh()
                else:
                    st.error("Record update failed.")


def _section_overview(snapshot: dict[str, Any]) -> None:
    st.subheader("Overview")
    st.caption("Phase B product database status.")
    counts = snapshot["counts"]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Cell Products", counts["product_cell"])
    c2.metric("DC Block Templates", counts["product_dc_block"])
    c3.metric("AC Block Templates", counts["product_ac_block"])
    c4.metric("Product Assets", counts["product_asset"])
    c5, c6, c7 = st.columns(3)
    c5.metric("Degradation Curves", counts["degradation_curve"])
    c6.metric("RTE Curves", counts["rte_curve"])
    c7.metric("Plugins", counts["degradation_plugin"])

    st.markdown("---")
    st.info(
        "These Phase B tables are independent from the legacy imported master-data tables. "
        "They are the maintained source for Admin Portal product records."
    )


def _section_cell_products(service: ProductAdminService, snapshot: dict[str, Any]) -> None:
    st.subheader("Cell Products")
    st.caption("LFP, NMC and other cell models with electrical, dimensional and density data.")

    st.dataframe(
        _rows(
            snapshot["cells"],
            [
                ("Code", "cell_code"),
                ("Model", "model_name"),
                ("Chemistry", "chemistry"),
                ("Ah", "nominal_capacity_ah"),
                ("Wh", "rated_energy_wh"),
                ("V nom.", "nominal_voltage_v"),
                ("Efficiency %", "energy_efficiency_pct"),
                ("Cycle life", "cycle_life_cycles"),
                ("Weight kg", "weight_kg"),
                ("Process", "manufacturing_process"),
                ("Manufacturer", "manufacturer"),
                ("Active", "is_active"),
            ],
        ),
        use_container_width=True,
        hide_index=True,
    )

    _render_edit_form(
        service=service,
        title="Cell Product",
        entity="cell",
        items=snapshot["cells"],
        id_field="product_cell_id",
        label_fields=["cell_code", "model_name"],
        specs=[
            {"key": "model_name", "label": "Model Name"},
            {"key": "chemistry", "label": "Chemistry", "kind": "select", "choices": ["LFP", "NMC", "NCA", "LTO", "Other"]},
            {"key": "manufacturer", "label": "Manufacturer"},
            {"key": "nominal_capacity_ah", "label": "Ah nominal", "kind": "float", "step": 1.0},
            {"key": "shipping_capacity_ah", "label": "Ah shipping", "kind": "float", "step": 1.0},
            {"key": "nominal_voltage_v", "label": "V nominal", "kind": "float", "step": 0.01},
            {"key": "min_voltage_v", "label": "V min", "kind": "float", "step": 0.01},
            {"key": "max_voltage_v", "label": "V max", "kind": "float", "step": 0.01},
            {"key": "rated_energy_wh", "label": "Rated Wh", "kind": "float", "step": 1.0},
            {"key": "length_mm", "label": "Length mm", "kind": "float", "step": 1.0},
            {"key": "width_mm", "label": "Width / Thickness mm", "kind": "float", "step": 0.1},
            {"key": "height_mm", "label": "Total Height mm", "kind": "float", "step": 0.1},
            {"key": "shoulder_height_mm", "label": "Shoulder Height mm", "kind": "float", "step": 0.1},
            {"key": "weight_kg", "label": "Weight kg", "kind": "float", "step": 0.01},
            {"key": "volume_l", "label": "Volume L", "kind": "float", "step": 0.01},
            {"key": "gravimetric_density_wh_kg", "label": "Wh/kg", "kind": "float", "step": 1.0},
            {"key": "volumetric_density_wh_l", "label": "Wh/L", "kind": "float", "step": 1.0},
            {"key": "energy_efficiency_pct", "label": "Energy Efficiency %", "kind": "float", "step": 0.1},
            {"key": "dcr_mohm", "label": "DCR mOhm", "kind": "float", "step": 0.01},
            {"key": "rated_c_rate_label", "label": "Rated C/P Label"},
            {"key": "cycle_life_cycles", "label": "Cycle Life", "kind": "int"},
            {"key": "cycle_life_rate_label", "label": "Cycle Life Rate Label"},
            {"key": "cycle_life_dod_pct", "label": "Cycle Life DoD %", "kind": "float", "step": 1.0},
            {"key": "end_of_life_soh_pct", "label": "EOL SoH %", "kind": "float", "step": 1.0},
            {"key": "manufacturing_process", "label": "Manufacturing Process"},
            {"key": "launch_year", "label": "Launch Year", "kind": "int"},
            {"key": "notes", "label": "Notes", "kind": "textarea"},
        ],
    )

    with st.expander("Add Cell Product", expanded=False):
        with st.form("admin_add_product_cell"):
            c1, c2, c3 = st.columns(3)
            cell_code = c1.text_input("Cell Code")
            model_name = c2.text_input("Model Name")
            chemistry = c3.selectbox("Chemistry", ["LFP", "NMC", "NCA", "LTO", "Other"])
            c4, c5, c6, c7 = st.columns(4)
            nominal_capacity_ah = c4.number_input("Ah nominal", min_value=0.0, step=1.0)
            shipping_capacity_ah = c5.number_input("Ah shipping", min_value=0.0, step=1.0)
            nominal_voltage_v = c6.number_input("V nominal", min_value=0.0, step=0.01)
            rated_energy_wh = c7.number_input("Rated Wh", min_value=0.0, step=1.0)
            d1, d2, d3, d4 = st.columns(4)
            length_mm = d1.number_input("Length mm", min_value=0.0, step=1.0)
            width_mm = d2.number_input("Width / Thickness mm", min_value=0.0, step=0.1)
            height_mm = d3.number_input("Height mm", min_value=0.0, step=1.0)
            shoulder_height_mm = d4.number_input("Shoulder Height mm", min_value=0.0, step=0.1)
            e1, e2, e3, e4 = st.columns(4)
            weight_kg = e1.number_input("Weight kg", min_value=0.0, step=0.01)
            volume_l = e2.number_input("Volume L", min_value=0.0, step=0.01)
            gravimetric_density_wh_kg = e3.number_input("Wh/kg", min_value=0.0, step=1.0)
            volumetric_density_wh_l = e4.number_input("Wh/L", min_value=0.0, step=1.0)
            f1, f2, f3, f4 = st.columns(4)
            energy_efficiency_pct = f1.number_input("Energy Efficiency %", min_value=0.0, step=0.1)
            dcr_mohm = f2.number_input("DCR mOhm", min_value=0.0, step=0.01)
            cycle_life_cycles = f3.number_input("Cycle Life", min_value=0, step=100)
            end_of_life_soh_pct = f4.number_input("EOL SoH %", min_value=0.0, max_value=100.0, step=1.0)
            g1, g2, g3 = st.columns(3)
            rated_c_rate_label = g1.text_input("Rated C/P Label")
            cycle_life_rate_label = g2.text_input("Cycle Life Rate Label")
            manufacturing_process = g3.text_input("Manufacturing Process")
            h1, h2 = st.columns(2)
            cycle_life_dod_pct = h1.number_input("Cycle Life DoD %", min_value=0.0, max_value=100.0, step=1.0)
            launch_year = h2.number_input("Launch Year", min_value=0, step=1)
            manufacturer = st.text_input("Manufacturer")
            notes = st.text_area("Notes", height=70)
            if st.form_submit_button("Save Cell Product", use_container_width=True):
                if not cell_code.strip() or not model_name.strip():
                    st.error("Cell Code and Model Name are required.")
                else:
                    service.create_cell(
                        {
                            "cell_code": cell_code.strip(),
                            "model_name": model_name.strip(),
                            "chemistry": chemistry,
                            "manufacturer": manufacturer.strip() or None,
                            "nominal_capacity_ah": nominal_capacity_ah or None,
                            "shipping_capacity_ah": shipping_capacity_ah or None,
                            "nominal_voltage_v": nominal_voltage_v or None,
                            "rated_energy_wh": rated_energy_wh or None,
                            "length_mm": length_mm or None,
                            "width_mm": width_mm or None,
                            "height_mm": height_mm or None,
                            "shoulder_height_mm": shoulder_height_mm or None,
                            "weight_kg": weight_kg or None,
                            "volume_l": volume_l or None,
                            "gravimetric_density_wh_kg": gravimetric_density_wh_kg or None,
                            "volumetric_density_wh_l": volumetric_density_wh_l or None,
                            "energy_efficiency_pct": energy_efficiency_pct or None,
                            "dcr_mohm": dcr_mohm or None,
                            "rated_c_rate_label": rated_c_rate_label.strip() or None,
                            "cycle_life_cycles": int(cycle_life_cycles) or None,
                            "cycle_life_rate_label": cycle_life_rate_label.strip() or None,
                            "cycle_life_dod_pct": cycle_life_dod_pct or None,
                            "end_of_life_soh_pct": end_of_life_soh_pct or None,
                            "manufacturing_process": manufacturing_process.strip() or None,
                            "launch_year": int(launch_year) or None,
                            "notes": notes.strip() or None,
                        }
                    )
                    st.success("Cell product saved.")
                    _refresh()


def _section_dc_block(service: ProductAdminService, snapshot: dict[str, Any]) -> None:
    st.subheader("DC Block Templates")
    st.caption("String/rack/container templates linked to maintained cell products.")

    st.dataframe(
        _rows(
            snapshot["dc_blocks"],
            [
                ("Code", "block_code"),
                ("Name", "block_name"),
                ("Form", "block_form"),
                ("Model", "product_model"),
                ("kWh", "rated_capacity_kwh"),
                ("Series", "cells_in_series"),
                ("Parallel", "strings_in_parallel"),
                ("Racks", "racks_per_block"),
                ("Packs", "pack_count"),
                ("Config", "configuration"),
                ("Gross MWh", "gross_energy_mwh"),
                ("V nom.", "nominal_voltage_v"),
                ("Thermal", "thermal_management"),
                ("Published", "is_published"),
                ("Active", "is_active"),
            ],
        ),
        use_container_width=True,
        hide_index=True,
    )

    _render_edit_form(
        service=service,
        title="DC Block Template",
        entity="dc_block",
        items=snapshot["dc_blocks"],
        id_field="product_dc_block_id",
        label_fields=["block_code", "block_name"],
        cells=snapshot["cells"],
        specs=[
            {"key": "block_name", "label": "Block Name"},
            {"key": "block_form", "label": "Block Form (sizing)", "kind": "select", "choices": ["container", "cabinet"]},
            {"key": "product_model", "label": "Product Model"},
            {"key": "product_cell_id", "label": "Linked Cell", "kind": "cell"},
            {"key": "cells_in_series", "label": "Cells in Series", "kind": "int"},
            {"key": "strings_in_parallel", "label": "Strings in Parallel", "kind": "int"},
            {"key": "racks_per_block", "label": "Racks per Block", "kind": "int"},
            {"key": "packs_per_rack", "label": "Packs per Rack", "kind": "int"},
            {"key": "racks_per_container", "label": "Racks per Container", "kind": "int"},
            {"key": "pack_count", "label": "Pack Count", "kind": "int"},
            {"key": "container_count", "label": "Container Count", "kind": "int"},
            {"key": "configuration", "label": "Configuration"},
            {"key": "container_type", "label": "Container / Cabinet Type"},
            {"key": "thermal_management", "label": "Thermal Management"},
            {"key": "enclosure", "label": "Enclosure"},
            {"key": "gross_energy_mwh", "label": "Gross MWh", "kind": "float", "step": 0.1},
            {"key": "usable_energy_mwh", "label": "Usable MWh", "kind": "float", "step": 0.1},
            {"key": "rated_capacity_kwh", "label": "Rated kWh", "kind": "float", "step": 1.0},
            {"key": "nominal_voltage_v", "label": "Nominal V", "kind": "float", "step": 1.0},
            {"key": "voltage_min_v", "label": "Min V", "kind": "float", "step": 1.0},
            {"key": "voltage_max_v", "label": "Max V", "kind": "float", "step": 1.0},
            {"key": "nominal_power_kw", "label": "Nominal Power kW", "kind": "float", "step": 1.0},
            {"key": "max_current_a", "label": "Max Current A", "kind": "float", "step": 1.0},
            {"key": "max_c_rate", "label": "Max C-rate", "kind": "float", "step": 0.1},
            {"key": "charge_discharge_rate", "label": "CH/DCH Rate"},
            {"key": "dod_pct", "label": "DoD %", "kind": "float", "step": 1.0},
            {"key": "cycle_life_cycles", "label": "Cycle Life", "kind": "int"},
            {"key": "end_of_life_soh_pct", "label": "EOL SoH %", "kind": "float", "step": 1.0},
            {"key": "service_life_years", "label": "Service Life Years", "kind": "float", "step": 1.0},
            {"key": "system_efficiency_pct", "label": "System Efficiency %", "kind": "float", "step": 0.1},
            {"key": "dimension_width_mm", "label": "Width mm", "kind": "float", "step": 1.0},
            {"key": "dimension_depth_mm", "label": "Depth / Length mm", "kind": "float", "step": 1.0},
            {"key": "dimension_height_mm", "label": "Height mm", "kind": "float", "step": 1.0},
            {"key": "weight_kg", "label": "Weight kg", "kind": "float", "step": 1.0},
            {"key": "ingress_protection", "label": "Ingress Protection"},
            {"key": "relative_humidity", "label": "Relative Humidity"},
            {"key": "working_temp_min_c", "label": "Work Temp Min C", "kind": "float", "step": 1.0},
            {"key": "working_temp_max_c", "label": "Work Temp Max C", "kind": "float", "step": 1.0},
            {"key": "storage_temp_min_c", "label": "Storage Temp Min C", "kind": "float", "step": 1.0},
            {"key": "storage_temp_max_c", "label": "Storage Temp Max C", "kind": "float", "step": 1.0},
            {"key": "altitude_m", "label": "Altitude m", "kind": "float", "step": 100.0},
            {"key": "bms_communication", "label": "BMS Communication"},
            {"key": "compliance_standards", "label": "Compliance Standards", "kind": "textarea"},
            {"key": "seismic_rating", "label": "Seismic Rating"},
            {"key": "coating", "label": "Painting / Coating"},
            {"key": "firefighting_system", "label": "Firefighting System", "kind": "textarea"},
            {"key": "explosion_protection", "label": "Explosion Protection", "kind": "textarea"},
            {"key": "default_degradation_curve_code", "label": "Default Degradation Curve Code"},
            {"key": "notes", "label": "Notes", "kind": "textarea"},
        ],
    )

    with st.expander("Add DC Block Template", expanded=False):
        with st.form("admin_add_product_dc_block"):
            c1, c2, c3 = st.columns(3)
            block_code = c1.text_input("Block Code")
            block_name = c2.text_input("Block Name")
            block_form = c3.selectbox("Block Form (sizing)", ["container", "cabinet"],
                                      help="Used by the DC sizing pipeline: 'container' = 20ft BESS unit, 'cabinet' = indoor rack cabinet")
            product_model = st.text_input("Product Model")
            cell_map = _cell_options(snapshot["cells"])
            cell_label = st.selectbox("Linked Cell", list(cell_map.keys()))
            d1, d2, d3, d4 = st.columns(4)
            cells_in_series = d1.number_input("Cells in Series", min_value=0, step=1)
            strings_in_parallel = d2.number_input("Strings in Parallel", min_value=0, step=1)
            racks_per_block = d3.number_input("Racks per Block", min_value=0, step=1)
            pack_count = d4.number_input("Pack Count", min_value=0, step=1)
            e1, e2, e3, e4 = st.columns(4)
            packs_per_rack = e1.number_input("Packs per Rack", min_value=0, step=1)
            racks_per_container = e2.number_input("Racks per Container", min_value=0, step=1)
            container_count = e3.number_input("Container Count", min_value=0, step=1)
            configuration = e4.text_input("Configuration")
            f1, f2, f3, f4 = st.columns(4)
            container_type = f1.text_input("Container / Cabinet Type")
            thermal_management = f2.text_input("Thermal Management")
            enclosure = f3.text_input("Enclosure")
            ingress_protection = f4.text_input("Ingress Protection")
            g1, g2, g3, g4 = st.columns(4)
            gross_energy_mwh = g1.number_input("Gross MWh", min_value=0.0, step=0.1)
            rated_capacity_kwh = g2.number_input("Rated kWh", min_value=0.0, step=1.0)
            nominal_voltage_v = g3.number_input("Nominal V", min_value=0.0, step=1.0)
            max_c_rate = g4.number_input("Max C-rate", min_value=0.0, step=0.1)
            h1, h2, h3, h4 = st.columns(4)
            voltage_min_v = h1.number_input("Min V", min_value=0.0, step=1.0)
            voltage_max_v = h2.number_input("Max V", min_value=0.0, step=1.0)
            nominal_power_kw = h3.number_input("Nominal Power kW", min_value=0.0, step=1.0)
            max_current_a = h4.number_input("Max Current A", min_value=0.0, step=1.0)
            i1, i2, i3, i4 = st.columns(4)
            dimension_depth_mm = i1.number_input("Depth / Length mm", min_value=0.0, step=1.0)
            dimension_width_mm = i2.number_input("Width mm", min_value=0.0, step=1.0)
            dimension_height_mm = i3.number_input("Height mm", min_value=0.0, step=1.0)
            weight_kg = i4.number_input("Weight kg", min_value=0.0, step=1.0)
            j1, j2, j3 = st.columns(3)
            charge_discharge_rate = j1.text_input("CH/DCH Rate")
            dod_pct = j2.number_input("DoD %", min_value=0.0, max_value=100.0, step=1.0)
            cycle_life_cycles = j3.number_input("Cycle Life", min_value=0, step=100)
            k1, k2, k3 = st.columns(3)
            end_of_life_soh_pct = k1.number_input("EOL SoH %", min_value=0.0, max_value=100.0, step=1.0)
            service_life_years = k2.number_input("Service Life Years", min_value=0.0, step=1.0)
            system_efficiency_pct = k3.number_input("System Efficiency %", min_value=0.0, step=0.1)
            l1, l2, l3 = st.columns(3)
            working_temp_min_c = l1.number_input("Work Temp Min C", step=1.0)
            working_temp_max_c = l2.number_input("Work Temp Max C", step=1.0)
            altitude_m = l3.number_input("Altitude m", min_value=0.0, step=100.0)
            relative_humidity = st.text_input("Relative Humidity")
            bms_communication = st.text_input("BMS Communication")
            default_degradation_curve_code = st.text_input("Default Degradation Curve Code")
            compliance_standards = st.text_area("Compliance Standards", height=70)
            firefighting_system = st.text_area("Firefighting System", height=70)
            explosion_protection = st.text_area("Explosion Protection", height=70)
            notes = st.text_area("Notes", height=70)
            if st.form_submit_button("Save DC Block Template", use_container_width=True):
                if not block_code.strip() or not block_name.strip():
                    st.error("Block Code and Block Name are required.")
                else:
                    service.create_dc_block(
                        {
                            "block_code": block_code.strip(),
                            "block_name": block_name.strip(),
                            "block_form": block_form,
                            "product_model": product_model.strip() or None,
                            "product_cell_id": cell_map[cell_label],
                            "cells_in_series": int(cells_in_series) or None,
                            "strings_in_parallel": int(strings_in_parallel) or None,
                            "racks_per_block": int(racks_per_block) or None,
                            "packs_per_rack": int(packs_per_rack) or None,
                            "racks_per_container": int(racks_per_container) or None,
                            "pack_count": int(pack_count) or None,
                            "container_count": int(container_count) or None,
                            "configuration": configuration.strip() or None,
                            "container_type": container_type.strip() or None,
                            "thermal_management": thermal_management.strip() or None,
                            "enclosure": enclosure.strip() or None,
                            "gross_energy_mwh": gross_energy_mwh or None,
                            "rated_capacity_kwh": rated_capacity_kwh or None,
                            "nominal_voltage_v": nominal_voltage_v or None,
                            "voltage_min_v": voltage_min_v or None,
                            "voltage_max_v": voltage_max_v or None,
                            "nominal_power_kw": nominal_power_kw or None,
                            "max_current_a": max_current_a or None,
                            "max_c_rate": max_c_rate or None,
                            "charge_discharge_rate": charge_discharge_rate.strip() or None,
                            "dod_pct": dod_pct or None,
                            "cycle_life_cycles": int(cycle_life_cycles) or None,
                            "end_of_life_soh_pct": end_of_life_soh_pct or None,
                            "service_life_years": service_life_years or None,
                            "system_efficiency_pct": system_efficiency_pct or None,
                            "dimension_width_mm": dimension_width_mm or None,
                            "dimension_depth_mm": dimension_depth_mm or None,
                            "dimension_height_mm": dimension_height_mm or None,
                            "weight_kg": weight_kg or None,
                            "ingress_protection": ingress_protection.strip() or None,
                            "relative_humidity": relative_humidity.strip() or None,
                            "working_temp_min_c": working_temp_min_c,
                            "working_temp_max_c": working_temp_max_c,
                            "altitude_m": altitude_m or None,
                            "bms_communication": bms_communication.strip() or None,
                            "compliance_standards": compliance_standards.strip() or None,
                            "firefighting_system": firefighting_system.strip() or None,
                            "explosion_protection": explosion_protection.strip() or None,
                            "default_degradation_curve_code": default_degradation_curve_code.strip() or None,
                            "notes": notes.strip() or None,
                        }
                    )
                    st.success("DC block template saved.")
                    _refresh()


def _section_ac_block(service: ProductAdminService, snapshot: dict[str, Any]) -> None:
    st.subheader("AC Block Templates")
    st.caption("PCS, transformer and AC-side efficiency template records.")

    st.dataframe(
        _rows(
            snapshot["ac_blocks"],
            [
                ("Code", "block_code"),
                ("Name", "block_name"),
                ("PCS Model", "pcs_model"),
                ("PCS kW", "pcs_power_kw"),
                ("PCS Count", "pcs_count"),
                ("Transformer kVA", "transformer_kva"),
                ("HV kV", "hv_voltage_kv"),
                ("LV V", "lv_voltage_v"),
                ("Peak Eff. %", "peak_efficiency_pct"),
                ("Active", "is_active"),
            ],
        ),
        use_container_width=True,
        hide_index=True,
    )

    _render_edit_form(
        service=service,
        title="AC Block Template",
        entity="ac_block",
        items=snapshot["ac_blocks"],
        id_field="product_ac_block_id",
        label_fields=["block_code", "block_name"],
        specs=[
            {"key": "block_name", "label": "Block Name"},
            {"key": "pcs_model", "label": "PCS Model"},
            {"key": "pcs_power_kw", "label": "PCS kW", "kind": "float", "step": 100.0},
            {"key": "pcs_count", "label": "PCS Count", "kind": "int"},
            {"key": "transformer_kva", "label": "Transformer kVA", "kind": "float", "step": 100.0},
            {"key": "hv_voltage_kv", "label": "HV kV", "kind": "float", "step": 0.1},
            {"key": "lv_voltage_v", "label": "LV V", "kind": "float", "step": 10.0},
            {"key": "peak_efficiency_pct", "label": "Peak Eff. %", "kind": "float", "step": 0.1},
            {"key": "aux_load_kw", "label": "Aux Load kW", "kind": "float", "step": 1.0},
            {"key": "notes", "label": "Notes", "kind": "textarea"},
        ],
    )

    with st.expander("Add AC Block Template", expanded=False):
        with st.form("admin_add_product_ac_block"):
            c1, c2 = st.columns(2)
            block_code = c1.text_input("Block Code")
            block_name = c2.text_input("Block Name")
            d1, d2, d3 = st.columns(3)
            pcs_model = d1.text_input("PCS Model")
            pcs_power_kw = d2.number_input("PCS kW", min_value=0.0, step=100.0)
            pcs_count = d3.number_input("PCS Count", min_value=0, step=1)
            e1, e2, e3, e4 = st.columns(4)
            transformer_kva = e1.number_input("Transformer kVA", min_value=0.0, step=100.0)
            hv_voltage_kv = e2.number_input("HV kV", min_value=0.0, step=0.1)
            lv_voltage_v = e3.number_input("LV V", min_value=0.0, step=10.0)
            peak_efficiency_pct = e4.number_input("Peak Eff. %", min_value=0.0, max_value=100.0, step=0.1)
            aux_load_kw = st.number_input("Aux Load kW", min_value=0.0, step=1.0)
            notes = st.text_area("Notes", height=70)
            if st.form_submit_button("Save AC Block Template", use_container_width=True):
                if not block_code.strip() or not block_name.strip():
                    st.error("Block Code and Block Name are required.")
                else:
                    service.create_ac_block(
                        {
                            "block_code": block_code.strip(),
                            "block_name": block_name.strip(),
                            "pcs_model": pcs_model.strip() or None,
                            "pcs_power_kw": pcs_power_kw or None,
                            "pcs_count": int(pcs_count) or None,
                            "transformer_kva": transformer_kva or None,
                            "hv_voltage_kv": hv_voltage_kv or None,
                            "lv_voltage_v": lv_voltage_v or None,
                            "peak_efficiency_pct": peak_efficiency_pct or None,
                            "aux_load_kw": aux_load_kw or None,
                            "notes": notes.strip() or None,
                        }
                    )
                    st.success("AC block template saved.")
                    _refresh()


def _section_assets(service: ProductAdminService, snapshot: dict[str, Any]) -> None:
    st.subheader("Product Assets")
    st.caption("Structured datasheets and product images used by future proposal product-information sections.")

    st.dataframe(
        _rows(
            snapshot["assets"],
            [
                ("Code", "asset_code"),
                ("Owner", "owner_code"),
                ("Entity", "owner_entity"),
                ("Kind", "asset_kind"),
                ("Title", "title"),
                ("File", "file_name"),
                ("Proposal Section", "proposal_section"),
                ("Primary", "is_primary"),
                ("Published", "is_published"),
            ],
        ),
        use_container_width=True,
        hide_index=True,
    )

    _render_edit_form(
        service=service,
        title="Product Asset",
        entity="asset",
        items=snapshot["assets"],
        id_field="product_asset_id",
        label_fields=["asset_code", "title"],
        specs=[
            {"key": "title", "label": "Title"},
            {"key": "asset_kind", "label": "Kind", "kind": "select", "choices": ["datasheet", "product_image", "proposal_image", "source_file", "other"]},
            {"key": "file_name", "label": "File Name"},
            {"key": "mime_type", "label": "MIME Type"},
            {"key": "source_path", "label": "Source Path", "kind": "textarea"},
            {"key": "storage_uri", "label": "Storage URI", "kind": "textarea"},
            {"key": "content_sha256", "label": "SHA-256"},
            {"key": "caption", "label": "Caption", "kind": "textarea"},
            {"key": "proposal_section", "label": "Proposal Section"},
            {"key": "sort_order", "label": "Sort Order", "kind": "int"},
            {"key": "is_primary", "label": "Primary Asset", "kind": "bool"},
        ],
    )

    with st.expander("Add Product Asset", expanded=False):
        owner_options = _asset_owner_options(snapshot)
        with st.form("admin_add_product_asset"):
            owner_label = st.selectbox("Owner", list(owner_options.keys()))
            owner_entity, owner_id, owner_code = owner_options[owner_label]
            c1, c2, c3 = st.columns(3)
            asset_code = c1.text_input("Asset Code", value=f"{owner_code}-DATASHEET" if owner_code else "")
            asset_kind = c2.selectbox("Kind", ["datasheet", "product_image", "proposal_image", "source_file", "other"])
            proposal_section = c3.text_input("Proposal Section", value="Standard Product Information")
            title = st.text_input("Title")
            d1, d2 = st.columns(2)
            file_name = d1.text_input("File Name")
            mime_type = d2.text_input("MIME Type")
            source_path = st.text_area("Source Path", height=60)
            storage_uri = st.text_area("Storage URI", height=60)
            content_sha256 = st.text_input("SHA-256")
            caption = st.text_area("Caption", height=70)
            e1, e2 = st.columns(2)
            sort_order = e1.number_input("Sort Order", min_value=0, step=1)
            is_primary = e2.checkbox("Primary Asset", value=True)
            if st.form_submit_button("Save Product Asset", use_container_width=True):
                if not asset_code.strip() or not title.strip():
                    st.error("Asset Code and Title are required.")
                else:
                    service.create_asset(
                        {
                            "asset_code": asset_code.strip(),
                            "owner_entity": owner_entity,
                            "owner_id": owner_id,
                            "owner_code": owner_code or None,
                            "asset_kind": asset_kind,
                            "title": title.strip(),
                            "file_name": file_name.strip() or None,
                            "mime_type": mime_type.strip() or None,
                            "source_path": source_path.strip() or None,
                            "storage_uri": storage_uri.strip() or None,
                            "content_sha256": content_sha256.strip() or None,
                            "caption": caption.strip() or None,
                            "proposal_section": proposal_section.strip() or None,
                            "sort_order": int(sort_order),
                            "is_primary": is_primary,
                        }
                    )
                    st.success("Product asset saved.")
                    _refresh()


def _section_degradation(service: ProductAdminService, snapshot: dict[str, Any]) -> None:
    st.subheader("Degradation Library")
    st.caption("SoH vs cycle/calendar curves under specific operating conditions.")

    st.dataframe(
        _rows(
            snapshot["degradation_curves"],
            [
                ("Code", "curve_code"),
                ("Family", "curve_family"),
                ("Status", "data_status"),
                ("Condition", "condition_label"),
                ("Temp C", "temperature_c"),
                ("DoD %", "dod_pct"),
                ("C-rate", "c_rate"),
                ("Years", "calendar_years"),
                ("EOL SoH %", "end_of_life_soh_pct"),
                ("Source", "source"),
                ("Active", "is_active"),
            ],
        ),
        use_container_width=True,
        hide_index=True,
    )

    _render_edit_form(
        service=service,
        title="Degradation Curve",
        entity="degradation_curve",
        items=snapshot["degradation_curves"],
        id_field="degradation_curve_id",
        label_fields=["curve_code", "condition_label"],
        cells=snapshot["cells"],
        specs=[
            {"key": "curve_type", "label": "Curve Type"},
            {"key": "curve_family", "label": "Curve Family"},
            {"key": "basis_cell_code", "label": "Basis Cell Code"},
            {"key": "default_scope", "label": "Default Scope"},
            {"key": "data_status", "label": "Data Status"},
            {"key": "product_cell_id", "label": "Linked Cell", "kind": "cell"},
            {"key": "condition_label", "label": "Condition Label"},
            {"key": "temperature_c", "label": "Temp C", "kind": "float", "step": 1.0},
            {"key": "dod_pct", "label": "DoD %", "kind": "float", "step": 1.0},
            {"key": "c_rate", "label": "C-rate", "kind": "float", "step": 0.1},
            {"key": "calendar_years", "label": "Calendar Years", "kind": "float", "step": 1.0},
            {"key": "end_of_life_soh_pct", "label": "EOL SoH %", "kind": "float", "step": 1.0},
            {"key": "source", "label": "Source"},
            {"key": "notes", "label": "Notes", "kind": "textarea"},
        ],
    )

    with st.expander("Add Degradation Curve Header", expanded=False):
        with st.form("admin_add_degradation_curve"):
            curve_code = st.text_input("Curve Code")
            cell_map = _cell_options(snapshot["cells"])
            cell_label = st.selectbox("Linked Cell", list(cell_map.keys()), key="deg_cell")
            m1, m2, m3 = st.columns(3)
            curve_type = m1.text_input("Curve Type", value="hybrid_year_cycle")
            curve_family = m2.text_input("Curve Family")
            data_status = m3.text_input("Data Status")
            m4, m5 = st.columns(2)
            basis_cell_code = m4.text_input("Basis Cell Code")
            default_scope = m5.text_input("Default Scope")
            condition_label = st.text_input("Condition Label")
            c1, c2, c3, c4 = st.columns(4)
            temperature_c = c1.number_input("Temp C", step=1.0)
            dod_pct = c2.number_input("DoD %", min_value=0.0, max_value=100.0, step=1.0)
            c_rate = c3.number_input("C-rate", min_value=0.0, step=0.1)
            calendar_years = c4.number_input("Calendar Years", min_value=0.0, step=1.0)
            end_of_life_soh_pct = st.number_input("EOL SoH %", min_value=0.0, max_value=100.0, step=1.0)
            source = st.text_input("Source")
            notes = st.text_area("Notes", height=70)
            if st.form_submit_button("Save Degradation Curve", use_container_width=True):
                if not curve_code.strip() or not condition_label.strip():
                    st.error("Curve Code and Condition Label are required.")
                else:
                    service.create_degradation_curve(
                        {
                            "curve_code": curve_code.strip(),
                            "product_cell_id": cell_map[cell_label],
                            "curve_type": curve_type.strip() or None,
                            "curve_family": curve_family.strip() or None,
                            "basis_cell_code": basis_cell_code.strip() or None,
                            "default_scope": default_scope.strip() or None,
                            "data_status": data_status.strip() or None,
                            "condition_label": condition_label.strip(),
                            "temperature_c": temperature_c,
                            "dod_pct": dod_pct or None,
                            "c_rate": c_rate or None,
                            "calendar_years": calendar_years or None,
                            "end_of_life_soh_pct": end_of_life_soh_pct or None,
                            "source": source.strip() or None,
                            "notes": notes.strip() or None,
                        }
                    )
                    st.success("Degradation curve saved.")
                    _refresh()


def _section_rte(service: ProductAdminService, snapshot: dict[str, Any]) -> None:
    st.subheader("RTE Library")
    st.caption("Round-trip efficiency by SoC, temperature and C-rate.")

    st.dataframe(
        _rows(
            snapshot["rte_curves"],
            [
                ("Code", "curve_code"),
                ("Condition", "condition_label"),
                ("SoC Min %", "soc_min_pct"),
                ("SoC Max %", "soc_max_pct"),
                ("Temp C", "temperature_c"),
                ("C-rate", "c_rate"),
                ("RTE %", "rte_pct"),
                ("Source", "source"),
                ("Active", "is_active"),
            ],
        ),
        use_container_width=True,
        hide_index=True,
    )

    _render_edit_form(
        service=service,
        title="RTE Curve",
        entity="rte_curve",
        items=snapshot["rte_curves"],
        id_field="rte_curve_id",
        label_fields=["curve_code", "condition_label"],
        cells=snapshot["cells"],
        specs=[
            {"key": "product_cell_id", "label": "Linked Cell", "kind": "cell"},
            {"key": "condition_label", "label": "Condition Label"},
            {"key": "soc_min_pct", "label": "SoC Min %", "kind": "float", "step": 1.0},
            {"key": "soc_max_pct", "label": "SoC Max %", "kind": "float", "step": 1.0},
            {"key": "temperature_c", "label": "Temp C", "kind": "float", "step": 1.0},
            {"key": "c_rate", "label": "C-rate", "kind": "float", "step": 0.1},
            {"key": "rte_pct", "label": "RTE %", "kind": "float", "step": 0.1},
            {"key": "source", "label": "Source"},
            {"key": "notes", "label": "Notes", "kind": "textarea"},
        ],
    )

    with st.expander("Add RTE Curve Header", expanded=False):
        with st.form("admin_add_rte_curve"):
            curve_code = st.text_input("Curve Code")
            cell_map = _cell_options(snapshot["cells"])
            cell_label = st.selectbox("Linked Cell", list(cell_map.keys()), key="rte_cell")
            condition_label = st.text_input("Condition Label")
            c1, c2, c3, c4, c5 = st.columns(5)
            soc_min_pct = c1.number_input("SoC Min %", min_value=0.0, max_value=100.0, step=1.0)
            soc_max_pct = c2.number_input("SoC Max %", min_value=0.0, max_value=100.0, step=1.0)
            temperature_c = c3.number_input("Temp C", step=1.0)
            c_rate = c4.number_input("C-rate", min_value=0.0, step=0.1)
            rte_pct = c5.number_input("RTE %", min_value=0.0, max_value=100.0, step=0.1)
            source = st.text_input("Source")
            notes = st.text_area("Notes", height=70)
            if st.form_submit_button("Save RTE Curve", use_container_width=True):
                if not curve_code.strip() or not condition_label.strip():
                    st.error("Curve Code and Condition Label are required.")
                else:
                    service.create_rte_curve(
                        {
                            "curve_code": curve_code.strip(),
                            "product_cell_id": cell_map[cell_label],
                            "condition_label": condition_label.strip(),
                            "soc_min_pct": soc_min_pct,
                            "soc_max_pct": soc_max_pct,
                            "temperature_c": temperature_c,
                            "c_rate": c_rate or None,
                            "rte_pct": rte_pct or None,
                            "source": source.strip() or None,
                            "notes": notes.strip() or None,
                        }
                    )
                    st.success("RTE curve saved.")
                    _refresh()


def _section_plugins(service: ProductAdminService, snapshot: dict[str, Any]) -> None:
    st.subheader("Plugin Registry")
    st.caption("Reserved mount points for PyBaMM, GitHub or internal degradation simulation plugins.")

    st.dataframe(
        _rows(
            snapshot["plugins"],
            [
                ("Key", "plugin_key"),
                ("Name", "name"),
                ("Version", "plugin_version"),
                ("Entrypoint", "entrypoint"),
                ("Schema", "schema_version"),
                ("Status", "status"),
                ("Enabled", "enabled"),
            ],
        ),
        use_container_width=True,
        hide_index=True,
    )

    _render_edit_form(
        service=service,
        title="Plugin",
        entity="plugin",
        items=snapshot["plugins"],
        id_field="degradation_plugin_id",
        label_fields=["plugin_key", "name"],
        specs=[
            {"key": "name", "label": "Name"},
            {"key": "plugin_version", "label": "Version"},
            {"key": "entrypoint", "label": "Entrypoint"},
            {"key": "schema_version", "label": "Schema Version"},
            {"key": "status", "label": "Status", "kind": "select", "choices": ["draft", "validated", "disabled"]},
            {"key": "enabled", "label": "Enabled", "kind": "bool"},
            {"key": "description", "label": "Description", "kind": "textarea"},
        ],
    )

    with st.expander("Register Plugin", expanded=False):
        with st.form("admin_add_degradation_plugin"):
            c1, c2 = st.columns(2)
            plugin_key = c1.text_input("Plugin Key")
            name = c2.text_input("Name")
            d1, d2 = st.columns(2)
            plugin_version = d1.text_input("Version", value="0.1.0")
            schema_version = d2.text_input("Schema Version", value="v1")
            entrypoint = st.text_input("Entrypoint", placeholder="package.module:callable")
            e1, e2 = st.columns(2)
            status = e1.selectbox("Status", ["draft", "validated", "disabled"])
            enabled = e2.checkbox("Enabled")
            description = st.text_area("Description", height=70)
            if st.form_submit_button("Save Plugin", use_container_width=True):
                if not plugin_key.strip() or not name.strip() or not entrypoint.strip():
                    st.error("Plugin Key, Name and Entrypoint are required.")
                else:
                    service.create_plugin(
                        {
                            "plugin_key": plugin_key.strip(),
                            "name": name.strip(),
                            "plugin_version": plugin_version.strip() or "0.1.0",
                            "entrypoint": entrypoint.strip(),
                            "schema_version": schema_version.strip() or "v1",
                            "status": status,
                            "enabled": enabled,
                            "description": description.strip() or None,
                        }
                    )
                    st.success("Plugin registered.")
                    _refresh()
