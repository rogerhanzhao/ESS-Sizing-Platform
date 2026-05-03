from __future__ import annotations

from sqlalchemy import ForeignKey, JSON, Float, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from calb_sizing_tool.infra.db.base import ActivePublishMixin, Base, SourceVersionMixin, TimestampMixin, new_uuid


class RTECurve(Base, TimestampMixin, SourceVersionMixin, ActivePublishMixin):
    __tablename__ = "rte_curve"

    rte_curve_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    curve_code: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    product_cell_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("product_cell.product_cell_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    condition_label: Mapped[str] = mapped_column(String(255), nullable=False)
    soc_min_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    soc_max_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    temperature_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    c_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    rte_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    matrix_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    source: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
