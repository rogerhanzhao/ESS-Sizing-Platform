from __future__ import annotations

from sqlalchemy import ForeignKey, JSON, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from calb_sizing_tool.infra.db.base import ActivePublishMixin, Base, SourceVersionMixin, TimestampMixin, new_uuid


class ProductDCBlock(Base, TimestampMixin, SourceVersionMixin, ActivePublishMixin):
    __tablename__ = "product_dc_block"

    product_dc_block_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    block_code: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    block_name: Mapped[str] = mapped_column(String(255), nullable=False)
    product_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    product_cell_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("product_cell.product_cell_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    cells_in_series: Mapped[int | None] = mapped_column(Integer, nullable=True)
    strings_in_parallel: Mapped[int | None] = mapped_column(Integer, nullable=True)
    racks_per_block: Mapped[int | None] = mapped_column(Integer, nullable=True)
    packs_per_rack: Mapped[int | None] = mapped_column(Integer, nullable=True)
    racks_per_container: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pack_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    container_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    block_form: Mapped[str | None] = mapped_column(String(32), nullable=True)
    configuration: Mapped[str | None] = mapped_column(String(128), nullable=True)
    container_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    thermal_management: Mapped[str | None] = mapped_column(String(128), nullable=True)
    enclosure: Mapped[str | None] = mapped_column(String(255), nullable=True)
    gross_energy_mwh: Mapped[float | None] = mapped_column(Float, nullable=True)
    usable_energy_mwh: Mapped[float | None] = mapped_column(Float, nullable=True)
    rated_capacity_kwh: Mapped[float | None] = mapped_column(Float, nullable=True)
    nominal_voltage_v: Mapped[float | None] = mapped_column(Float, nullable=True)
    voltage_min_v: Mapped[float | None] = mapped_column(Float, nullable=True)
    voltage_max_v: Mapped[float | None] = mapped_column(Float, nullable=True)
    nominal_power_kw: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_current_a: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_c_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    charge_discharge_rate: Mapped[str | None] = mapped_column(String(64), nullable=True)
    dod_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    cycle_life_cycles: Mapped[int | None] = mapped_column(Integer, nullable=True)
    end_of_life_soh_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    service_life_years: Mapped[float | None] = mapped_column(Float, nullable=True)
    system_efficiency_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    dimension_width_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    dimension_depth_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    dimension_height_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    weight_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    ingress_protection: Mapped[str | None] = mapped_column(String(64), nullable=True)
    relative_humidity: Mapped[str | None] = mapped_column(String(128), nullable=True)
    working_temp_min_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    working_temp_max_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    storage_temp_min_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    storage_temp_max_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    altitude_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    bms_communication: Mapped[str | None] = mapped_column(String(255), nullable=True)
    compliance_standards: Mapped[str | None] = mapped_column(Text, nullable=True)
    seismic_rating: Mapped[str | None] = mapped_column(String(64), nullable=True)
    coating: Mapped[str | None] = mapped_column(String(255), nullable=True)
    firefighting_system: Mapped[str | None] = mapped_column(Text, nullable=True)
    explosion_protection: Mapped[str | None] = mapped_column(Text, nullable=True)
    default_degradation_curve_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
