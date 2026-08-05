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

"""AC alternatives under a fixed DC result (owner ruling B, 2026-08-04).

    "同一个确定了的 DC 方案，AC 是可以稍微有多一个方案的，但是可以匹配 DC block，
     SLD 以后的所有生成都可以变，最终报告可以重新生成一个版本"

WHY THIS IS NOT A SECOND CASE
-----------------------------
A Case holds DC-side assumptions ONLY — ``SizingCaseInput`` is POI power/energy,
life, DoD, RTE, the efficiency chain and the scenario. It contains no AC field at
all. So "which AC configuration did we pick on top of this DC result" has nowhere
to live in a Case, and an AC run does not duplicate one:

    Project → Case (方案 x scenario) → DC Run → AC Run → SLD / layout / report

WHY IT DOES NOT MULTIPLY WITHOUT BOUND
--------------------------------------
The owner's constraint was "不能过度的细分". A run per click would do exactly
that, so the AC configuration is hashed and the hash is the identity: re-running
with an unchanged configuration REUSES its run instead of adding one. The number
of AC runs equals the number of distinct alternatives actually tried, not the
number of times the button was pressed. ``test_ac_run_service.py`` holds that.

SCOPE OF THIS STEP
------------------
Records only. SLD, layout and report artifacts still attach to the DC run; moving
them to the AC run re-addresses the whole downstream chain and is step 2 in
docs/AC_RUN_PROMOTION_DESIGN.md. Writing the record first means the history
exists before anything depends on it, and this step can be reverted on its own.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping

from calb_sizing_tool.infra.db.session import session_scope
from calb_sizing_tool.repositories.run_repository import RunRepository
from calb_sizing_tool.schemas.run_snapshot import (
    RunInputSnapshotSchema,
    RunOutputSnapshotSchema,
)

AC_RUN_TYPE = "ac_sizing"
AC_INPUT_SNAPSHOT_KIND = "ac_case_input"
AC_OUTPUT_SNAPSHOT_KIND = "ac_sizing_output"

# The AC decisions that make one alternative different from another. Anything not
# in here is a presentation or bookkeeping detail and must NOT mint a new run —
# that is the difference between "a second alternative" and "over-splitting".
_IDENTITY_FIELDS = (
    "num_blocks",
    "pcs_per_block",
    "pcs_kw",
    "block_size_mw",
    "transformer_mva",
    "transformer_topology",
    "lv_winding_count",
    "dc_blocks_total",
    "dc_allocation_plan",
    "ac_block_model_name",
    "configuration_code",
    "layout_variant",
    "ac_block_arrangement",
    "grid_kv",
    "lv_voltage_v",
    "transformer_vector_group",
    "transformer_cooling",
)


@dataclass(frozen=True)
class AcRunResult:
    run_id: str
    parent_run_id: str
    content_hash: str
    reused: bool
    alternatives: int


def ac_configuration_hash(ac_output: Mapping[str, Any] | None,
                          ac_inputs: Mapping[str, Any] | None = None) -> str:
    """Identity of an AC alternative.

    Only the fields that make one alternative genuinely different are hashed, so
    a re-run that changes nothing meaningful resolves to the same run. Values are
    normalised through JSON so an int and a float of the same value agree.
    """
    source: dict[str, Any] = {}
    for field in _IDENTITY_FIELDS:
        for candidate in (ac_output or {}, ac_inputs or {}):
            if field in candidate:
                source[field] = candidate[field]
                break
    raw = json.dumps(source, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _payload_hash(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def persist_ac_run(
    *,
    dc_run_id: str,
    ac_inputs: Mapping[str, Any] | None,
    ac_output: Mapping[str, Any] | None,
    db_url: str | None = None,
    actor: str | None = None,
    version_tag: str | None = None,
    source_ref: str = "ac_view",
) -> AcRunResult | None:
    """Record this AC alternative under its DC run, reusing an identical one.

    Returns ``None`` when there is nothing to record (no DC run, or an empty AC
    result) — a caller must not have to guard for that itself.
    """
    parent_id = str(dc_run_id or "").strip()
    if not parent_id or not ac_output:
        return None

    content_hash = ac_configuration_hash(ac_output, ac_inputs)

    with session_scope(db_url) as session:
        repo = RunRepository(session)
        parent = repo.get_run(parent_id)
        if parent is None:
            return None

        existing = repo.find_child_run_by_hash(parent_id, AC_RUN_TYPE, content_hash)
        if existing is not None:
            # Same configuration as before: this is the SAME alternative being
            # recomputed, not a new one. Keep one row and move on.
            existing.finished_at = _now()
            session.flush()
            return AcRunResult(
                run_id=existing.sizing_run_id,
                parent_run_id=parent_id,
                content_hash=content_hash,
                reused=True,
                alternatives=len(repo.list_child_runs(parent_id, run_type=AC_RUN_TYPE)),
            )

        run = repo.create_run(
            project_id=parent.project_id,
            sizing_case_id=parent.sizing_case_id,
            parent_run_id=parent_id,
            run_type=AC_RUN_TYPE,
            status="succeeded",
            input_summary_json={
                "pcs_per_block": ac_output.get("pcs_per_block"),
                "num_blocks": ac_output.get("num_blocks"),
                "dc_blocks_total": ac_output.get("dc_blocks_total"),
                "configuration_code": ac_output.get("configuration_code"),
            },
            output_summary_json={
                "total_ac_mw": ac_output.get("total_ac_mw"),
                "block_size_mw": ac_output.get("block_size_mw"),
                "transformer_mva": ac_output.get("transformer_mva"),
            },
            version_tag=version_tag,
            source_ref=source_ref,
        )
        session.flush()

        # The input snapshot carries the IDENTITY hash, because that is what
        # find_child_run_by_hash matches on.
        repo.add_input_snapshot(
            run.sizing_run_id,
            RunInputSnapshotSchema(
                snapshot_kind=AC_INPUT_SNAPSHOT_KIND,
                payload=dict(ac_inputs or {}),
                content_hash=content_hash,
            ),
            version_tag=version_tag,
            source_ref=source_ref,
        )
        output_payload = dict(ac_output)
        repo.add_output_snapshot(
            run.sizing_run_id,
            RunOutputSnapshotSchema(
                snapshot_kind=AC_OUTPUT_SNAPSHOT_KIND,
                payload=output_payload,
                content_hash=_payload_hash(output_payload),
            ),
            version_tag=version_tag,
            source_ref=source_ref,
        )
        repo.add_audit_log(
            entity_type="sizing_run",
            entity_id=run.sizing_run_id,
            action="persist_ac_run",
            actor=actor,
            payload_json={
                "parent_run_id": parent_id,
                "content_hash": content_hash,
            },
            version_tag=version_tag,
            source_ref=source_ref,
        )
        session.flush()
        return AcRunResult(
            run_id=run.sizing_run_id,
            parent_run_id=parent_id,
            content_hash=content_hash,
            reused=False,
            alternatives=len(repo.list_child_runs(parent_id, run_type=AC_RUN_TYPE)),
        )


def list_ac_alternatives(dc_run_id: str, *, db_url: str | None = None) -> list[dict[str, Any]]:
    """AC alternatives recorded under one DC run, newest first.

    Shaped for the UI's alternative switcher (owner ruling C: the workbench keeps
    its three-level picker, and AC alternatives sit beside the run rather than
    becoming a fourth level).
    """
    parent_id = str(dc_run_id or "").strip()
    if not parent_id:
        return []
    with session_scope(db_url) as session:
        repo = RunRepository(session)
        rows = repo.list_child_runs(parent_id, run_type=AC_RUN_TYPE)
        return [
            {
                "run_id": row.sizing_run_id,
                "started_at": row.started_at,
                "finished_at": row.finished_at,
                "summary": dict(row.input_summary_json or {}),
                "output": dict(row.output_summary_json or {}),
            }
            for row in rows
        ]


def _now():
    from calb_sizing_tool.infra.db.base import utc_now

    return utc_now()


__all__ = [
    "AC_RUN_TYPE",
    "AC_INPUT_SNAPSHOT_KIND",
    "AC_OUTPUT_SNAPSHOT_KIND",
    "AcRunResult",
    "ac_configuration_hash",
    "list_ac_alternatives",
    "persist_ac_run",
]
