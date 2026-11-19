"""Editable administrator working copies; publication creates a new release."""
from sqlalchemy import JSON, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from calb_sizing_tool.infra.db.base import Base, TimestampMixin, new_uuid


class CurveReleaseDraft(Base, TimestampMixin):
    __tablename__ = 'curve_release_draft'
    draft_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    base_release_id: Mapped[str] = mapped_column(ForeignKey('curve_release.release_id'), nullable=False)
    version_label: Mapped[str] = mapped_column(String(128), nullable=False)
    payload_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    review_note: Mapped[str] = mapped_column(Text, nullable=False)
    actor: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default='draft', nullable=False)
    published_release_id: Mapped[str | None] = mapped_column(ForeignKey('curve_release.release_id'), nullable=True)
