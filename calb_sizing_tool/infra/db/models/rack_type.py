from __future__ import annotations

from sqlalchemy import ForeignKey, JSON, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from calb_sizing_tool.infra.db.base import ActivePublishMixin, Base, SourceVersionMixin, TimestampMixin, new_uuid


class RackType(Base, TimestampMixin, SourceVersionMixin, ActivePublishMixin):
    __tablename__ = "rack_type"

    rack_type_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    pack_type_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("pack_type.pack_type_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    source_rack_type_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    rack_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    packs_per_rack: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rack_nameplate_capacity_mwh: Mapped[float | None] = mapped_column(Float, nullable=True)
    rack_aux_energy_kwh: Mapped[float | None] = mapped_column(Float, nullable=True)
    raw_row_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
