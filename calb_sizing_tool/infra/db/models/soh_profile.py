from __future__ import annotations

from sqlalchemy import ForeignKey, JSON, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from calb_sizing_tool.infra.db.base import ActivePublishMixin, Base, SourceVersionMixin, TimestampMixin, new_uuid


class SohProfile(Base, TimestampMixin, SourceVersionMixin, ActivePublishMixin):
    __tablename__ = "soh_profile"

    soh_profile_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    battery_cell_type_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("battery_cell_type.battery_cell_type_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    source_profile_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    profile_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    cycles_per_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    c_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    reference_temperature_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    raw_row_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
