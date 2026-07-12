"""Admin-only product and database management portal."""
from __future__ import annotations

import hashlib
import io
import mimetypes
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from calb_sizing_tool.services.auth_service import AuthService
from calb_sizing_tool.services.product_admin_service import ProductAdminService
from calb_sizing_tool.utils.files import safe_child_path, safe_storage_filename
from calb_sizing_tool.state.auth_state import get_auth_context
from calb_sizing_tool.ui._ui import page_header

_ASSET_STORE = Path("var/assets")

# ── CSV template column definitions ──────────────────────────────────────────

_CELL_CSV_COLUMNS = [
    "cell_code", "model_name", "chemistry", "manufacturer",
    "nominal_capacity_ah", "shipping_capacity_ah", "nominal_voltage_v",
    "min_voltage_v", "max_voltage_v", "rated_energy_wh",
    "length_mm", "width_mm", "height_mm", "shoulder_height_mm",
    "weight_kg", "volume_l", "gravimetric_density_wh_kg", "volumetric_density_wh_l",
    "energy_efficiency_pct", "dcr_mohm", "rated_c_rate_label",
    "cycle_life_cycles", "cycle_life_rate_label", "cycle_life_dod_pct",
    "end_of_life_soh_pct", "manufacturing_process", "launch_year", "notes",
]

_DC_BLOCK_CSV_COLUMNS = [
    "block_code", "block_name", "block_form", "product_model",
    "cells_in_series", "strings_in_parallel", "racks_per_block",
    "packs_per_rack", "racks_per_container", "pack_count", "container_count",
    "configuration", "container_type", "thermal_management", "enclosure",
    "gross_energy_mwh", "usable_energy_mwh", "rated_capacity_kwh",
    "nominal_voltage_v", "voltage_min_v", "voltage_max_v",
    "nominal_power_kw", "max_current_a", "max_c_rate", "charge_discharge_rate",
    "dod_pct", "cycle_life_cycles", "end_of_life_soh_pct",
    "service_life_years", "system_efficiency_pct",
    "dimension_width_mm", "dimension_depth_mm", "dimension_height_mm", "weight_kg",
    "ingress_protection", "working_temp_min_c", "working_temp_max_c", "notes",
]


def _template_csv(columns: list[str]) -> bytes:
    """Return an empty CSV template with header row."""
    return (",".join(columns) + "\n").encode()


def _parse_upload(uploaded_file) -> pd.DataFrame | None:
    """Parse an uploaded CSV or XLSX file. Returns None on failure."""
    try:
        name = uploaded_file.name.lower()
        if name.endswith(".xlsx") or name.endswith(".xls"):
            return pd.read_excel(uploaded_file, dtype=str).replace({"nan": None, "": None})
        return pd.read_csv(uploaded_file, dtype=str).replace({"nan": None, "": None})
    except Exception as exc:
        st.error(f"Failed to parse file: {exc}")
        return None


def _render_import_expander(
    service: ProductAdminService,
    entity: str,
    required_cols: list[str],
    template_cols: list[str],
    label: str,
) -> None:
    with st.expander(f"Import {label} from CSV / Excel", expanded=False):
        tpl_bytes = _template_csv(template_cols)
        st.download_button(
            f"Download {label} CSV Template",
            tpl_bytes,
            file_name=f"template_{entity}.csv",
            mime="text/csv",
            key=f"dl_tpl_{entity}",
        )
        uploaded = st.file_uploader(
            "Upload CSV or XLSX",
            type=["csv", "xlsx", "xls"],
            key=f"upload_{entity}",
        )
        if uploaded is None:
            return
        df = _parse_upload(uploaded)
        if df is None:
            return
        missing = [c for c in required_cols if c not in df.columns]
        if missing:
            st.error(f"Missing required columns: {', '.join(missing)}")
            return
        st.caption(f"{len(df)} rows detected. Preview (first 5):")
        st.dataframe(df.head(5), use_container_width=True, hide_index=True)
        if st.button(f"Import {len(df)} {label} rows", key=f"btn_import_{entity}", type="primary"):
            result = service.import_records_from_df(entity, df)
            if result["imported"]:
                st.success(f"Imported {result['imported']} record(s).")
            if result["skipped"]:
                st.warning(f"Skipped {result['skipped']} row(s).")
            for err in result["errors"][:20]:
                st.error(err)
            if result["imported"]:
                _refresh()

_SECTIONS = [
    ("Overview", "Dashboard"),
    ("Cell Products", "Cells"),
    ("DC Block Templates", "DC Blocks"),
    ("AC Block Templates", "AC Blocks"),
    ("Product Assets", "Assets"),
    ("Degradation Library", "Degradation"),
    ("RTE Library", "RTE"),
    ("Plugin Registry", "Plugins"),
    ("DC Sizing Data", "Sizing Data"),
    ("Users & Access", "Users"),
]

_ADMIN_NAV_KEY = "admin_portal_section"


def _render_admin_css() -> None:
    st.markdown(
        """
        <style>
        .calb-admin-nav-title {
            color: #506F94;
            font-size: 0.72rem;
            font-weight: 700;
            letter-spacing: 0.06em;
            margin-bottom: 0.35rem;
            text-transform: uppercase;
        }

        .calb-admin-section-note {
            color: #6F7E8F;
            font-size: 0.86rem;
            margin-bottom: 0.75rem;
        }

        div[data-testid="stRadio"] [role="radiogroup"] {
            gap: 0.15rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def show() -> None:
    auth_context = get_auth_context()
    if auth_context is None or not auth_context.is_admin:
        st.error("Admin access required.")
        return

    service = ProductAdminService()
    snapshot = _load_snapshot(service)

    _render_admin_css()
    page_header("Product & Database", "Admin-only product libraries, user access, performance data, and simulation plugins")
    st.divider()

    nav_col, content_col = st.columns([1, 4], gap="large")

    with nav_col:
        with st.container(border=True):
            st.markdown('<div class="calb-admin-nav-title">Admin Portal</div>', unsafe_allow_html=True)
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
        elif selected == "DC Sizing Data":
            _section_dc_sizing_data()
        elif selected == "Users & Access":
            _section_users_access()


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


def _format_datetime(value: Any) -> str:
    if value is None:
        return "N/A"
    try:
        return value.strftime("%Y-%m-%d %H:%M")
    except AttributeError:
        return str(value)


def _project_label_map(projects: list[dict[str, str]]) -> dict[str, str]:
    return {project["label"]: project["project_id"] for project in projects}


def _labels_for_project_ids(projects: list[dict[str, str]], project_ids: list[str]) -> list[str]:
    by_id = {project["project_id"]: project["label"] for project in projects}
    return [by_id[project_id] for project_id in project_ids if project_id in by_id]


def _user_option_label(row: dict[str, Any]) -> str:
    display = row.get("display_name") or row.get("username")
    status = row.get("status") or "unknown"
    return f"{row['username']} - {display} ({status})"


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
                # Explicit entity+record keys: without them Streamlit derives
                # widget IDs from (type, label, value), which collide with the
                # add-form widgets on the same page whenever values match, and
                # keep stale user input when the selected record changes.
                widget_key = f"edit_{entity}_{record_id}_{key}"
                if kind == "text":
                    values[key] = st.text_input(label, value=str(current or ""), key=widget_key)
                elif kind == "textarea":
                    values[key] = st.text_area(label, value=str(current or ""), height=70, key=widget_key)
                elif kind == "float":
                    values[key] = st.number_input(label, value=_optional_float(current), step=float(spec.get("step", 1.0)), key=widget_key)
                elif kind == "int":
                    values[key] = st.number_input(label, value=_optional_int(current), min_value=0, step=1, key=widget_key)
                elif kind == "select":
                    choices = spec["choices"]
                    index = choices.index(current) if current in choices else 0
                    values[key] = st.selectbox(label, choices, index=index, key=widget_key)
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
                            key=widget_key,
                        )
                    ]
                elif kind == "bool":
                    values[key] = st.checkbox(label, value=bool(current), key=widget_key)

            c1, c2 = st.columns(2)
            values["is_active"] = c1.checkbox("Active", value=bool(record.get("is_active", True)), key=f"edit_{entity}_{record_id}_is_active")
            values["is_published"] = c2.checkbox("Published", value=bool(record.get("is_published", False)), key=f"edit_{entity}_{record_id}_is_published")

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


def _section_users_access() -> None:
    auth_context = get_auth_context()
    if auth_context is None or not auth_context.is_admin:
        st.error("Admin access required.")
        return

    service = AuthService()
    rows = service.list_user_admin_rows()
    role_options = sorted(
        service.list_role_codes(),
        key=lambda code: {"normal_user": 0, "admin": 1}.get(code, 10),
    )
    default_roles = ["normal_user"] if "normal_user" in role_options else role_options[:1]
    projects = service.list_project_options()
    project_map = _project_label_map(projects)
    project_labels = list(project_map.keys())

    st.subheader("Users & Access")
    st.caption("Public sign-up remains disabled. Administrators create accounts and assign project access here.")

    display_rows = [
        {
            "Username": row["username"],
            "Display Name": row.get("display_name") or "N/A",
            "Email": row.get("email") or "N/A",
            "Status": row.get("status"),
            "Roles": ", ".join(row.get("roles") or []),
            "Project Access": (
                "All projects (admin)"
                if row.get("is_admin")
                else ", ".join(row.get("project_labels") or []) or "N/A"
            ),
            "Created": _format_datetime(row.get("created_at")),
            "Last Login": _format_datetime(row.get("last_login_at")),
        }
        for row in rows
    ]
    st.dataframe(display_rows, use_container_width=True, hide_index=True)

    with st.expander("Create User", expanded=False):
        st.info("This prepares registration internally only. No public registration entry is exposed on the login page.")
        with st.form("admin_create_user"):
            c1, c2 = st.columns(2)
            username = c1.text_input("Username *")
            display_name = c2.text_input("Display Name")
            email = st.text_input("Email")
            roles = st.multiselect("Roles *", role_options, default=default_roles)
            selected_project_labels = st.multiselect(
                "Project Access",
                project_labels,
                help="Admin role can access all projects. Use this list to scope normal users.",
            )
            p1, p2 = st.columns(2)
            password = p1.text_input("Initial Password *", type="password")
            confirm = p2.text_input("Confirm Password *", type="password")

            if st.form_submit_button("Create User", use_container_width=True):
                if password != confirm:
                    st.error("Passwords do not match.")
                else:
                    try:
                        service.admin_create_user(
                            actor_user_id=auth_context.user_id,
                            username=username,
                            password=password,
                            display_name=display_name,
                            email=email,
                            role_codes=roles,
                            project_ids=[project_map[label] for label in selected_project_labels],
                        )
                    except ValueError as exc:
                        st.error(str(exc))
                    else:
                        st.success("User created.")
                        st.rerun()

    if not rows:
        return

    with st.expander("Edit User Access", expanded=False):
        option_map = {_user_option_label(row): row["user_id"] for row in rows}
        selected_label = st.selectbox("User", list(option_map.keys()), key="admin_edit_user_record")
        user_id = option_map[selected_label]
        row = next((item for item in rows if item["user_id"] == user_id), None)
        if row is None:
            st.warning("Selected user is no longer available.")
            return

        with st.form("admin_edit_user"):
            st.text_input("Username", value=str(row.get("username") or ""), disabled=True)
            c1, c2 = st.columns(2)
            display_name = c1.text_input("Display Name", value=str(row.get("display_name") or ""))
            email = c2.text_input("Email", value=str(row.get("email") or ""))
            statuses = ["active", "inactive"]
            current_status = str(row.get("status") or "active")
            status = st.selectbox(
                "Status",
                statuses,
                index=statuses.index(current_status) if current_status in statuses else 0,
            )
            current_roles = [role for role in (row.get("roles") or []) if role in role_options] or default_roles
            roles = st.multiselect("Roles *", role_options, default=current_roles, key="admin_edit_user_roles")
            current_project_labels = _labels_for_project_ids(projects, row.get("project_ids") or [])
            selected_project_labels = st.multiselect(
                "Project Access",
                project_labels,
                default=current_project_labels,
                help="Admin role can access all projects. Use this list to scope normal users.",
            )
            st.caption("Leave password fields blank to keep the current password.")
            p1, p2 = st.columns(2)
            new_password = p1.text_input("New Password", type="password")
            confirm_password = p2.text_input("Confirm New Password", type="password")

            if st.form_submit_button("Save User Access", use_container_width=True):
                if new_password and new_password != confirm_password:
                    st.error("Passwords do not match.")
                else:
                    try:
                        service.admin_update_user(
                            user_id=user_id,
                            actor_user_id=auth_context.user_id,
                            display_name=display_name,
                            email=email,
                            status=status,
                            role_codes=roles,
                            project_ids=[project_map[label] for label in selected_project_labels],
                            new_password=new_password or None,
                        )
                    except ValueError as exc:
                        st.error(str(exc))
                    else:
                        st.success("User access updated.")
                        st.rerun()


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

    _render_import_expander(
        service, "cell",
        required_cols=["cell_code", "model_name", "chemistry"],
        template_cols=_CELL_CSV_COLUMNS,
        label="Cell Products",
    )


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
            # ── Identity (always visible) ─────────────────────────────────
            c1, c2, c3 = st.columns(3)
            block_code = c1.text_input("Block Code *")
            block_name = c2.text_input("Block Name *")
            block_form = c3.selectbox(
                "Block Form *",
                ["container", "cabinet"],
                help="container = 20ft BESS unit, cabinet = indoor rack cabinet",
            )
            # ── Tabs for the remaining 40 fields ─────────────────────────
            tab_core, tab_struct, tab_phys, tab_comply, tab_notes = st.tabs(
                ["Core", "Structure", "Physical", "Compliance", "Notes"]
            )

            with tab_core:
                tc1, tc2 = st.columns(2)
                product_model = tc1.text_input("Product Model")
                cell_map = _cell_options(snapshot["cells"])
                cell_label = tc2.selectbox("Linked Cell", list(cell_map.keys()))
                e1, e2, e3, e4 = st.columns(4)
                gross_energy_mwh = e1.number_input("Gross MWh", min_value=0.0, step=0.1)
                rated_capacity_kwh = e2.number_input("Rated kWh", min_value=0.0, step=1.0)
                usable_energy_mwh = e3.number_input("Usable MWh", min_value=0.0, step=0.1)
                max_c_rate = e4.number_input("Max C-rate", min_value=0.0, step=0.1)
                f1, f2, f3, f4 = st.columns(4)
                nominal_voltage_v = f1.number_input("Nominal V", min_value=0.0, step=1.0)
                voltage_min_v = f2.number_input("Min V", min_value=0.0, step=1.0)
                voltage_max_v = f3.number_input("Max V", min_value=0.0, step=1.0)
                nominal_power_kw = f4.number_input("Nominal Power kW", min_value=0.0, step=1.0)
                g1, g2, g3, g4 = st.columns(4)
                max_current_a = g1.number_input("Max Current A", min_value=0.0, step=1.0)
                charge_discharge_rate = g2.text_input("CH/DCH Rate")
                dod_pct = g3.number_input("DoD %", min_value=0.0, max_value=100.0, step=1.0)
                system_efficiency_pct = g4.number_input("System Efficiency %", min_value=0.0, step=0.1)
                h1, h2, h3 = st.columns(3)
                cycle_life_cycles = h1.number_input("Cycle Life", min_value=0, step=100)
                end_of_life_soh_pct = h2.number_input("EOL SoH %", min_value=0.0, max_value=100.0, step=1.0)
                service_life_years = h3.number_input("Service Life Years", min_value=0.0, step=1.0)

            with tab_struct:
                s1, s2, s3, s4 = st.columns(4)
                cells_in_series = s1.number_input("Cells in Series", min_value=0, step=1)
                strings_in_parallel = s2.number_input("Strings in Parallel", min_value=0, step=1)
                racks_per_block = s3.number_input("Racks per Block", min_value=0, step=1)
                pack_count = s4.number_input("Pack Count", min_value=0, step=1)
                s5, s6, s7, s8 = st.columns(4)
                packs_per_rack = s5.number_input("Packs per Rack", min_value=0, step=1)
                racks_per_container = s6.number_input("Racks per Container", min_value=0, step=1)
                container_count = s7.number_input("Container Count", min_value=0, step=1)
                configuration = s8.text_input("Configuration")
                st1, st2 = st.columns(2)
                container_type = st1.text_input("Container / Cabinet Type")
                thermal_management = st2.text_input("Thermal Management")

            with tab_phys:
                p1, p2, p3, p4 = st.columns(4)
                dimension_depth_mm = p1.number_input("Depth mm", min_value=0.0, step=1.0)
                dimension_width_mm = p2.number_input("Width mm", min_value=0.0, step=1.0)
                dimension_height_mm = p3.number_input("Height mm", min_value=0.0, step=1.0)
                weight_kg = p4.number_input("Weight kg", min_value=0.0, step=1.0)
                p5, p6, p7, p8 = st.columns(4)
                enclosure = p5.text_input("Enclosure")
                ingress_protection = p6.text_input("Ingress Protection")
                relative_humidity = p7.text_input("Relative Humidity")
                altitude_m = p8.number_input("Altitude m", min_value=0.0, step=100.0)
                p9, p10 = st.columns(2)
                working_temp_min_c = p9.number_input("Work Temp Min °C", step=1.0)
                working_temp_max_c = p10.number_input("Work Temp Max °C", step=1.0)

            with tab_comply:
                bms_communication = st.text_input("BMS Communication")
                default_degradation_curve_code = st.text_input("Default Degradation Curve Code")
                compliance_standards = st.text_area("Compliance Standards", height=70)
                firefighting_system = st.text_area("Firefighting System", height=70)
                explosion_protection = st.text_area("Explosion Protection", height=70)
                seismic_rating = st.text_input("Seismic Rating")
                coating = st.text_input("Painting / Coating")

            with tab_notes:
                notes = st.text_area("Notes", height=100)

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
                            "usable_energy_mwh": usable_energy_mwh or None,
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
                            "seismic_rating": seismic_rating.strip() or None,
                            "coating": coating.strip() or None,
                            "default_degradation_curve_code": default_degradation_curve_code.strip() or None,
                            "notes": notes.strip() or None,
                        }
                    )
                    st.success("DC block template saved.")
                    _refresh()

    _render_import_expander(
        service, "dc_block",
        required_cols=["block_code", "block_name", "block_form"],
        template_cols=_DC_BLOCK_CSV_COLUMNS,
        label="DC Block Templates",
    )


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

            # ── File upload ───────────────────────────────────────────────
            uploaded_asset = st.file_uploader(
                "Upload File (PDF, image, …)",
                type=["pdf", "png", "jpg", "jpeg", "svg", "xlsx", "docx", "zip"],
                key="asset_file_upload",
                help="File is saved to var/assets/ on this server. SHA-256 and MIME auto-filled.",
            )
            d1, d2 = st.columns(2)
            file_name = d1.text_input("File Name (auto-filled from upload)")
            mime_type = d2.text_input("MIME Type (auto-filled from upload)")
            source_path = st.text_area("Source Path (auto-filled from upload)", height=50)
            storage_uri = st.text_area("Storage URI (optional — cloud path)", height=50)
            content_sha256 = st.text_input("SHA-256 (auto-filled from upload)")
            caption = st.text_area("Caption", height=70)
            e1, e2 = st.columns(2)
            sort_order = e1.number_input("Sort Order", min_value=0, step=1)
            is_primary = e2.checkbox("Primary Asset", value=True)

            if st.form_submit_button("Save Product Asset", use_container_width=True):
                if not asset_code.strip() or not title.strip():
                    st.error("Asset Code and Title are required.")
                else:
                    _file_name = file_name.strip() or None
                    _mime_type = mime_type.strip() or None
                    _source_path = source_path.strip() or None
                    _sha256 = content_sha256.strip() or None

                    if uploaded_asset is not None:
                        _raw = uploaded_asset.read()
                        _sha256 = hashlib.sha256(_raw).hexdigest()
                        _file_name = safe_storage_filename(_file_name or uploaded_asset.name)
                        _mime_type = _mime_type or (
                            mimetypes.guess_type(uploaded_asset.name)[0]
                            or uploaded_asset.type
                            or "application/octet-stream"
                        )
                        _dest_dir = _ASSET_STORE / safe_storage_filename(asset_code.strip(), fallback="asset")
                        _dest_dir.mkdir(parents=True, exist_ok=True)
                        _dest = safe_child_path(_dest_dir, _file_name or uploaded_asset.name)
                        _dest.write_bytes(_raw)
                        _source_path = _source_path or str(_dest.resolve())

                    service.create_asset(
                        {
                            "asset_code": asset_code.strip(),
                            "owner_entity": owner_entity,
                            "owner_id": owner_id,
                            "owner_code": owner_code or None,
                            "asset_kind": asset_kind,
                            "title": title.strip(),
                            "file_name": _file_name,
                            "mime_type": _mime_type,
                            "source_path": _source_path,
                            "storage_uri": storage_uri.strip() or None,
                            "content_sha256": _sha256,
                            "caption": caption.strip() or None,
                            "proposal_section": proposal_section.strip() or None,
                            "sort_order": int(sort_order),
                            "is_primary": is_primary,
                        }
                    )
                    st.success(
                        "Product asset saved."
                        + (f" File stored at `{_source_path}`." if uploaded_asset else "")
                    )
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


def _section_dc_sizing_data() -> None:
    st.subheader("DC Sizing Data")
    st.caption(
        "SoH profiles, degradation curves and RTE bands used by the stage-3 DC sizing pipeline. "
        "When DB data is present it overrides the Excel reference file at runtime."
    )

    from calb_sizing_tool.services.master_data_service import MasterDataService

    svc = MasterDataService()
    try:
        counts = svc.get_soh_rte_counts()
    except Exception as exc:
        st.error(f"Could not query DB: {exc}")
        return

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("SoH Profiles", counts["soh_profile"])
    c2.metric("SoH Curve Points", counts["soh_curve_point"])
    c3.metric("RTE Profiles", counts["rte_profile"])
    c4.metric("RTE Curve Bands", counts["rte_curve_band"])

    _has_data = counts["soh_profile"] > 0 and counts["rte_profile"] > 0
    if _has_data:
        st.success("DB data present — stage-3 will use DB curves (refreshed every 60 s).")
    else:
        st.info("No DB data — stage-3 uses the Excel reference file.")

    st.markdown("---")
    st.markdown("**Migrate from Excel reference file**")
    st.caption(
        "Reads `soh_profile_314_data`, `soh_curve_314_template`, `rte_profile_314_data`, "
        "and `rte_curve_314_template` sheets from the active DC data workbook and stores them "
        "in the database. Existing SoH/RTE records are fully replaced."
    )

    version_tag = st.text_input("Version tag", value="excel-import", key="soh_rte_version_tag")
    source_ref = st.text_input("Source ref (optional notes)", value="", key="soh_rte_source_ref")

    if st.button("Migrate SoH / RTE from Excel", type="primary", key="btn_migrate_soh_rte"):
        try:
            from calb_sizing_tool.config import DC_DATA_PATH
            from calb_sizing_tool.adapters.excel_loader_adapter import load_dc_excel_bundle_from_path
            from pathlib import Path

            data_path = Path(DC_DATA_PATH)
            if not data_path.is_file():
                st.error(f"Excel data file not found: {data_path}")
            else:
                bundle = load_dc_excel_bundle_from_path(data_path)
                result = svc.migrate_soh_rte_from_excel_bundle(
                    bundle,
                    version_tag=version_tag.strip() or "excel-import",
                    source_ref=source_ref.strip() or str(data_path.name),
                )
                st.success(
                    f"Migration complete — "
                    f"{result['soh_profile']} SoH profiles, "
                    f"{result['soh_curve_point']} curve points, "
                    f"{result['rte_profile']} RTE profiles, "
                    f"{result['rte_curve_band']} curve bands."
                )
                st.rerun()
        except Exception as exc:
            st.error(f"Migration failed: {exc}")

    if _has_data:
        st.markdown("---")
        st.markdown("**Clear DB data (revert to Excel)**")
        st.caption("Removes all SoH/RTE records. Stage-3 will revert to the Excel reference file.")
        if st.button("Clear DB SoH / RTE data", key="btn_clear_soh_rte"):
            try:
                result = svc.migrate_soh_rte_from_excel_bundle(
                    _empty_bundle(), version_tag="cleared", source_ref="admin-clear"
                )
                st.success("SoH/RTE DB data cleared.")
                st.rerun()
            except Exception as exc:
                st.error(f"Clear failed: {exc}")


def _empty_bundle():
    """Return a minimal DcExcelMasterDataBundle with empty SoH/RTE DataFrames for clearing."""
    import pandas as pd
    from pathlib import Path
    from calb_sizing_tool.schemas.master_data import DcExcelMasterDataBundle
    return DcExcelMasterDataBundle(
        workbook_path=Path("."),
        defaults={},
        df_blocks=pd.DataFrame(),
        df_soh_profile=pd.DataFrame(),
        df_soh_curve=pd.DataFrame(),
        df_rte_profile=pd.DataFrame(),
        df_rte_curve=pd.DataFrame(),
        raw_sheets={},
    )
