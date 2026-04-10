from __future__ import annotations

from sqlalchemy import ForeignKey, JSON, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from calb_sizing_tool.infra.db.base import ActivePublishMixin, Base, SourceVersionMixin, TimestampMixin, new_uuid


class DcBlockTemplate(Base, TimestampMixin, SourceVersionMixin, ActivePublishMixin):
    __tablename__ = "dc_block_template"

    dc_block_template_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    rack_type_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("rack_type.rack_type_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    source_dc_block_template_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    dc_block_code: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    dc_block_name: Mapped[str] = mapped_column(String(255), nullable=False)
    block_form: Mapped[str] = mapped_column(String(32), nullable=False)
    container_length_ft: Mapped[int | None] = mapped_column(Integer, nullable=True)
    racks_per_block: Mapped[int | None] = mapped_column(Integer, nullable=True)
    packs_per_block: Mapped[int | None] = mapped_column(Integer, nullable=True)
    block_nameplate_capacity_mwh: Mapped[float | None] = mapped_column(Float, nullable=True)
    block_aux_energy_kwh: Mapped[float | None] = mapped_column(Float, nullable=True)
    design_max_c_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    raw_row_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
