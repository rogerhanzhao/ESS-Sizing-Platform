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
