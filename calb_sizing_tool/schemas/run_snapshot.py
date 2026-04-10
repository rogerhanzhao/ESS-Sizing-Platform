from __future__ import annotations

from typing import Any

from calb_sizing_tool.schemas.common import CanonicalBaseModel
from calb_sizing_tool.schemas.stage1 import Stage1Result
from calb_sizing_tool.schemas.stage2 import Stage2Result
from calb_sizing_tool.schemas.stage3 import Stage3Result


class RunInputSnapshotSchema(CanonicalBaseModel):
    snapshot_kind: str
    payload: dict[str, Any]
    content_hash: str | None = None


class RunOutputSnapshotSchema(CanonicalBaseModel):
    snapshot_kind: str
    payload: dict[str, Any]
    content_hash: str | None = None


class DcPipelineRunSnapshot(CanonicalBaseModel):
    stage1: Stage1Result
    stage2: Stage2Result
    stage3: Stage3Result
    iteration_count: int
    poi_usable_energy_mwh_at_guarantee_year: float | None
    converged: bool
    summary: dict[str, Any]
