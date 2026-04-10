from __future__ import annotations

from sqlalchemy import ForeignKey, Float, String
from sqlalchemy.orm import Mapped, mapped_column

from calb_sizing_tool.infra.db.base import Base, SourceVersionMixin, TimestampMixin, new_uuid


class RteCurveBand(Base, TimestampMixin, SourceVersionMixin):
    __tablename__ = "rte_curve_band"

    rte_curve_band_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    rte_profile_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("rte_profile.rte_profile_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    soh_band_min_pct: Mapped[float] = mapped_column(Float, nullable=False)
    soh_band_max_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    rte_dc_pct: Mapped[float] = mapped_column(Float, nullable=False)
