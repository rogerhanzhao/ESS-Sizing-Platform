from __future__ import annotations

from sqlalchemy import JSON, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from calb_sizing_tool.infra.db.base import ActivePublishMixin, Base, SourceVersionMixin, TimestampMixin, new_uuid


class BatteryCellType(Base, TimestampMixin, SourceVersionMixin, ActivePublishMixin):
    __tablename__ = "battery_cell_type"

    battery_cell_type_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    source_cell_type_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    cell_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    chemistry_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    cell_capacity_ah: Mapped[float | None] = mapped_column(Float, nullable=True)
    cell_nominal_voltage_v: Mapped[float | None] = mapped_column(Float, nullable=True)
    cell_energy_wh: Mapped[float | None] = mapped_column(Float, nullable=True)
    raw_row_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
