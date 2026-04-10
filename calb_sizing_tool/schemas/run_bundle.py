from __future__ import annotations

from calb_sizing_tool.schemas.common import CanonicalBaseModel
from calb_sizing_tool.schemas.run_snapshot import DcPipelineRunSnapshot, RunInputSnapshotSchema, RunOutputSnapshotSchema


class DcRunBundle(CanonicalBaseModel):
    run_id: str
    project_id: str | None = None
    project_code: str | None = None
    project_name: str | None = None
    sizing_case_id: str | None = None
    case_code: str | None = None
    case_name: str | None = None
    scenario_mode: str | None = None
    input_snapshot: RunInputSnapshotSchema | None = None
    output_snapshot: RunOutputSnapshotSchema | None = None
    snapshot: DcPipelineRunSnapshot
