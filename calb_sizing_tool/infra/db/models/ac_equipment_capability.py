"""Independent, immutable equipment evidence and its administrative review trail."""

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from calb_sizing_tool.infra.db.base import Base, TimestampMixin, new_uuid


class EquipmentCapabilityRevision(Base, TimestampMixin):
    __tablename__ = "ac_equipment_capability_revision"
    __table_args__ = (
        UniqueConstraint("kind", "package_code", "revision"),
        CheckConstraint("kind IN ('pcs', 'transformer')", name="equipment_capability_kind"),
        CheckConstraint("status IN ('draft', 'parameter_review', 'candidate_only', 'retired')",
                        name="equipment_capability_status"),
    )
    revision_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    package_code: Mapped[str] = mapped_column(String(128), nullable=False)
    revision: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_published: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_by: Mapped[str] = mapped_column(String(128), nullable=False)


class EquipmentCapabilityRevisionEvent(Base, TimestampMixin):
    __tablename__ = "ac_equipment_capability_event"
    __table_args__ = (
        UniqueConstraint("revision_id", "event_number"),
        CheckConstraint("event_number > 0", name="equipment_capability_event_number"),
    )
    event_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    revision_id: Mapped[str] = mapped_column(
        ForeignKey("ac_equipment_capability_revision.revision_id", ondelete="RESTRICT"), nullable=False)
    event_number: Mapped[int] = mapped_column(Integer, nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(32))
    to_status: Mapped[str] = mapped_column(String(32), nullable=False)
    actor: Mapped[str] = mapped_column(String(128), nullable=False)
    evidence_ref: Mapped[str] = mapped_column(Text, nullable=False)
    previous_event_sha256: Mapped[str | None] = mapped_column(String(64))
    event_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
