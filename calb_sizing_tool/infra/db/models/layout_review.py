from __future__ import annotations

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from calb_sizing_tool.infra.db.base import Base, TimestampMixin, new_uuid


class LayoutReview(Base, TimestampMixin):
    __tablename__ = "layout_review"

    review_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    submission_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("external_artifact_submission.submission_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    decision: Mapped[str] = mapped_column(String(64), nullable=False)
    reviewer: Mapped[str | None] = mapped_column(String(128), nullable=True)
    comments: Mapped[str | None] = mapped_column(Text, nullable=True)
