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

"""Mixed AC Block station — a manual-adjustment layer over the uniform trunk.

The AC Sizing trunk sizes ONE uniform AC Block model applied to every AC Block.
A *mixed station* is an opt-in manual adjustment: the user edits the per-AC-Block
table so a **head** AC Block model covers most DC Blocks and one or more smaller
**tail** AC Block models cover the remainder — the AC-side counterpart of the DC
container + cabinet tail (DC Sizing "Hybrid Mode").

This module is deliberately OUTSIDE the frozen sizing canon
(``docs/SIZING_LOGIC_CANON_V1.md``). It only *composes* frozen helpers
(``minimum_dc_blocks_for_pcs_feeders``, ``build_dc_allocation_plan``); it never
changes a DC/AC sizing formula. Uniform is simply the single-entry case, so the
UI and report follow ONE code path whether or not the station is mixed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Sequence

from calb_sizing_tool.services.ac_sizing_service import (
    build_dc_allocation_plan,
    minimum_dc_blocks_for_pcs_feeders,
)

DEFAULT_DC_BLOCK_OUTPUT_CIRCUITS = 2

# One editable row per AC Block. Kept as a plain dict so it round-trips cleanly
# through ``st.data_editor`` and JSON persistence.
AcBlockRow = Dict[str, int]


def default_uniform_rows(
    dc_blocks_per_ac: Sequence[int],
    pcs_count: int,
    pcs_kw: int,
) -> List[AcBlockRow]:
    """One row per AC Block, pre-filled from the uniform trunk allocation.

    Editing any row turns the (otherwise uniform) station into a mixed one; an
    unedited table summarises back to a single head entry.
    """
    return [
        {"pcs_count": int(pcs_count), "pcs_kw": int(pcs_kw), "dc_blocks": int(dc_count)}
        for dc_count in dc_blocks_per_ac
    ]


def row_block_mw(row: AcBlockRow) -> float:
    """AC power of one AC Block row (MW)."""
    return int(row.get("pcs_count") or 0) * float(row.get("pcs_kw") or 0) / 1000.0


@dataclass(frozen=True)
class MixedStationValidation:
    ok: bool
    total_dc_assigned: int
    dc_blocks_total: int
    total_ac_mw: float
    total_pcs: int
    messages: tuple
    infeasible_rows: tuple  # 1-based indices failing the physical feeder check


def validate_ac_block_rows(
    rows: Sequence[AcBlockRow],
    dc_blocks_total: int,
    *,
    dc_block_output_circuits: int = DEFAULT_DC_BLOCK_OUTPUT_CIRCUITS,
) -> MixedStationValidation:
    """Validate a per-AC-Block table: positive specs, feeder capacity, and that
    the DC Blocks assigned across all rows sum to the DC total (no orphan/overrun).
    """
    messages: List[str] = []
    infeasible: List[int] = []
    total_dc = 0
    total_mw = 0.0
    total_pcs = 0

    if not rows:
        messages.append("At least one AC Block is required.")

    for index, row in enumerate(rows, start=1):
        pcs = int(row.get("pcs_count") or 0)
        kw = int(row.get("pcs_kw") or 0)
        dc = int(row.get("dc_blocks") or 0)
        if pcs <= 0 or kw <= 0 or dc <= 0:
            messages.append(
                f"AC Block {index}: PCS count, PCS rating and DC Blocks must all be greater than 0."
            )
            infeasible.append(index)
            continue
        total_dc += dc
        total_pcs += pcs
        total_mw += pcs * kw / 1000.0
        minimum = minimum_dc_blocks_for_pcs_feeders(
            pcs, dc_block_output_circuits=dc_block_output_circuits
        )
        if dc < minimum:
            messages.append(
                f"AC Block {index}: {pcs} PCS with {dc_block_output_circuits} protected "
                f"output circuit(s) per DC Block need at least {minimum} DC Blocks "
                f"(this row has {dc})."
            )
            infeasible.append(index)

    if total_dc != int(dc_blocks_total):
        messages.append(
            f"DC Blocks assigned = {total_dc}, but {int(dc_blocks_total)} are available. "
            f"Adjust the rows so they sum to exactly {int(dc_blocks_total)}."
        )

    return MixedStationValidation(
        ok=not messages,
        total_dc_assigned=total_dc,
        dc_blocks_total=int(dc_blocks_total),
        total_ac_mw=round(total_mw, 3),
        total_pcs=total_pcs,
        messages=tuple(messages),
        infeasible_rows=tuple(dict.fromkeys(infeasible)),  # de-dup, keep order
    )


def summarize_ac_block_rows(rows: Sequence[AcBlockRow]) -> List[Dict]:
    """Group rows by AC Block MODEL into head/tail schedule entries.

    An AC Block model is (pcs_count, pcs_kw). The uniform trunk already fills DC
    Blocks unevenly across identical AC Blocks (e.g. 20×8 + 6×7 DC), so DC count
    is carried as a per-model range (``dc_blocks_min``/``max``; ``dc_blocks_each``
    is the exact value only when they are equal) rather than splitting one model
    into several rows. The largest-power model is the Head; the rest are Tails.
    A single model (however its DC Blocks are distributed) is not a mixed station.
    """
    groups: Dict[tuple, Dict] = {}
    order: List[tuple] = []
    for row in rows:
        pcs = int(row["pcs_count"])
        kw = int(row["pcs_kw"])
        dc = int(row["dc_blocks"])
        key = (pcs, kw)
        if key not in groups:
            groups[key] = {"count": 0, "dc_total": 0, "dc_min": dc, "dc_max": dc}
            order.append(key)
        group = groups[key]
        group["count"] += 1
        group["dc_total"] += dc
        group["dc_min"] = min(group["dc_min"], dc)
        group["dc_max"] = max(group["dc_max"], dc)

    entries: List[Dict] = []
    for pcs, kw in order:
        group = groups[(pcs, kw)]
        entries.append(
            {
                "count": group["count"],
                "pcs_count": pcs,
                "pcs_kw": kw,
                "block_mw": round(pcs * kw / 1000.0, 3),
                "dc_blocks_total": group["dc_total"],
                "dc_blocks_min": group["dc_min"],
                "dc_blocks_max": group["dc_max"],
                "dc_blocks_each": (
                    group["dc_max"] if group["dc_min"] == group["dc_max"] else None
                ),
            }
        )

    if entries:
        head = max(entries, key=lambda entry: (entry["block_mw"], entry["count"]))
        for entry in entries:
            entry["role"] = "Head" if entry is head else "Tail"
    return entries


def is_mixed_station(rows: Sequence[AcBlockRow]) -> bool:
    """True when the table holds more than one distinct AC Block model.

    Uneven DC-Block filling of a single model is *not* a mixed station; only two
    or more distinct (pcs_count, pcs_kw) models are.
    """
    return len(summarize_ac_block_rows(rows)) > 1


def build_mixed_dc_allocation_plan(
    rows: Sequence[AcBlockRow],
    *,
    dc_block_output_circuits: int = DEFAULT_DC_BLOCK_OUTPUT_CIRCUITS,
) -> List[Dict]:
    """Per-AC-Block DC allocation for a mixed table.

    Each row is a single AC Block, so its DC-to-PCS feeder plan comes from the
    frozen ``build_dc_allocation_plan`` for that one block; the per-row plans are
    concatenated and re-indexed 1..N across the whole station.
    """
    plan: List[Dict] = []
    for index, row in enumerate(rows, start=1):
        pcs = int(row["pcs_count"])
        dc = int(row["dc_blocks"])
        single = build_dc_allocation_plan(
            dc, 1, pcs, dc_block_output_circuits=dc_block_output_circuits
        )
        entry = dict(single[0])
        entry["ac_block_index"] = index
        plan.append(entry)
    return plan


def _rows_from_ac_output(ac_output: Dict) -> List[AcBlockRow]:
    """Recover the per-AC-Block table from a persisted AC output payload.

    Prefers the authoritative ``ac_block_rows`` written by the AC Sizing page;
    falls back to reconstructing rows from the per-block mirror lists so older
    runs (persisted before the mixed table existed) still resolve.
    """
    rows = ac_output.get("ac_block_rows")
    if isinstance(rows, list) and rows:
        return [
            {
                "pcs_count": int(r.get("pcs_count") or 0),
                "pcs_kw": int(r.get("pcs_kw") or 0),
                "dc_blocks": int(r.get("dc_blocks") or 0),
            }
            for r in rows
        ]
    pcs_counts = ac_output.get("pcs_count_by_block") or []
    dc_per_ac = ac_output.get("dc_blocks_per_ac") or ac_output.get("dc_blocks_total_by_block") or []
    pcs_kw = int(ac_output.get("pcs_kw") or ac_output.get("pcs_power_kw") or 0)
    reconstructed: List[AcBlockRow] = []
    for index in range(len(pcs_counts)):
        dc = int(dc_per_ac[index]) if index < len(dc_per_ac) else 0
        reconstructed.append(
            {"pcs_count": int(pcs_counts[index] or 0), "pcs_kw": pcs_kw, "dc_blocks": dc}
        )
    return reconstructed


def head_fleet_ac_output_for_sld(ac_output: Dict) -> Dict | None:
    """Project a (possibly mixed) AC output onto its HEAD AC-Block fleet.

    The SLD authoritative contract is uniform-only by design (SLD V1 requires
    ``pcs_count_by_block`` uniform), so a mixed station cannot be rendered
    directly. The head-model AC Blocks, however, *already* form a real uniform
    sub-station (same PCS count/rating; DC Blocks may still fill unevenly, which
    V1 permits). This returns a uniform, SLD-V1-valid payload for exactly that
    head fleet — a genuine subset of the site, nothing fabricated — so the SLD
    can render the representative head AC Block while the report's §6.1 schedule
    carries the full head + tail composition.

    Returns ``None`` when there is no resolvable head fleet (no rows).
    """
    if not isinstance(ac_output, dict):
        return None
    rows = _rows_from_ac_output(ac_output)
    breakdown = summarize_ac_block_rows(rows)
    if not breakdown:
        return None
    head = next((entry for entry in breakdown if entry.get("role") == "Head"), breakdown[0])
    head_key = (int(head["pcs_count"]), int(head["pcs_kw"]))
    head_rows = [
        row for row in rows if (int(row["pcs_count"]), int(row["pcs_kw"])) == head_key
    ]
    if not head_rows:
        return None

    circuits = int(ac_output.get("dc_block_output_circuits") or DEFAULT_DC_BLOCK_OUTPUT_CIRCUITS)
    plan = build_mixed_dc_allocation_plan(head_rows, dc_block_output_circuits=circuits)
    dc_total_by_block = [int(entry["dc_blocks_total"]) for entry in plan]

    pcs_per_block = int(head["pcs_count"])
    pcs_kw = int(head["pcs_kw"])
    num_blocks = len(head_rows)

    representative = dict(ac_output)
    representative.update(
        {
            "num_blocks": num_blocks,
            "pcs_per_block": pcs_per_block,
            "pcs_count_by_block": [pcs_per_block for _ in head_rows],
            "pcs_kw": pcs_kw,
            "pcs_power_kw": pcs_kw,
            "pcs_rating_kw_each": pcs_kw,
            "block_size_mw": pcs_per_block * pcs_kw / 1000.0,
            "dc_blocks_per_ac": [int(row["dc_blocks"]) for row in head_rows],
            "dc_blocks_total_by_block": list(dc_total_by_block),
            "dc_blocks_per_feeder_by_block": [
                list(entry.get("feeder_allocations", [])) for entry in plan
            ],
            "dc_block_connections_by_block": [
                list(entry.get("dc_block_connections", [])) for entry in plan
            ],
            "dc_allocation_plan": plan,
            "dc_blocks_total": sum(dc_total_by_block),
            "transformer_count": num_blocks,
            "pcs_count_total": pcs_per_block * num_blocks,
            # This projection is a uniform station in its own right; clear the
            # mixed markers so downstream reads it as such, but keep a trail.
            "ac_block_mixed": False,
            # Derive "this SLD is only the head fleet" from the ACTUAL rows, not
            # solely from the caller's ``ac_block_mixed`` marker. That marker is
            # written by the AC Sizing page, but ``_rows_from_ac_output`` also
            # reconstructs rows for runs persisted BEFORE the mixed table existed —
            # those carry no marker, so trusting it alone would let a genuinely
            # mixed station's head-fleet-only drawing pass the formal-readiness
            # gate as a full-site SLD (the tail AC Blocks are not on it).
            "sld_representative_of_mixed": bool(
                ac_output.get("ac_block_mixed") or is_mixed_station(rows)
            ),
            "sld_head_fleet_block_count": num_blocks,
        }
    )
    return representative
