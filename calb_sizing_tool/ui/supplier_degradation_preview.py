"""Supplier curve review on the existing admin Degradation page."""
from __future__ import annotations

import streamlit as st
from sqlalchemy.exc import SQLAlchemyError

from calb_sizing_tool.services.supplier_degradation_service import parse_supplier_degradation
from calb_sizing_tool.services.supplier_degradation_library_service import SupplierDegradationLibraryService
from calb_sizing_tool.services.supplier_degradation_export_service import export_supplier_review_workbook
from calb_sizing_tool.state.auth_state import get_auth_context
from calb_sizing_tool.ui._ui import render_static_table
from calb_sizing_tool.utils.files import upload_exceeds_limit


@st.cache_data(max_entries=4, show_spinner=False)
def _parse(data):
    return parse_supplier_degradation(data)


@st.cache_data(max_entries=8, show_spinner=False)
def _export(dataset, curves=None, metadata=None):
    return export_supplier_review_workbook(dataset, curves, metadata)


def render_supplier_degradation_preview(db_url=None):
    st.caption("Open a saved version, or choose New upload / preview to add a workbook. Reference curves are not active in sizing.")
    auth = get_auth_context()
    service = SupplierDegradationLibraryService(db_url)
    versions = []
    library_ready = False
    if auth and auth.is_admin:
        try:
            versions = service.list_versions(auth.user_id)
            library_ready = True
        except PermissionError as exc:
            st.error(str(exc))
        except SQLAlchemyError:
            st.warning("Candidate storage is unavailable. Complete the database migration before saving; upload preview remains available.")
    if versions:
        with st.expander(f"Saved version details ({len(versions)})", expanded=False):
            render_static_table([{"Version": v["version_label"], "File": v["filename"], "Status": "Saved · Not active",
                "Curves": v["curve_count"], "Source N/A points": v["missing_points"], "Imported at (UTC)": v["created_at"][:16].replace("T", " ")} for v in versions])
            st.caption("Source N/A points are blank in the supplier workbook; they are not failed imports.")
    else:
        st.caption("No saved candidate versions.")
    options = {v["import_id"]: v for v in versions}
    choices = [*options, "upload"]
    pending = st.session_state.pop("supplier_curve_pending_source", None)
    if pending in options:
        st.session_state["supplier_curve_review_source"] = pending
    elif st.session_state.get("supplier_curve_review_source", choices[0]) not in choices:
        st.session_state["supplier_curve_review_source"] = choices[0]
    source = st.selectbox("Review source", choices,
        format_func=lambda key: "New upload / preview" if key == "upload" else f'{options[key]["version_label"]} · {options[key]["created_at"][:16].replace("T", " ")}',
        key="supplier_curve_review_source")
    metadata = None
    if source != "upload":
        try:
            metadata, dataset, original = service.load_version(source, auth.user_id)
        except (ValueError, PermissionError) as exc:
            st.error(str(exc))
            return
        st.success(f'Saved candidate: {metadata["version_label"]} · {metadata["curve_count"]} curves · Not active in sizing.')
        _render_dataset(dataset, metadata)
        with st.expander("Original source file — unchanged supplier format", expanded=False):
            st.caption("For source verification only. Use the formatted Excel exports below for reading and analysis.")
            st.download_button("Download original supplier workbook", original, file_name=metadata["filename"],
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key="supplier_curve_original", on_click="ignore")
        return
    with st.container(key="supplier_curve_upload_box"):
        st.markdown('<style>.st-key-supplier_curve_upload_box [data-testid="stFileUploader"] small {display:none;}</style>', unsafe_allow_html=True)
        upload = st.file_uploader("Supplier degradation workbook", type=["xlsx"], key="supplier_curve_preview_upload", help="XLSX only. Maximum workbook size: 25 MB.")
        st.caption("XLSX workbook · Maximum 25 MB. If Windows says the file is in use, save and close it in Excel before selecting it.")
    if upload is None:
        return
    if upload_exceeds_limit(upload, limit=25 * 1024 * 1024):
        st.error("Workbook exceeds the 25 MB preview limit.")
        return
    try:
        dataset = _parse(upload.getvalue())
    except ValueError as exc:
        st.error(str(exc))
        return
    if library_ready:
        label = st.text_input("Candidate version name", value=getattr(upload, "name", "Supplier workbook").removesuffix(".xlsx"), key=f"supplier_curve_version_{dataset.source_sha256}")
        existing = next((v for v in versions if v["source_sha256"] == dataset.source_sha256), None)
        if existing:
            st.success(f'Already saved as candidate: {existing["version_label"]}. No duplicate was created.')
            metadata = existing
            if st.button("Open saved version", key="supplier_curve_open_existing"):
                st.session_state["supplier_curve_pending_source"] = existing["import_id"]
                st.rerun()
        elif st.button("Save all source curves as candidate", key="supplier_curve_save", type="primary"):
            try:
                metadata, created = service.save_candidate(upload.getvalue(), getattr(upload, "name", "supplier.xlsx"), label, auth.user_id)
            except (ValueError, PermissionError) as exc:
                st.error(str(exc))
            else:
                st.success("Candidate saved to database; available after refresh. No sizing defaults changed." if created else "This exact workbook is already saved.")
                st.session_state["supplier_curve_pending_source"] = metadata["import_id"]
                st.rerun()
    _render_dataset(dataset, metadata)


def _render_dataset(dataset, metadata=None):
    if metadata is None:
        st.info("Preview only. Save this workbook to reopen it after refreshing. Reference curves are not a system warranty.")
    series_col, soc_col, rate_col = st.columns([1.2, 1, 1])
    basis = series_col.selectbox("Source series", ["lower_limit", "mean"], format_func=lambda v: {"lower_limit": "Lower limit", "mean": "Mean"}[v], key="supplier_curve_basis",
        help="Mean is the supplier's average sheet; Lower limit is its lower-limit sheet. Statistical and warranty definitions are unconfirmed.")
    socs = sorted({c.soc_pct for c in dataset.curves if c.basis == basis})
    if st.session_state.get("supplier_curve_soc", socs[0]) not in socs:
        st.session_state["supplier_curve_soc"] = 50 if 50 in socs else socs[0]
    soc = soc_col.selectbox("Source SOC label (%)", socs, index=socs.index(50) if 50 in socs else 0, key="supplier_curve_soc", format_func=lambda v: f"{v:.2f}%",
        help="This is the original supplier SOC label, not DOD. Standby SOC versus cycling window remains unconfirmed.")
    rates = sorted({c.power_rate for c in dataset.curves if c.basis == basis and c.soc_pct == soc})
    if st.session_state.get("supplier_curve_rate", rates[0]) not in rates:
        st.session_state["supplier_curve_rate"] = 0.25 if 0.25 in rates else rates[0]
    rate = rate_col.selectbox("Source Power Rate", rates, index=rates.index(0.25) if 0.25 in rates else 0, key="supplier_curve_rate", format_func=lambda v: f"{v:g}",
        help="Source rate label. Nominal charging/discharging basis requires supplier confirmation.")
    cases = [c for c in dataset.curves if c.basis == basis and c.soc_pct == soc and c.power_rate == rate]
    extended = st.checkbox("Show extended daily frequencies above 2 cycles/day", key="supplier_curve_extended")
    frequencies = sorted({c.cycles_per_day for c in cases if extended or c.cycles_per_day <= 2})
    frequency_key = f"supplier_curve_frequency_{dataset.source_sha256}_{basis}_{soc}_{rate}"
    if frequency_key in st.session_state:
        valid_selected = [f for f in st.session_state[frequency_key] if f in frequencies]
        if valid_selected != st.session_state[frequency_key]:
            st.session_state[frequency_key] = valid_selected
    defaults = None if frequency_key in st.session_state else [n for n in [1, 2] if n in frequencies]
    selected = st.multiselect("Cycles/day", frequencies, default=defaults, key=frequency_key, format_func=lambda v: f"{v:g}")
    curves = [c for c in cases if c.cycles_per_day in selected]
    selected_col, all_col = st.columns(2)
    if curves:
        selected_col.download_button("Download selected curves — formatted Excel", _export(dataset, tuple(curves), metadata),
            file_name=f"CALB_Capacity_Retention_SOC{soc:g}_{'Lower' if basis == 'lower_limit' else 'Mean'}_Rate{rate:g}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key="supplier_curve_selected_export", on_click="ignore", type="primary", use_container_width=True)
    all_col.download_button("Download all curves — formatted Excel", _export(dataset, metadata=metadata),
        file_name="CALB_Capacity_Retention_All.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key="supplier_curve_all_export", on_click="ignore", use_container_width=True)
    st.caption("Selected = current filters. All = every source case, with common and extended cases on separate Excel worksheets.")
    if not curves:
        st.info("Select at least one daily frequency to display a curve.")
        return
    import matplotlib.pyplot as plt
    from matplotlib.ticker import PercentFormatter
    fig, ax = plt.subplots(figsize=(8, 3.6))
    for curve in curves:
        ax.plot(curve.years, curve.retention_pct, label=f"{curve.cycles_per_day:g} cycle{'s' if curve.cycles_per_day != 1 else ''}/day", linewidth=1.7)
    ax.set(xlabel="Source year", ylabel="Capacity retention (%)", ylim=(0, 105))
    ax.set_title(f"{'Lower limit' if basis == 'lower_limit' else 'Mean'} · SOC {soc:.2f}% · Power Rate {rate:g}", fontsize=10)
    ax.yaxis.set_major_formatter(PercentFormatter(xmax=100, decimals=2))
    ax.grid(alpha=0.2)
    ax.legend()
    fig.tight_layout()
    st.pyplot(fig)
    plt.close(fig)
    rows = [{"Year": year, **{f"{c.cycles_per_day:g} cycle{'s' if c.cycles_per_day != 1 else ''}/day": "N/A" if c.retention_pct[i] is None else f"{c.retention_pct[i]:.2f}%" for c in curves}} for i, year in enumerate(curves[0].years)]
    with st.expander("Annual capacity table — two decimal percentages", expanded=False):
        render_static_table(rows)
        st.caption("N/A means the supplier supplied no value; it is not an import failure. No missing-year extension or interpolation is applied.")
    for curve in curves:
        last_year = curve.last_supported_year if curve.last_supported_year is not None else "N/A"
        st.caption(f"{curve.cycles_per_day:g} cycle{'s' if curve.cycles_per_day != 1 else ''}/day: source values through Year {last_year}.")
        for issue in curve.issues:
            st.warning(issue)
        # A reference screen, not a modification of supplier retention values.
        hours = curve.cycles_per_day * (2 / curve.power_rate + 1)
        if hours > 24:
            st.warning(f"{curve.cycles_per_day:g} cycles/day would need {hours:.2f} h/day at 100% depth, equal charge/discharge rates and two 30-minute rests per cycle. That assumed schedule does not fit 24 hours.")
    with st.expander("Source definitions and timing assumptions", expanded=False):
        st.caption("SOC and Power Rate are original supplier labels. SOC standby/window meaning, rate definition and Mean/lower-limit statistical or warranty basis remain unconfirmed. Reference data are not applied to sizing or a system warranty.")
        st.caption("Timing assumes 100% cycle depth, equal compatible nominal charge/discharge rates and two 30-minute rests per cycle. This is a conditional screen, not verified dispatch feasibility.")
        if not dataset.rte_numeric_values or not dataset.calendar_numeric_values:
            st.caption("No numeric RTE data or no separate calendar-aging table is supplied. Existing platform RTE data are unchanged; calendar and cycle losses are not recombined.")
