from __future__ import annotations

from sqlalchemy import JSON, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from calb_sizing_tool.infra.db.base import ActivePublishMixin, Base, SourceVersionMixin, TimestampMixin, new_uuid


class ProductCell(Base, TimestampMixin, SourceVersionMixin, ActivePublishMixin):
    __tablename__ = "product_cell"

    product_cell_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    cell_code: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    model_name: Mapped[str] = mapped_column(String(255), nullable=False)
    chemistry: Mapped[str] = mapped_column(String(64), nullable=False)
    manufacturer: Mapped[str | None] = mapped_column(String(255), nullable=True)
    nominal_capacity_ah: Mapped[float | None] = mapped_column(Float, nullable=True)
    shipping_capacity_ah: Mapped[float | None] = mapped_column(Float, nullable=True)
    nominal_voltage_v: Mapped[float | None] = mapped_column(Float, nullable=True)
    min_voltage_v: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_voltage_v: Mapped[float | None] = mapped_column(Float, nullable=True)
    rated_energy_wh: Mapped[float | None] = mapped_column(Float, nullable=True)
    length_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    width_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    height_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    shoulder_height_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    weight_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    volume_l: Mapped[float | None] = mapped_column(Float, nullable=True)
    gravimetric_density_wh_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    volumetric_density_wh_l: Mapped[float | None] = mapped_column(Float, nullable=True)
    energy_efficiency_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    dcr_mohm: Mapped[float | None] = mapped_column(Float, nullable=True)
    rated_c_rate_label: Mapped[str | None] = mapped_column(String(64), nullable=True)
    cycle_life_cycles: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cycle_life_rate_label: Mapped[str | None] = mapped_column(String(64), nullable=True)
    cycle_life_dod_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    end_of_life_soh_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    manufacturing_process: Mapped[str | None] = mapped_column(String(64), nullable=True)
    launch_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
