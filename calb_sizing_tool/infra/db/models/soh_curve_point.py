from __future__ import annotations

from sqlalchemy import ForeignKey, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from calb_sizing_tool.infra.db.base import Base, SourceVersionMixin, TimestampMixin, new_uuid


class SohCurvePoint(Base, TimestampMixin, SourceVersionMixin):
    __tablename__ = "soh_curve_point"

    soh_curve_point_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    soh_profile_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("soh_profile.soh_profile_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    life_year_index: Mapped[int] = mapped_column(Integer, nullable=False)
    cycle_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    soh_dc_pct: Mapped[float] = mapped_column(Float, nullable=False)
