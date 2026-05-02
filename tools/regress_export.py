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

import argparse
import json
import math
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from calb_sizing_tool.common.allocation import evenly_distribute
from calb_sizing_tool.config import AC_DATA_PATH, DC_DATA_PATH
from calb_sizing_tool.reporting import export_docx
from calb_sizing_tool.ui import dc_view


ROUND_DECIMALS = 6


def load_fixture(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _round_value(value):
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, int):
        return value
    try:
        return round(float(value), ROUND_DECIMALS)
    except Exception:
        return value


def _normalize_payload(payload):
    if isinstance(payload, dict):
        return {k: _normalize_payload(v) for k, v in payload.items()}
    if isinstance(payload, list):
        return [_normalize_payload(v) for v in payload]
    return _round_value(payload)


def _extract_block_identity(stage2_raw):
    block_code = None
    block_name = None
    block_table = stage2_raw.get("block_config_table") if isinstance(stage2_raw, dict) else None
    if block_table is not None and not block_table.empty:
        first_row = block_table.iloc[0]
        block_code = first_row.get("Block Code")
        block_name = first_row.get("Block Name")
    return block_code, block_name


def run_dc_sizing(fixture: dict):
    defaults, df_blocks, df_soh_profile, df_soh_curve, df_rte_profile, df_rte_curve = dc_view.load_data(DC_DATA_PATH)

    stage1_inputs = {}
    for key in (
        "project_name",
        "poi_power_req_mw",
        "poi_energy_req_mwh",
        "project_life_years",
        "cycles_per_year",
        "poi_guarantee_year",
        "eff_dc_cables",
        "eff_pcs",
        "eff_mvt",
        "eff_ac_cables_sw_rmu",
        "eff_hvt_others",
        "sc_time_months",
        "dod_pct",
        "dc_round_trip_efficiency_pct",
    ):
        if key in fixture and fixture[key] is not None:
            stage1_inputs[key] = fixture[key]

    stage1 = dc_view.run_stage1(stage1_inputs, defaults)
    scenario_id = fixture.get("scenario_id", "container_only")

    s2, s3_df, s3_meta, iter_count, poi_g, converged = dc_view.size_with_guarantee(
        stage1,
        scenario_id,
        df_blocks,
        df_soh_profile,
        df_soh_curve,
        df_rte_profile,
        df_rte_curve,
        k_max=dc_view.K_MAX_FIXED,
    )

    return {
        "stage1": stage1,
        "stage2": s2,
        "stage3_df": s3_df,
        "stage3_meta": s3_meta,
        "iter_count": iter_count,
        "poi_g": poi_g,
        "converged": converged,
        "scenario_id": scenario_id,
    }


def run_ac_sizing(fixture: dict, stage1: dict, stage2: dict) -> dict:
    ac_inputs = fixture.get("ac_inputs", {}) or {}
    target_mw = float(stage1.get("poi_power_req_mw", 0.0))
    target_mwh = float(stage1.get("poi_energy_req_mwh", 0.0))

    grid_kv = float(ac_inputs.get("grid_kv", fixture.get("poi_nominal_voltage_kv", 33.0)))
    pcs_lv = float(ac_inputs.get("pcs_lv_v", 800.0))
    block_size = float(ac_inputs.get("block_size_mw", 5.0))

    num_blocks = math.ceil(target_mw / block_size) if block_size > 0 else 0
    total_ac_mw = num_blocks * block_size
    overhead = total_ac_mw - target_mw

    container_count = int(stage2.get("container_count", 0))
    dc_per_ac = 0
    if num_blocks > 0:
        dc_per_ac = max(1, container_count // num_blocks)

    pcs_per_block = 2
    pcs_power_kw = block_size * 1000 / pcs_per_block if pcs_per_block else 0.0
    transformer_kva = block_size * 1000 / 0.9
    total_pcs = num_blocks * pcs_per_block
    pcs_count_by_block = evenly_distribute(total_pcs, num_blocks)
    dc_blocks_total = int(stage2.get("container_count", 0)) + int(stage2.get("cabinet_count", 0))
    dc_blocks_total_by_block = evenly_distribute(dc_blocks_total, num_blocks)
    dc_blocks_per_feeder_by_block = []
    for idx, block_pcs in enumerate(pcs_count_by_block):
        block_dc_total = dc_blocks_total_by_block[idx] if idx < len(dc_blocks_total_by_block) else 0
        dc_blocks_per_feeder_by_block.append(evenly_distribute(block_dc_total, block_pcs))

    return {
        "project_name": stage1.get("project_name", "CALB ESS Project"),
        "poi_power_mw": target_mw,
        "poi_energy_mwh": target_mwh,
        "grid_kv": grid_kv,
        "inverter_lv_v": pcs_lv,
        "block_size_mw": block_size,
        "num_blocks": num_blocks,
        "total_ac_mw": total_ac_mw,
        "overhead_mw": overhead,
        "pcs_power_kw": pcs_power_kw,
        "pcs_per_block": pcs_per_block,
        "pcs_count_by_block": pcs_count_by_block,
        "total_pcs": total_pcs,
        "transformer_kva": transformer_kva,
        "transformer_count": num_blocks,
        "dc_blocks_per_ac": dc_per_ac,
        "dc_blocks_total_by_block": dc_blocks_total_by_block,
        "dc_blocks_per_feeder_by_block": dc_blocks_per_feeder_by_block,
        "mv_level_kv": grid_kv,
    }


def build_v1_report_bytes(dc_output: dict, ac_output: dict):
    ctx = {
        "project_name": ac_output.get("project_name"),
        "inputs": {
            "Selected DC Scenario": dc_output.get("selected_scenario"),
            "Grid Voltage (kV)": f"{ac_output.get('grid_kv', 0.0):.1f}",
            "Standard AC Block Size (MW)": f"{ac_output.get('block_size_mw', 0.0):.2f}",
        },
    }
    return export_docx.create_combined_report(dc_output, ac_output, ctx)


def build_summary(fixture: dict) -> dict:
    dc_results = run_dc_sizing(fixture)
    stage1 = dc_results["stage1"]
    stage2 = dc_results["stage2"]
    stage3_df = dc_results["stage3_df"]
    scenario_id = dc_results["scenario_id"]

    ac_output = run_ac_sizing(fixture, stage1, stage2)

    block_code, block_name = _extract_block_identity(stage2)
    results_dict = {
        scenario_id: (
            stage2,
            stage3_df,
            dc_results["stage3_meta"],
            dc_results["iter_count"],
            dc_results["poi_g"],
            dc_results["converged"],
        )
    }

    dc_output = {
        "stage1": stage1,
        "selected_scenario": scenario_id,
        "dc_block_total_qty": int(stage2.get("container_count", 0)) + int(stage2.get("cabinet_count", 0)),
        "container_count": int(stage2.get("container_count", 0)),
        "block_code": block_code,
        "block_name": block_name,
        "results_dict": results_dict,
        "report_order": [(scenario_id, scenario_id.replace("_", " ").title())],
    }

    _ = build_v1_report_bytes(dc_output, ac_output)

    stage3_year0 = stage3_df[stage3_df["Year_Index"] == 0]["POI_Usable_Energy_MWh"].iloc[0]

    summary = {
        "fixture_id": fixture.get("fixture_id"),
        "inputs": {
            "project_name": stage1.get("project_name"),
            "poi_power_requirement_mw": stage1.get("poi_power_req_mw"),
            "poi_energy_requirement_mwh": stage1.get("poi_energy_req_mwh"),
            "poi_nominal_voltage_kv": fixture.get("poi_nominal_voltage_kv", ac_output.get("grid_kv")),
            "poi_frequency_hz": fixture.get("poi_frequency_hz"),
            "scenario_id": scenario_id,
            "dictionary_version_dc": Path(DC_DATA_PATH).name,
            "dictionary_version_ac": Path(AC_DATA_PATH).name,
        },
        "outputs": {
            "dc_blocks_total": int(stage2.get("container_count", 0)) + int(stage2.get("cabinet_count", 0)),
            "dc_blocks_container": int(stage2.get("container_count", 0)),
            "dc_blocks_cabinet": int(stage2.get("cabinet_count", 0)),
            "ac_blocks_total": int(ac_output.get("num_blocks", 0)),
            "pcs_modules_total": int(ac_output.get("total_pcs", 0)),
            "transformer_rating_kva": ac_output.get("transformer_kva"),
            "stage3_year0_poi_usable_energy_mwh": stage3_year0,
        },
    }

    return _normalize_payload(summary)


def build_summary_from_fixture_path(path: Path) -> dict:
    fixture = load_fixture(path)
    return build_summary(fixture)


def main():
    parser = argparse.ArgumentParser(description="Generate V1 report and summary from fixtures.")
    parser.add_argument("--fixture", type=Path, required=True, help="Path to fixture input JSON.")
    parser.add_argument("--summary-out", type=Path, required=True, help="Path to output summary JSON.")
    parser.add_argument("--docx-out", type=Path, default=None, help="Path to write V1 DOCX report.")
    args = parser.parse_args()

    summary = build_summary_from_fixture_path(args.fixture)
    args.summary_out.parent.mkdir(parents=True, exist_ok=True)
    args.summary_out.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")

    docx_out = args.docx_out
    if docx_out is None:
        docx_out = args.summary_out.with_name("v1_report.docx")

    fixture = load_fixture(args.fixture)
    dc_results = run_dc_sizing(fixture)
    stage1 = dc_results["stage1"]
    stage2 = dc_results["stage2"]
    stage3_df = dc_results["stage3_df"]
    scenario_id = dc_results["scenario_id"]
    ac_output = run_ac_sizing(fixture, stage1, stage2)
    block_code, block_name = _extract_block_identity(stage2)

    dc_output = {
        "stage1": stage1,
        "selected_scenario": scenario_id,
        "dc_block_total_qty": int(stage2.get("container_count", 0)) + int(stage2.get("cabinet_count", 0)),
        "container_count": int(stage2.get("container_count", 0)),
        "block_code": block_code,
        "block_name": block_name,
        "results_dict": {
            scenario_id: (
                stage2,
                stage3_df,
                dc_results["stage3_meta"],
                dc_results["iter_count"],
                dc_results["poi_g"],
                dc_results["converged"],
            )
        },
        "report_order": [(scenario_id, scenario_id.replace("_", " ").title())],
    }
    report_bytes = build_v1_report_bytes(dc_output, ac_output)
    docx_out.parent.mkdir(parents=True, exist_ok=True)
    docx_out.write_bytes(report_bytes)


if __name__ == "__main__":
    main()
