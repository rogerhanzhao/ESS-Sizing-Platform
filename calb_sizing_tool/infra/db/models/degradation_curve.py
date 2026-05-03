from __future__ import annotations

from sqlalchemy import ForeignKey, JSON, Float, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from calb_sizing_tool.infra.db.base import ActivePublishMixin, Base, SourceVersionMixin, TimestampMixin, new_uuid


class DegradationCurve(Base, TimestampMixin, SourceVersionMixin, ActivePublishMixin):
    __tablename__ = "degradation_curve"

    degradation_curve_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    curve_code: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    product_cell_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("product_cell.product_cell_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    curve_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    curve_family: Mapped[str | None] = mapped_column(String(128), nullable=True)
    basis_cell_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    default_scope: Mapped[str | None] = mapped_column(String(64), nullable=True)
    data_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    condition_label: Mapped[str] = mapped_column(String(255), nullable=False)
    temperature_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    dod_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    c_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    calendar_years: Mapped[float | None] = mapped_column(Float, nullable=True)
    end_of_life_soh_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    cycle_points_json: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    calendar_points_json: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    source: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
