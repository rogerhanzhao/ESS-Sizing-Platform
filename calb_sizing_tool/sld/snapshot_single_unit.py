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
import json
from typing import Dict, List, Optional

from calb_sizing_tool.common.allocation import allocate_dc_blocks, evenly_distribute
from calb_sizing_tool.sld.ac_block_group import build_ac_block_group_spec


def _snapshot_hash(snapshot: dict) -> str:
    payload = json.dumps(snapshot, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


def _safe_int(value, default=0):
    try:
        return int(value)
    except Exception:
        return default


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return default


def _build_feeders(pcs_rating_kva_list: List[float]) -> List[Dict]:
    feeders = []
    for idx, rating in enumerate(pcs_rating_kva_list, start=1):
        feeders.append(
            {
                "feeder_id": f"FDR-{idx:02d}",
                "pcs_id": f"PCS-{idx:02d}",
                "pcs_rating_kva": rating,
            }
        )
    return feeders


def _build_dc_blocks_by_feeder(
    dc_blocks_per_feeder: List[int], dc_block_unit_mwh: Optional[float]
) -> List[Dict]:
    allocations = []
    for idx, count in enumerate(dc_blocks_per_feeder, start=1):
        entry = {
            "feeder_id": f"FDR-{idx:02d}",
            "dc_block_count": int(count),
            "dc_block_energy_mwh": None,
        }
        if dc_block_unit_mwh:
            entry["dc_block_energy_mwh"] = int(count) * dc_block_unit_mwh
        allocations.append(entry)
    return allocations


def _compute_site_dc_blocks(stage13_output: dict, dc_summary: dict) -> int:
    total_dc_blocks = _safe_int(stage13_output.get("dc_block_total_qty") or 0)
    if total_dc_blocks <= 0:
        total_dc_blocks = _safe_int(stage13_output.get("container_count") or 0) + _safe_int(
            stage13_output.get("cabinet_count") or 0
        )
    if total_dc_blocks <= 0 and isinstance(dc_summary, dict):
        dc_block = dc_summary.get("dc_block")
        if dc_block is not None:
            total_dc_blocks = _safe_int(getattr(dc_block, "count", 0))
    return total_dc_blocks


def _compute_site_ac_blocks(ac_output: dict) -> int:
    return _safe_int(ac_output.get("num_blocks") or ac_output.get("ac_blocks_total") or 0)


def build_single_unit_snapshot(
    stage13_output: dict,
    ac_output: dict,
    dc_summary: dict,
    sld_inputs: dict,
    scenario_id: str,
) -> dict:
    """LEGACY compatibility only.

    The authoritative SLD build chain is now:
    canonical input -> SldTopology -> compatibility adapters.
    This raw snapshot format is retained only for older tools that still consume it.
    """
    stage13_output = stage13_output or {}
    ac_output = ac_output or {}
    dc_summary = dc_summary or {}
    sld_inputs = sld_inputs or {}

    project_name = (
        stage13_output.get("project_name")
        or ac_output.get("project_name")
        or "CALB ESS Project"
    )
    project_hz = _safe_float(stage13_output.get("poi_frequency_hz"), 60.0)

    group_index = _safe_int(sld_inputs.get("group_index"), 1)
    group_spec = build_ac_block_group_spec(
        stage13_output, ac_output, dc_summary, sld_inputs, group_index
    )

    site_ac_block_total = _safe_int(
        sld_inputs.get("site_ac_block_total") or _compute_site_ac_blocks(ac_output)
    )
    site_dc_block_total = _safe_int(
        sld_inputs.get("site_dc_block_total") or _compute_site_dc_blocks(stage13_output, dc_summary)
    )
    ratio_default = 0
    if site_ac_block_total > 0 and site_dc_block_total > 0:
        ratio_default = max(1, int(round(site_dc_block_total / site_ac_block_total)))

    feeders = sld_inputs.get("feeders")
    if not isinstance(feeders, list) or len(feeders) != group_spec.pcs_count:
        feeders = _build_feeders(group_spec.pcs_rating_kva_list)
    else:
        normalized_feed = []
        for idx, entry in enumerate(feeders, start=1):
            if not isinstance(entry, dict):
                continue
            pcs_rating = entry.get("pcs_rating_kva")
            if pcs_rating is None and idx - 1 < len(group_spec.pcs_rating_kva_list):
                pcs_rating = group_spec.pcs_rating_kva_list[idx - 1]
            normalized_feed.append(
                {
                    "feeder_id": entry.get("feeder_id") or f"FDR-{idx:02d}",
                    "pcs_id": entry.get("pcs_id") or f"PCS-{idx:02d}",
                    "pcs_rating_kva": pcs_rating,
                }
            )
        feeders = normalized_feed if len(normalized_feed) == group_spec.pcs_count else _build_feeders(
            group_spec.pcs_rating_kva_list
        )

    dc_blocks_by_feeder = sld_inputs.get("dc_blocks_by_feeder")
    dc_blocks_for_one_ac_block_group = _safe_int(
        sld_inputs.get("dc_blocks_for_one_ac_block_group"), 0
    )

    if isinstance(dc_blocks_by_feeder, list) and len(dc_blocks_by_feeder) == group_spec.pcs_count:
        normalized = []
        total_count = 0
        for idx, entry in enumerate(dc_blocks_by_feeder, start=1):
            if not isinstance(entry, dict):
                continue
            feeder_id = entry.get("feeder_id") or f"FDR-{idx:02d}"
            count = _safe_int(entry.get("dc_block_count"), 0)
            total_count += count
            energy = entry.get("dc_block_energy_mwh")
            if energy is None and group_spec.dc_block_energy_mwh:
                energy = count * group_spec.dc_block_energy_mwh
            normalized.append(
                {
                    "feeder_id": feeder_id,
                    "dc_block_count": count,
                    "dc_block_energy_mwh": energy,
                }
            )
        dc_blocks_by_feeder = normalized
        if total_count > 0:
            dc_blocks_for_one_ac_block_group = total_count
    else:
        if dc_blocks_for_one_ac_block_group <= 0:
            if sld_inputs.get("use_site_ratio"):
                dc_blocks_for_one_ac_block_group = ratio_default or group_spec.dc_blocks_total_in_group
            else:
                dc_blocks_for_one_ac_block_group = group_spec.dc_blocks_total_in_group
        if dc_blocks_for_one_ac_block_group <= 0:
            dc_blocks_for_one_ac_block_group = group_spec.pcs_count
        dc_blocks_per_feeder = list(group_spec.dc_blocks_per_feeder)
        if sum(dc_blocks_per_feeder) != dc_blocks_for_one_ac_block_group:
            dc_blocks_for_one_ac_block_group = sum(dc_blocks_per_feeder)
        dc_blocks_by_feeder = _build_dc_blocks_by_feeder(
            dc_blocks_per_feeder, group_spec.dc_block_energy_mwh
        )

    labels = sld_inputs.get("mv_labels") if isinstance(sld_inputs.get("mv_labels"), dict) else {}
    diagram_scope = sld_inputs.get("diagram_scope") or "one_ac_block_group"

    snapshot = {
        "schema_version": "sld_single_unit_v0_5",
        "snapshot_id": f"SLD-Raw-{project_name}-{scenario_id}-{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}",
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "diagram_scope": diagram_scope,
        "group_index": group_spec.group_index,
        "site_ac_block_total": site_ac_block_total,
        "site_dc_block_total": site_dc_block_total,
        "dc_blocks_for_one_ac_block_group": dc_blocks_for_one_ac_block_group,
        "project": {"name": project_name, "scenario_id": scenario_id, "hz": project_hz},
        "mv": {
            "kv": group_spec.mv_voltage_kv,
            "node_id": "MV_NODE_01",
            "labels": {
                "to_switchgear": labels.get("to_switchgear") or "To Switchgear",
                "to_other_rmu": labels.get("to_other_rmu") or "To Other RMU",
            },
        },
        "transformer": {
            "rated_mva": group_spec.transformer_rating_mva,
            "rated_kva": group_spec.transformer_rating_mva * 1000.0,
            "hv_kv": group_spec.mv_voltage_kv,
            "lv_v": group_spec.lv_voltage_v_ll,
            "vector_group": sld_inputs.get("transformer", {}).get("vector_group"),
            "uk_percent": sld_inputs.get("transformer", {}).get("uk_percent"),
            "tap_range": sld_inputs.get("transformer", {}).get("tap_range"),
            "cooling": sld_inputs.get("transformer", {}).get("cooling"),
        },
        "ac_block": {
            "group_index": group_spec.group_index,
            "pcs_count": group_spec.pcs_count,
            "pcs_rating_each_kva": group_spec.pcs_rating_kva_list[0]
            if group_spec.pcs_rating_kva_list
            else None,
            "pcs_rating_kva_list": group_spec.pcs_rating_kva_list,
            "pcs_lv_voltage_v_ll": group_spec.lv_voltage_v_ll,
        },
        "feeders": feeders,
        "dc_block_energy_mwh": group_spec.dc_block_energy_mwh,
        "dc_blocks_by_feeder": dc_blocks_by_feeder,
        "electrical_inputs": {
            "rmu": sld_inputs.get("rmu", {}) or {},
            "transformer": sld_inputs.get("transformer", {}) or {},
            "lv_busbar": sld_inputs.get("lv_busbar", {}) or {},
            "cables": sld_inputs.get("cables", {}) or {},
            "dc_fuse": sld_inputs.get("dc_fuse", {}) or {},
        },
        "svg_width": sld_inputs.get("svg_width"),
        "svg_height": sld_inputs.get("svg_height"),
    }

    snapshot["snapshot_hash"] = _snapshot_hash(snapshot)
    return snapshot


def validate_single_unit_snapshot(snapshot: dict) -> None:
    if not isinstance(snapshot, dict):
        raise ValueError("Snapshot must be a dict.")

    if snapshot.get("schema_version") != "sld_single_unit_v0_5":
        raise ValueError("Unsupported snapshot schema_version.")

    project = snapshot.get("project")
    if not isinstance(project, dict):
        raise ValueError("Snapshot 'project' must be a dict.")
    for key in ("name", "hz"):
        if key not in project:
            raise ValueError(f"Missing '{key}' in project.")

    mv = snapshot.get("mv")
    if not isinstance(mv, dict):
        raise ValueError("Snapshot 'mv' must be a dict.")
    for key in ("kv", "node_id", "labels"):
        if key not in mv:
            raise ValueError(f"Missing '{key}' in mv.")

    transformer = snapshot.get("transformer")
    if not isinstance(transformer, dict):
        raise ValueError("Snapshot 'transformer' must be a dict.")
    for key in ("rated_mva", "hv_kv", "lv_v"):
        if key not in transformer:
            raise ValueError(f"Missing '{key}' in transformer.")

    ac_block = snapshot.get("ac_block")
    if not isinstance(ac_block, dict):
        raise ValueError("Snapshot 'ac_block' must be a dict.")
    for key in ("pcs_count", "pcs_rating_each_kva", "pcs_lv_voltage_v_ll"):
        if key not in ac_block:
            raise ValueError(f"Missing '{key}' in ac_block.")

    feeders = snapshot.get("feeders")
    pcs_count = _safe_int(ac_block.get("pcs_count"), 0)
    if not isinstance(feeders, list) or not feeders:
        raise ValueError("Snapshot 'feeders' must be a non-empty list.")
    if pcs_count > 0 and len(feeders) != pcs_count:
        raise ValueError("Snapshot 'feeders' count must match ac_block.pcs_count.")
    for feeder in feeders:
        if not isinstance(feeder, dict):
            raise ValueError("Each feeder entry must be a dict.")
        for key in ("feeder_id", "pcs_id"):
            if key not in feeder:
                raise ValueError(f"Missing '{key}' in feeders[].")

    dc_blocks_by_feeder = snapshot.get("dc_blocks_by_feeder")
    if not isinstance(dc_blocks_by_feeder, list) or len(dc_blocks_by_feeder) != len(feeders):
        raise ValueError("Snapshot 'dc_blocks_by_feeder' must match feeder count.")
