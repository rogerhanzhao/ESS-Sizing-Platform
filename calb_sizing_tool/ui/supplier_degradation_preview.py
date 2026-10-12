"""Supplier curve review on the existing admin Degradation page."""
from __future__ import annotations

import csv
from io import StringIO

import streamlit as st

from calb_sizing_tool.services.supplier_degradation_service import parse_supplier_degradation
from calb_sizing_tool.ui._ui import render_static_table
from calb_sizing_tool.utils.files import upload_exceeds_limit


@st.cache_data(max_entries=4, show_spinner=False)
def _parse(data):
    return parse_supplier_degradation(data)


def render_supplier_degradation_preview():
    st.caption("Review original supplier curves before selecting data for the sizing database.")
    upload = st.file_uploader("Supplier degradation workbook", type=["xlsx"], key="supplier_curve_preview_upload")
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
    st.info("Preview only. SOC is reproduced as a source label; its standby/window meaning and the Power Rate definition are unconfirmed. These values have not been applied to sizing or a system warranty.")
    st.caption(f"{len(dataset.curves)} source curves · SHA-256 {dataset.source_sha256}")
    if not dataset.rte_numeric_values or not dataset.calendar_numeric_values:
        st.caption("This workbook has no numeric RTE data or no separate calendar-aging table. Existing platform RTE data are not replaced; the source's calendar-aging treatment remains unconfirmed.")
    basis = st.selectbox("Source series", ["lower_limit", "mean"], format_func=lambda v: {"lower_limit": "Lower limit", "mean": "Mean"}[v], key="supplier_curve_basis")
    socs = sorted({c.soc_pct for c in dataset.curves})
    soc = st.selectbox("Source SOC label (%)", socs, index=socs.index(50) if 50 in socs else 0, key="supplier_curve_soc")
    rates = sorted({c.power_rate for c in dataset.curves if c.basis == basis and c.soc_pct == soc})
    rate = st.selectbox("Source Power Rate", rates, index=rates.index(0.25) if 0.25 in rates else 0, key="supplier_curve_rate")
    cases = [c for c in dataset.curves if c.basis == basis and c.soc_pct == soc and c.power_rate == rate]
    extended = st.checkbox("Show extended daily frequencies above 2 cycles/day", key="supplier_curve_extended")
    frequencies = sorted({c.cycles_per_day for c in cases if extended or c.cycles_per_day <= 2})
    selected = st.multiselect("Cycles/day", frequencies, default=[n for n in [1, 2] if n in frequencies], key=f"supplier_curve_frequency_{dataset.source_sha256}_{rate}_{extended}")
    curves = [c for c in cases if c.cycles_per_day in selected]
    if not curves:
        st.info("Select at least one daily frequency.")
        return
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(8, 3.6))
    for curve in curves:
        ax.plot(curve.years, curve.retention_pct, label=f"{curve.cycles_per_day:g} cycles/day", linewidth=1.7)
    ax.set(xlabel="Source year", ylabel="Capacity retention (%)", ylim=(0, 105))
    ax.grid(alpha=0.2)
    ax.legend()
    fig.tight_layout()
    st.pyplot(fig)
    plt.close(fig)
    rows = [{"Year": year, **{f"{c.cycles_per_day:g} cycles/day": "N/A" if c.retention_pct[i] is None else f"{c.retention_pct[i]:.2f}%" for c in curves}} for i, year in enumerate(curves[0].years)]
    render_static_table(rows)
    st.caption("N/A means the supplier supplied no value. Lines join annual source checkpoints; no missing-year extension or duty-case interpolation is applied.")
    for curve in curves:
        st.caption(f"{curve.cycles_per_day:g} cycles/day: source values through Year {curve.last_supported_year}.")
        for issue in curve.issues:
            st.warning(issue)
        # A reference screen, not a modification of supplier retention values.
        hours = curve.cycles_per_day * (2 / curve.power_rate + 1)
        if hours > 24:
            st.warning(f"{curve.cycles_per_day:g} cycles/day would need {hours:.2f} h/day at 100% depth, equal charge/discharge rates and two 30-minute rests per cycle. That assumed schedule does not fit 24 hours.")
    st.caption("The timing screen assumes Power Rate is a compatible nominal charge/discharge rate; the supplier has not confirmed that basis or actual cycle depth. Calendar and cycling losses are not recombined here.")
    csv_text = StringIO()
    writer = csv.writer(csv_text)
    writer.writerow(["source_sha256", "sheet", "source_soc_pct", "source_power_rate", "cycles_per_day", "year", "retention_pct", "source_cell"])
    for c in curves:
        for year, value, cell in zip(c.years, c.retention_pct, c.source_cells):
            writer.writerow([dataset.source_sha256, c.sheet, c.soc_pct, c.power_rate, c.cycles_per_day, year, value if value is not None else "", cell])
    st.download_button("Download selected reference data (CSV)", csv_text.getvalue().encode("utf-8-sig"), file_name="supplier_degradation_reference.csv", mime="text/csv", key="supplier_curve_csv")
