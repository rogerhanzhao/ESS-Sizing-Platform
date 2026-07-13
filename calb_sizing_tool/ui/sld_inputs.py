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

from __future__ import annotations

import streamlit as st

from calb_sizing_tool.schemas.sld_render_input import (
    SldDcFuseSpec,
    SldEquipmentRatings,
    SldInputOverride,
    SldLabels,
    SldLvBusbarRatings,
    SldCableSpecs,
    SldRmuRatings,
    legacy_sld_override_preset,
)
from calb_sizing_tool.sld.voltage_contract import resolve_mv_rmu_voltage_contract


def _safe_float(value, default):
    try:
        return float(value)
    except Exception:
        return default


def render_electrical_inputs(
    defaults: dict | None,
    key_prefix: str | None = None,
    *,
    mv_nominal_voltage_kv: float | None = None,
    section_title: str = "SLD Override Inputs",
    section_caption: str | None = None,
) -> SldInputOverride:
    """Draft-only UI override collector.

    Formal SLD generation must rely on authoritative runtime/project inputs. This
    form exists only for explicit override_mode workflows.
    """
    defaults = defaults or legacy_sld_override_preset()
    key_prefix = key_prefix or "sld_inputs"
    labels = defaults.get("labels", {}) if isinstance(defaults.get("labels"), dict) else {}
    if not labels and isinstance(defaults.get("mv_labels"), dict):
        labels = defaults.get("mv_labels", {})
    equipment_defaults = (
        defaults.get("equipment_ratings", {}) if isinstance(defaults.get("equipment_ratings"), dict) else {}
    )
    transformer_defaults = defaults.get("transformer", {}) if isinstance(defaults.get("transformer"), dict) else {}
    rmu_defaults = equipment_defaults.get("rmu", {}) if isinstance(equipment_defaults.get("rmu"), dict) else {}
    bus_defaults = (
        equipment_defaults.get("lv_busbar", {}) if isinstance(equipment_defaults.get("lv_busbar"), dict) else {}
    )
    cable_defaults = (
        equipment_defaults.get("cables", {}) if isinstance(equipment_defaults.get("cables"), dict) else {}
    )
    fuse_defaults = (
        equipment_defaults.get("dc_fuse", {}) if isinstance(equipment_defaults.get("dc_fuse"), dict) else {}
    )

    st.subheader(section_title)
    st.caption(section_caption or "Legacy preset values are only allowed when override mode is explicitly enabled.")

    def _key(field: str) -> str:
        return f"{key_prefix}.{field}"

    label_c1, label_c2 = st.columns(2)
    to_switchgear = label_c1.text_input(
        "MV label: to switchgear",
        value=labels.get("to_switchgear") or "To Switchgear",
        key=_key("mv_label_to_switchgear"),
    )
    to_other_rmu = label_c2.text_input(
        "MV label: to other RMU",
        value=labels.get("to_other_rmu") or "To Other RMU",
        key=_key("mv_label_to_other_rmu"),
    )

    contract = None
    try:
        contract = resolve_mv_rmu_voltage_contract(mv_nominal_voltage_kv=mv_nominal_voltage_kv)
    except ValueError:
        contract = None
    visible_mv_kv = contract.authoritative_mv_voltage_kv if contract else None
    derived_rmu_kv = contract.rmu_rated_voltage_kv if contract else _safe_float(rmu_defaults.get("rated_kv"), 24.0)

    for stale_key in (
        _key("rmu_rated_kv"),
        _key("rmu_rated_kv_auto"),
        _key("rmu_rated_kv_manual"),
        _key("rmu_rated_kv_manual_override"),
    ):
        if stale_key in st.session_state:
            st.session_state.pop(stale_key)

    rmu_derived_value_key = _key("rmu_rated_kv_derived")
    st.session_state[rmu_derived_value_key] = derived_rmu_kv

    st.markdown("**RMU**")
    if visible_mv_kv is not None:
        st.caption(
            f"RMU rated voltage follows POI / MV Voltage (kV): {visible_mv_kv:.1f} kV. "
            "This page does not redefine a second RMU voltage input."
        )
    else:
        st.caption("POI / MV Voltage is unavailable. RMU rated voltage display falls back to the current draft preset.")
    r1, r2, r3 = st.columns(3)
    rmu_rated_kv = r1.number_input(
        "RMU rated voltage (kV)",
        min_value=0.0,
        value=_safe_float(st.session_state.get(rmu_derived_value_key), derived_rmu_kv),
        key=rmu_derived_value_key,
        step=0.1,
        disabled=True,
        help="Derived directly from POI / MV Voltage (kV).",
    )
    rmu_rated_a = r2.number_input(
        "Rated current (A)",
        min_value=0.0,
        value=_safe_float(rmu_defaults.get("rated_a"), 630.0),
        key=_key("rmu_rated_a"),
        step=10.0,
    )
    rmu_short_circuit_ka = r3.number_input(
        "Short-circuit (kA/3s)",
        min_value=0.0,
        value=_safe_float(rmu_defaults.get("short_circuit_ka_3s"), 25.0),
        key=_key("rmu_short_circuit_ka_3s"),
        step=1.0,
    )
    r4, r5, r6 = st.columns(3)
    rmu_ct_ratio = r4.text_input(
        "CT ratio",
        value=rmu_defaults.get("ct_ratio") or "200/1",
        key=_key("rmu_ct_ratio"),
    )
    rmu_ct_class = r5.text_input(
        "CT class",
        value=rmu_defaults.get("ct_class") or "5P20",
        key=_key("rmu_ct_class"),
    )
    rmu_ct_va = r6.number_input(
        "CT burden (VA)",
        min_value=0.0,
        value=_safe_float(rmu_defaults.get("ct_va"), 10.0),
        key=_key("rmu_ct_va"),
        step=1.0,
    )

    st.markdown("**Transformer / DC Block**")
    t1, t2, t3, t4 = st.columns(4)
    tr_vector_group = t1.text_input(
        "Vector group",
        value=defaults.get("transformer_vector_group") or transformer_defaults.get("vector_group") or "Dyn11",
        key=_key("tr_vector_group"),
    )
    tr_uk_percent = t2.number_input(
        "Uk (%)",
        min_value=0.0,
        value=_safe_float(
            defaults.get("transformer_uk_percent", transformer_defaults.get("uk_percent")),
            7.0,
        ),
        key=_key("tr_uk_percent"),
        step=0.1,
    )
    tr_tap_range = t3.text_input(
        "Tap range",
        value=equipment_defaults.get("transformer_tap_range") or "+/-2x2.5%",
        key=_key("tr_tap_range"),
    )
    tr_cooling = t4.text_input(
        "Cooling",
        value=equipment_defaults.get("transformer_cooling") or "ONAN",
        key=_key("tr_cooling"),
    )
    d1 = st.columns(1)[0]
    dc_block_voltage_v = d1.number_input(
        "DC block voltage (V)",
        min_value=0.0,
        value=_safe_float(defaults.get("dc_block_voltage_v"), 1500.0),
        key=_key("dc_block_voltage_v"),
        step=10.0,
    )

    st.markdown("**LV Busbar**")
    b1, b2, b3 = st.columns(3)
    lv_rated_a = b1.number_input(
        "Rated current (A, per winding)",
        min_value=0.0,
        value=_safe_float(bus_defaults.get("rated_a"), 2500.0),
        key=_key("lv_rated_a"),
        step=10.0,
    )
    lv_short_circuit_ka = b2.number_input(
        "Short-circuit (kA)",
        min_value=0.0,
        value=_safe_float(bus_defaults.get("short_circuit_ka"), 25.0),
        key=_key("lv_short_circuit_ka"),
        step=1.0,
    )
    lv_winding_count = b3.number_input(
        "LV windings (split-secondary)",
        min_value=1,
        max_value=4,
        value=int(_safe_float(defaults.get("lv_winding_count"), 1.0)),
        key=_key("lv_winding_count"),
        step=1,
        help=(
            "Independent LV secondaries on the step-up transformer. Use 2 for a "
            "split-winding (dual-secondary) block: the LV current then divides "
            "across two busbars, and 'Rated current' above is checked per winding."
        ),
    )

    st.markdown("**Cables**")
    c1, c2, c3 = st.columns(3)
    mv_cable_spec = c1.text_input(
        "MV cable spec",
        value=cable_defaults.get("mv_cable_spec") or "TBD",
        key=_key("mv_cable_spec"),
    )
    lv_cable_spec = c2.text_input(
        "LV cable spec",
        value=cable_defaults.get("lv_cable_spec") or "TBD",
        key=_key("lv_cable_spec"),
    )
    dc_cable_spec = c3.text_input(
        "DC cable spec",
        value=cable_defaults.get("dc_cable_spec") or "TBD",
        key=_key("dc_cable_spec"),
    )

    st.markdown("**DC Fuse**")
    fuse_spec = st.text_input(
        "Fuse spec",
        value=fuse_defaults.get("fuse_spec") or "DC isolator/fuse",
        key=_key("dc_fuse_spec"),
    )

    st.markdown("**BESS**")
    battery_cell_spec = st.text_input(
        "BESS cell spec",
        value=equipment_defaults.get("battery_cell_spec") or "",
        key=_key("battery_cell_spec"),
        help="Optional professional note field for the SLD left-side equipment list.",
    )

    return SldInputOverride(
        transformer_vector_group=tr_vector_group,
        transformer_uk_percent=tr_uk_percent,
        lv_winding_count=int(lv_winding_count),
        dc_block_voltage_v=dc_block_voltage_v,
        labels=SldLabels(
            to_switchgear=to_switchgear,
            to_other_rmu=to_other_rmu,
        ),
        equipment_ratings=SldEquipmentRatings(
            rmu=SldRmuRatings(
                rated_kv=rmu_rated_kv,
                rated_a=rmu_rated_a,
                short_circuit_ka_3s=rmu_short_circuit_ka,
                ct_ratio=rmu_ct_ratio,
                ct_class=rmu_ct_class,
                ct_va=rmu_ct_va,
            ),
            lv_busbar=SldLvBusbarRatings(
                rated_a=lv_rated_a,
                short_circuit_ka=lv_short_circuit_ka,
            ),
            cables=SldCableSpecs(
                mv_cable_spec=mv_cable_spec,
                lv_cable_spec=lv_cable_spec,
                dc_cable_spec=dc_cable_spec,
            ),
            dc_fuse=SldDcFuseSpec(
                fuse_spec=fuse_spec,
            ),
            transformer_tap_range=tr_tap_range,
            transformer_cooling=tr_cooling,
            battery_cell_spec=battery_cell_spec.strip() or None,
        ),
    )
