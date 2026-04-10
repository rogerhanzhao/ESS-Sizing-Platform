from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CanonicalBaseModel(BaseModel):
    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        populate_by_name=True,
        extra="forbid",
    )


class TimestampedSchema(CanonicalBaseModel):
    created_at: datetime | None = None
    updated_at: datetime | None = None


class AuditStamp(TimestampedSchema):
    source_ref: str | None = None
    version_tag: str | None = None


class JsonSnapshot(CanonicalBaseModel):
    payload: dict[str, Any] = Field(default_factory=dict)
