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

import datetime
import hashlib
import importlib
import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from calb_sizing_tool.common.ac_block import derive_ac_template_fields
from calb_sizing_tool.config import AC_DATA_PATH, DC_DATA_PATH
from calb_sizing_tool.runtime_paths import get_outputs_dir


@dataclass
class ReportContext:
    project_name: str
    scenario_id: str
    poi_power_requirement_mw: float
    poi_energy_requirement_mwh: float
    poi_energy_guarantee_mwh: float
    poi_usable_energy_mwh_at_guarantee_year: Optional[float]
    poi_usable_energy_mwh_at_year0: Optional[float]
    poi_guarantee_year: int
    project_life_years: int
    cycles_per_year: int
    grid_mv_voltage_kv_ac: Optional[float]
    pcs_lv_voltage_v_ll_rms_ac: Optional[float]
    grid_power_factor: Optional[float]
    ac_block_template_id: str
    pcs_per_block: int
    feeders_per_block: int
    dc_blocks_total: int
    ac_blocks_total: int
    pcs_modules_total: int
    transformer_rating_kva: Optional[float]
    ac_block_size_mw: Optional[float]
    dc_block_unit_mwh: Optional[float]
    dc_total_energy_mwh: Optional[float]
    efficiency_chain_oneway_frac: float
    efficiency_components_frac: Dict[str, float]
    avg_dc_blocks_per_ac_block: Optional[float]
    dc_blocks_allocation: List[Dict[str, int]]
    qc_checks: List[str]
    dictionary_version_dc: str
    dictionary_version_ac: str
    # --- governed configuration identity (carried directly from ac_output) ---
    # When present, Report / Site Array must route by these fields rather than
    # rebuilding the unit from the average DC-per-AC ratio.
    configuration_code: Optional[str] = None
    layout_variant: Optional[str] = None
    # --- DB provenance (populated from workspace session state) ---
    run_id: Optional[str] = None
    ac_run_id: Optional[str] = None
    project_code: Optional[str] = None
    case_code: Optional[str] = None
    case_name: Optional[str] = None
    report_generated_at: str = ""
    # --- SLD / layout ---
    sld_snapshot_id: Optional[str] = None
    sld_snapshot_hash: Optional[str] = None
    sld_generated_at: Optional[str] = None
    sld_group_index: Optional[int] = None
    sld_preview_svg_bytes: Optional[bytes] = None
    sld_pro_png_bytes: Optional[bytes] = None
    layout_png_bytes: Optional[bytes] = None
    layout_svg_bytes: Optional[bytes] = None
    stage1: Dict[str, Any] = field(default_factory=dict)
    stage2: Dict[str, Any] = field(default_factory=dict)
    stage3_df: Any = None
    stage3_meta: Dict[str, Any] = field(default_factory=dict)
    ac_output: Dict[str, Any] = field(default_factory=dict)
    project_inputs: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_session_state(
        cls,
        session_state: Optional[dict],
        stage_outputs: Optional[dict] = None,
        project_inputs: Optional[dict] = None,
        scenario_ids=None,
    ) -> "ReportContext":
        return build_report_context(session_state, stage_outputs, project_inputs, scenario_ids)


def _snapshot_hash(snapshot: dict) -> str:
    payload = json.dumps(snapshot, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


def _safe_int(value, default=0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _parse_template_count(template_id: Optional[str]) -> Optional[int]:
    if not template_id:
        return None
    match = re.search(r"(\d+)\s*x", str(template_id).lower())
    if match:
        try:
            return int(match.group(1))
        except Exception:
            return None
    return None


def _extract_dc_unit_mwh(stage2: dict) -> Optional[float]:
    df = stage2.get("block_config_table") if isinstance(stage2, dict) else None
    if df is None or df.empty:
        return None
    if "Unit Capacity (MWh)" not in df.columns:
        return None
    units = [float(v) for v in df["Unit Capacity (MWh)"].dropna().unique().tolist()]
    if len(units) == 1:
        return units[0]
    return None


def _extract_dc_total_energy_mwh(stage2: dict) -> Optional[float]:
    if not isinstance(stage2, dict):
        return None
    total = stage2.get("dc_nameplate_bol_mwh")
    if total is not None:
        try:
            return float(total)
        except Exception:
            return None
    df = stage2.get("block_config_table")
    if df is None or df.empty or "Subtotal (MWh)" not in df.columns:
        return None
    try:
        return float(df["Subtotal (MWh)"].sum())
    except Exception:
        return None


def _pick_scenario_id(stage13_output: dict, scenario_ids):
    if isinstance(scenario_ids, (list, tuple)):
        if scenario_ids:
            return scenario_ids[0]
    if scenario_ids:
        return str(scenario_ids)
    return stage13_output.get("selected_scenario", "container_only")


def _get_stage3_df(stage1: dict, stage2: dict):
    try:
        dc_view = importlib.import_module("calb_sizing_tool.ui.dc_view")
        _, _, df_soh_profile, df_soh_curve, df_rte_profile, df_rte_curve = dc_view.load_data(DC_DATA_PATH)
        return dc_view.run_stage3(stage1, stage2, df_soh_profile, df_soh_curve, df_rte_profile, df_rte_curve)
    except Exception as exc:
        # Capture and return an error message so the report can surface the root cause
        try:
            msg = str(exc)
        except Exception:
            msg = "Unknown error while computing Stage 3"
        return None, {"error": msg}


def build_report_context(
    session_state: Optional[dict] = None,
    stage_outputs: Optional[dict] = None,
    project_inputs: Optional[dict] = None,
    scenario_ids=None,
) -> ReportContext:
    state = session_state or {}
    outputs = stage_outputs or {}

    dc_results = state.get("dc_results") if isinstance(state, dict) else {}
    stage13_output = (
        outputs.get("stage13_output")
        or state.get("stage13_output")
        or (dc_results.get("stage13_output") if isinstance(dc_results, dict) else None)
        or outputs.get("stage1")
    )
    if not stage13_output:
        raise ValueError("stage13_output is required to build ReportContext.")

    stage1 = stage13_output
    stage2 = outputs.get("stage2") or stage13_output.get("stage2_raw") or {}
    # Prefer an explicit stage3_df passed in outputs, then any stage3_df embedded in
    # the stage13_output (packaged by DC UI). If none, attempt to recompute.
    stage3_df = outputs.get("stage3_df")
    if stage3_df is None:
        stage3_df = stage13_output.get("stage3_df")
    stage3_meta = outputs.get("stage3_meta") or stage13_output.get("stage3_meta") or {}
    if stage3_df is None:
        stage3_df, stage3_meta = _get_stage3_df(stage1, stage2)

    ac_results = state.get("ac_results") if isinstance(state, dict) else {}
    ac_output = outputs.get("ac_output") or ac_results or state.get("ac_output") or {}
    project_name = None
    if isinstance(state, dict):
        project_name = state.get("project_name")
    project_name = (
        project_name
        or stage1.get("project_name")
        or ac_output.get("project_name")
        or (project_inputs or {}).get("project_name")
        or "CALB ESS Project"
    )
    if project_inputs is None:
        project_inputs = {}
    if project_inputs.get("poi_frequency_hz") is None and stage1.get("poi_frequency_hz") is not None:
        project_inputs["poi_frequency_hz"] = stage1.get("poi_frequency_hz")

    scenario_id = _pick_scenario_id(stage13_output, scenario_ids)

    dc_blocks_total = int(stage2.get("container_count", 0)) + int(stage2.get("cabinet_count", 0))
    if dc_blocks_total == 0:
        dc_blocks_total = int(stage13_output.get("dc_block_total_qty", 0))

    ac_blocks_total = _safe_int(ac_output.get("num_blocks") or ac_output.get("ac_blocks_total"), 0)
    if ac_blocks_total <= 0:
        allocation_plan = ac_output.get("dc_allocation_plan")
        if isinstance(allocation_plan, list) and allocation_plan:
            ac_blocks_total = len(allocation_plan)
        else:
            pcs_count_by_block = ac_output.get("pcs_count_by_block")
            if isinstance(pcs_count_by_block, list) and pcs_count_by_block:
                ac_blocks_total = len(pcs_count_by_block)

    pcs_modules_total = _safe_int(ac_output.get("pcs_count_total") or ac_output.get("total_pcs"), 0)
    if pcs_modules_total <= 0:
        pcs_count_by_block = ac_output.get("pcs_count_by_block")
        if isinstance(pcs_count_by_block, list) and pcs_count_by_block:
            pcs_modules_total = sum(_safe_int(v, 0) for v in pcs_count_by_block)

    template_fields = derive_ac_template_fields(ac_output)
    ac_block_template_id = template_fields["ac_block_template_id"]
    pcs_per_block = int(template_fields["pcs_per_block"])
    feeders_per_block = int(template_fields["feeders_per_block"])
    grid_power_factor = template_fields["grid_power_factor"]

    if pcs_modules_total <= 0 and ac_blocks_total > 0 and pcs_per_block > 0:
        pcs_modules_total = ac_blocks_total * pcs_per_block

    transformer_rating_kva = ac_output.get("transformer_kva")
    if transformer_rating_kva is None:
        transformer_rating_kva = ac_output.get("transformer_rating_kva")
    if transformer_rating_kva is None:
        transformer_mva = ac_output.get("transformer_mva")
        try:
            if transformer_mva is not None:
                transformer_rating_kva = float(transformer_mva) * 1000.0
        except Exception:
            transformer_rating_kva = None
    # Legacy convenience fallback: derive a nameplate from AC power / power
    # factor. A governed configuration must NOT get this silent estimate — its
    # transformer MVA is an owner-confirmed value or it stays unresolved (TBD),
    # exactly as the strict SLD contract requires (never promote 10 MW / 0.9 to
    # an approved 11.11 MVA nameplate). See
    # docs/GOVERNED_AC_BLOCK_10MW_8PCS_8DC_2026-07-24.md §5.
    is_governed = bool(ac_output.get("governed_configuration")) if isinstance(ac_output, dict) else False
    if transformer_rating_kva is None and not is_governed:
        try:
            block_size_mw = float(ac_output.get("block_size_mw") or 0.0)
        except Exception:
            block_size_mw = 0.0
        if block_size_mw > 0 and grid_power_factor and grid_power_factor > 0:
            transformer_rating_kva = block_size_mw * 1000.0 / grid_power_factor

    poi_power_requirement_mw = float(stage1.get("poi_power_req_mw", 0.0) or 0.0)
    poi_energy_requirement_mwh = float(stage1.get("poi_energy_req_mwh", 0.0) or 0.0)
    poi_energy_guarantee_mwh = float(
        (project_inputs or {}).get("poi_energy_guarantee_mwh", poi_energy_requirement_mwh)
    )

    poi_guarantee_year = int(stage1.get("poi_guarantee_year", 0) or 0)
    project_life_years = int(stage1.get("project_life_years", 0) or 0)
    cycles_per_year = int(stage1.get("cycles_per_year", 0) or 0)

    # Read efficiency values from DC SIZING stage1 output (DC SIZING page computes these)
    # Do NOT use fallback defaults for report - if values are missing, user needs to re-run DC SIZING
    eff_dc_cables = float(stage1.get("eff_dc_cables_frac", 0.0) or 0.0)
    eff_pcs = float(stage1.get("eff_pcs_frac", 0.0) or 0.0)
    eff_mvt = float(stage1.get("eff_mvt_frac", 0.0) or 0.0)
    eff_ac_cables_sw_rmu = float(stage1.get("eff_ac_cables_sw_rmu_frac", 0.0) or 0.0)
    eff_hvt_others = float(stage1.get("eff_hvt_others_frac", 0.0) or 0.0)
    eff_chain = float(stage1.get("eff_dc_to_poi_frac", 0.0) or 0.0)
    
    efficiency_components = {
        "eff_dc_cables_frac": eff_dc_cables,
        "eff_pcs_frac": eff_pcs,
        "eff_mvt_frac": eff_mvt,
        "eff_ac_cables_sw_rmu_frac": eff_ac_cables_sw_rmu,
        "eff_hvt_others_frac": eff_hvt_others,
    }
    efficiency_chain_oneway = eff_chain

    avg_dc_blocks_per_ac_block = None
    dc_blocks_allocation = []
    if ac_blocks_total > 0:
        avg_dc_blocks_per_ac_block = dc_blocks_total / ac_blocks_total
        base = dc_blocks_total // ac_blocks_total
        remainder = dc_blocks_total % ac_blocks_total
        if remainder > 0:
            dc_blocks_allocation.append(
                {"dc_blocks_per_ac_block": base + 1, "ac_blocks_count": remainder}
            )
        base_count = ac_blocks_total - remainder
        if base_count > 0:
            dc_blocks_allocation.append(
                {"dc_blocks_per_ac_block": base, "ac_blocks_count": base_count}
            )

    poi_usable_year0 = None
    poi_usable_guarantee = None
    if stage3_df is not None and not stage3_df.empty:
        year0 = stage3_df[stage3_df["Year_Index"] == 0]
        if not year0.empty:
            poi_usable_year0 = float(year0["POI_Usable_Energy_MWh"].iloc[0])
        g_row = stage3_df[stage3_df["Year_Index"] == poi_guarantee_year]
        if not g_row.empty:
            poi_usable_guarantee = float(g_row["POI_Usable_Energy_MWh"].iloc[0])

    qc_checks = []
    if poi_energy_guarantee_mwh is None:
        qc_checks.append("POI energy guarantee value is missing.")
    if abs(poi_energy_requirement_mwh - poi_energy_guarantee_mwh) > 1e-6:
        qc_checks.append(
            "POI energy requirement differs from POI energy guarantee. Stage 3 checks use guarantee value."
        )
    if ac_blocks_total > 0 and pcs_per_block > 0:
        expected_pcs = ac_blocks_total * pcs_per_block
        if pcs_modules_total and pcs_modules_total != expected_pcs:
            qc_checks.append(
                f"PCS module mismatch: expected {expected_pcs}, got {pcs_modules_total}."
            )
    allocation_plan = ac_output.get("dc_allocation_plan")
    if isinstance(allocation_plan, list) and allocation_plan:
        if ac_blocks_total and len(allocation_plan) != ac_blocks_total:
            qc_checks.append(
                f"AC block count mismatch: allocation plan has {len(allocation_plan)} blocks, "
                f"but report uses {ac_blocks_total}."
            )
    selected_ratio = ac_output.get("selected_ratio")
    if selected_ratio in ("1:1", "1:2", "1:4") and dc_blocks_total > 0:
        ratio_map = {"1:1": 1, "1:2": 2, "1:4": 4}
        denom = ratio_map.get(selected_ratio)
        if denom:
            expected_blocks = int(math.ceil(dc_blocks_total / denom))
            if ac_blocks_total and expected_blocks != ac_blocks_total:
                qc_checks.append(
                    f"AC block count mismatch: ratio {selected_ratio} implies {expected_blocks} blocks "
                    f"for {dc_blocks_total} DC blocks, but report uses {ac_blocks_total}."
                )
    if ac_blocks_total > 0 and feeders_per_block > 0:
        feeders_total = ac_blocks_total * feeders_per_block
        if ac_output.get("feeders_total") and int(ac_output.get("feeders_total")) != feeders_total:
            qc_checks.append(
                f"Feeder count mismatch: expected {feeders_total}, got {ac_output.get('feeders_total')}."
            )
    if ac_blocks_total > 0 and dc_blocks_total == 0:
        qc_checks.append("DC block total is zero while AC blocks exist.")
    if grid_power_factor is None or grid_power_factor <= 0 or grid_power_factor > 1:
        qc_checks.append("Grid power factor is out of range (0, 1].")
    if not ac_block_template_id:
        qc_checks.append("AC block template ID could not be resolved.")
    template_count = _parse_template_count(ac_block_template_id)
    if template_count and pcs_per_block and template_count != pcs_per_block:
        qc_checks.append(
            f"AC block template indicates {template_count} PCS but sizing uses {pcs_per_block} PCS per block."
        )
    if template_count and feeders_per_block and template_count != feeders_per_block:
        qc_checks.append(
            f"AC block template indicates {template_count} feeders but sizing uses {feeders_per_block} feeders per block."
        )
    if poi_usable_guarantee is None:
        qc_checks.append("POI usable energy at guarantee year could not be resolved.")
    if poi_usable_guarantee is not None and poi_energy_guarantee_mwh is not None:
        if poi_usable_guarantee + 1e-6 < poi_energy_guarantee_mwh:
            qc_checks.append(
                "POI usable energy at guarantee year is below the guarantee target."
            )
    if stage2.get("busbars_needed") is not None:
        qc_checks.append("DC busbar grouping not implemented in V2.1 report; field omitted.")

    # --- DB provenance from workspace context (set by persist/restore services) ---
    run_id = (
        state.get("active_run_id")
        or state.get("dc_last_run_id")
        or outputs.get("run_id")
    )
    project_code = state.get("active_project_code") or outputs.get("project_code")
    case_code = state.get("active_case_code") or outputs.get("case_code")
    case_name = state.get("active_case_name") or outputs.get("case_name")
    report_generated_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M UTC+0")
    # AC run ID: stored in ac_output by the AC view as source_ac_run_id
    ac_run_id = None
    if isinstance(ac_output, dict):
        ac_run_id = ac_output.get("source_ac_run_id")

    sld_snapshot = outputs.get("sld_snapshot") or state.get("sld_snapshot")
    sld_snapshot_id = None
    sld_snapshot_hash = None
    sld_generated_at = None
    sld_group_index = None
    if isinstance(sld_snapshot, dict):
        sld_snapshot_id = sld_snapshot.get("snapshot_id")
        sld_generated_at = sld_snapshot.get("generated_at")
        sld_snapshot_hash = sld_snapshot.get("snapshot_hash") or _snapshot_hash(sld_snapshot)
        sld_group_index = _safe_int(
            sld_snapshot.get("group_index") or sld_snapshot.get("ac_block", {}).get("group_index"),
            0,
        )
        if sld_group_index <= 0:
            sld_group_index = None

    sld_preview_svg_bytes = None
    sld_pro_png_bytes = None
    layout_png_bytes = None
    layout_svg_bytes = None

    def _extract_bundle(bundle) -> tuple[bytes | None, bytes | None]:
        """Extract (png, svg) from a DiagramArtifactBundle.artifacts list[dict]."""
        png = svg = None
        artifact_list = getattr(bundle, "artifacts", None)
        if not isinstance(artifact_list, list):
            return png, svg
        for item in artifact_list:
            if not isinstance(item, dict):
                continue
            kind = item.get("artifact_kind", "")
            content = item.get("content")
            if not content:
                continue
            if kind.endswith("_png") and png is None:
                png = content
            elif kind.endswith("_svg") and svg is None:
                svg = content
        return png, svg

    # st.session_state is a SessionState proxy (not a dict subclass) but supports .get()
    try:
        # Priority 1: new plugin-based bundles (sld_artifacts / layout_artifacts)
        _sld_bundle = state.get("sld_artifacts")
        if _sld_bundle is not None:
            sld_pro_png_bytes, sld_preview_svg_bytes = _extract_bundle(_sld_bundle)

        _layout_bundle = state.get("layout_artifacts")
        if _layout_bundle is not None:
            layout_png_bytes, layout_svg_bytes = _extract_bundle(_layout_bundle)

        # Priority 2: artifacts dict (written back by report_export_view after resolution)
        _artifacts = state.get("artifacts")
        if isinstance(_artifacts, dict):
            sld_pro_png_bytes = sld_pro_png_bytes or _artifacts.get("sld_png_bytes")
            sld_preview_svg_bytes = sld_preview_svg_bytes or _artifacts.get("sld_svg_bytes")
            layout_png_bytes = layout_png_bytes or _artifacts.get("layout_png_bytes")
            layout_svg_bytes = layout_svg_bytes or _artifacts.get("layout_svg_bytes")

        # Priority 3: legacy diagram_results / layout_results dicts (old sessions)
        if sld_pro_png_bytes is None:
            diagram_results = state.get("diagram_results") or {}
            if isinstance(diagram_results, dict):
                for style_key in (diagram_results.get("last_style"), "raw_v05", "pro_v10", "jp_v08"):
                    entry = diagram_results.get(style_key) if style_key else None
                    if isinstance(entry, dict):
                        sld_pro_png_bytes = sld_pro_png_bytes or entry.get("png")
                        sld_preview_svg_bytes = sld_preview_svg_bytes or entry.get("svg")
                        if sld_pro_png_bytes:
                            break

        if layout_png_bytes is None:
            layout_results = state.get("layout_results") or {}
            if isinstance(layout_results, dict):
                for style_key in (layout_results.get("last_style"), "raw_v05"):
                    entry = layout_results.get(style_key) if style_key else None
                    if isinstance(entry, dict):
                        layout_png_bytes = layout_png_bytes or entry.get("png")
                        layout_svg_bytes = layout_svg_bytes or entry.get("svg")
                        if layout_png_bytes:
                            break
            layout_png_bytes = layout_png_bytes or state.get("layout_png_bytes")
            layout_svg_bytes = layout_svg_bytes or state.get("layout_svg_bytes")
    except Exception:
        pass

    # Priority 4: flat file fallbacks (written by old pipeline)
    outputs_dir = get_outputs_dir()
    if sld_pro_png_bytes is None:
        candidate = outputs_dir / "sld_latest.png"
        if candidate.exists():
            sld_pro_png_bytes = candidate.read_bytes()
    if sld_preview_svg_bytes is None:
        candidate = outputs_dir / "sld_latest.svg"
        if candidate.exists():
            sld_preview_svg_bytes = candidate.read_bytes()
    if layout_png_bytes is None:
        candidate = outputs_dir / "layout_latest.png"
        if candidate.exists():
            layout_png_bytes = candidate.read_bytes()
    if layout_svg_bytes is None:
        candidate = outputs_dir / "layout_latest.svg"
        if candidate.exists():
            layout_svg_bytes = candidate.read_bytes()

    # Priority 5: DB artifact_registry (enables recovery after run restore)
    if (sld_pro_png_bytes is None or layout_png_bytes is None) and run_id:
        try:
            from calb_sizing_tool.services.artifact_service import load_artifact_bytes_from_db
            _needed = []
            if sld_pro_png_bytes is None:
                _needed += ["sld_png", "sld_svg"]
            if layout_png_bytes is None:
                _needed += ["layout_png", "layout_svg"]
            if _needed:
                _db_art = load_artifact_bytes_from_db(run_id, _needed)
                sld_pro_png_bytes = sld_pro_png_bytes or _db_art.get("sld_png")
                sld_preview_svg_bytes = sld_preview_svg_bytes or _db_art.get("sld_svg")
                layout_png_bytes = layout_png_bytes or _db_art.get("layout_png")
                layout_svg_bytes = layout_svg_bytes or _db_art.get("layout_svg")
        except Exception:
            pass

    return ReportContext(
        project_name=project_name,
        scenario_id=scenario_id,
        poi_power_requirement_mw=poi_power_requirement_mw,
        poi_energy_requirement_mwh=poi_energy_requirement_mwh,
        poi_energy_guarantee_mwh=poi_energy_guarantee_mwh,
        poi_usable_energy_mwh_at_guarantee_year=poi_usable_guarantee,
        poi_usable_energy_mwh_at_year0=poi_usable_year0,
        poi_guarantee_year=poi_guarantee_year,
        project_life_years=project_life_years,
        cycles_per_year=cycles_per_year,
        grid_mv_voltage_kv_ac=ac_output.get("mv_voltage_kv")
        or ac_output.get("mv_kv")
        or ac_output.get("grid_kv"),
        pcs_lv_voltage_v_ll_rms_ac=ac_output.get("lv_voltage_v")
        or ac_output.get("lv_v")
        or ac_output.get("inverter_lv_v"),
        grid_power_factor=grid_power_factor,
        ac_block_template_id=ac_block_template_id,
        pcs_per_block=pcs_per_block,
        feeders_per_block=feeders_per_block,
        dc_blocks_total=dc_blocks_total,
        ac_blocks_total=ac_blocks_total,
        pcs_modules_total=pcs_modules_total,
        transformer_rating_kva=transformer_rating_kva,
        ac_block_size_mw=ac_output.get("block_size_mw"),
        dc_block_unit_mwh=_extract_dc_unit_mwh(stage2),
        dc_total_energy_mwh=_extract_dc_total_energy_mwh(stage2),
        efficiency_chain_oneway_frac=efficiency_chain_oneway,
        efficiency_components_frac=efficiency_components,
        avg_dc_blocks_per_ac_block=avg_dc_blocks_per_ac_block,
        dc_blocks_allocation=dc_blocks_allocation,
        qc_checks=qc_checks,
        dictionary_version_dc=Path(DC_DATA_PATH).name,
        dictionary_version_ac=Path(AC_DATA_PATH).name,
        configuration_code=(ac_output.get("configuration_code") if isinstance(ac_output, dict) else None),
        layout_variant=(ac_output.get("layout_variant") if isinstance(ac_output, dict) else None),
        run_id=run_id,
        ac_run_id=ac_run_id,
        project_code=project_code,
        case_code=case_code,
        case_name=case_name,
        report_generated_at=report_generated_at,
        sld_snapshot_id=sld_snapshot_id,
        sld_snapshot_hash=sld_snapshot_hash,
        sld_generated_at=sld_generated_at,
        sld_group_index=sld_group_index,
        sld_preview_svg_bytes=sld_preview_svg_bytes,
        sld_pro_png_bytes=sld_pro_png_bytes,
        layout_png_bytes=layout_png_bytes,
        layout_svg_bytes=layout_svg_bytes,
        stage1=stage1,
        stage2=stage2,
        stage3_df=stage3_df,
        stage3_meta=stage3_meta,
        ac_output=ac_output,
        project_inputs=project_inputs or {},
    )


def validate_report_context(ctx: ReportContext) -> list[str]:
    """
    Validate a ReportContext for internal consistency.
    Returns a list of warning strings (empty if valid).
    """
    warnings = []
    
    # Check AC sizing power consistency
    if ctx.ac_blocks_total > 0 and ctx.ac_block_size_mw is not None and ctx.ac_block_size_mw > 0:
        ac_total_mw = ctx.ac_blocks_total * ctx.ac_block_size_mw
        if abs(ac_total_mw - ctx.poi_power_requirement_mw) > 0.1:
            warnings.append(
                f"AC total power ({ac_total_mw:.2f} MW) does not match POI requirement ({ctx.poi_power_requirement_mw:.2f} MW). "
                f"Difference: {abs(ac_total_mw - ctx.poi_power_requirement_mw):.2f} MW."
            )
    
    # Check guarantee year is within project life
    if ctx.poi_guarantee_year > ctx.project_life_years:
        warnings.append(
            f"Guarantee year ({ctx.poi_guarantee_year}) exceeds project life ({ctx.project_life_years} years)."
        )
    
    # Check POI usable energy at guarantee year
    if (ctx.poi_usable_energy_mwh_at_guarantee_year is not None and 
        ctx.poi_energy_guarantee_mwh is not None and 
        ctx.poi_usable_energy_mwh_at_guarantee_year + 1e-6 < ctx.poi_energy_guarantee_mwh):
        warnings.append(
            f"POI usable energy at guarantee year ({ctx.poi_usable_energy_mwh_at_guarantee_year:.2f} MWh) "
            f"is below the guarantee target ({ctx.poi_energy_guarantee_mwh:.2f} MWh)."
        )
    
    # Check PCS module count
    if ctx.ac_blocks_total > 0 and ctx.pcs_per_block > 0:
        expected_pcs = ctx.ac_blocks_total * ctx.pcs_per_block
        if ctx.pcs_modules_total and ctx.pcs_modules_total != expected_pcs:
            warnings.append(
                f"PCS module count mismatch: expected {expected_pcs} (blocks x per_block), got {ctx.pcs_modules_total}."
            )
    
    return warnings



