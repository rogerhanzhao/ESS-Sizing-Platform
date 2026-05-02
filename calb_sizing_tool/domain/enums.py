from __future__ import annotations

from enum import Enum


class StrEnum(str, Enum):
    def __str__(self) -> str:
        return str(self.value)


class ScenarioMode(StrEnum):
    CONTAINER_ONLY = "container_only"
    CABINET_ONLY = "cabinet_only"
    HYBRID = "hybrid"


class RunStatus(StrEnum):
    DRAFT = "draft"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    ARCHIVED = "archived"


class StageCode(StrEnum):
    STAGE1 = "stage1"
    STAGE2 = "stage2"
    STAGE3 = "stage3"
    DC_PIPELINE = "dc_pipeline"


class ArtifactKind(StrEnum):
    REPORT = "report"
    SLD = "sld"
    LAYOUT = "layout"
    SNAPSHOT = "snapshot"
    CSV = "csv"


class DataSourceKind(StrEnum):
    EXCEL = "excel"
    DATABASE = "database"
    IMPORT = "import"
    SESSION = "session"


class ParameterDataType(StrEnum):
    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    PERCENT = "percent"
    JSON = "json"


class ImportMode(StrEnum):
    DRY_RUN = "dry_run"
    PREVIEW_DIFF = "preview_diff"
    APPLY_IMPORT = "apply_import"


class ValidationSeverity(StrEnum):
    ERROR = "error"
    WARNING = "warning"


class StageScope(StrEnum):
    DC = "dc"
    AC = "ac"
