"""Versioned catalogue evidence, isolated from active sizing inputs."""
from sqlalchemy import CheckConstraint, ForeignKey, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from calb_sizing_tool.infra.db.base import Base, TimestampMixin, new_uuid


class DcCatalogueRevision(Base, TimestampMixin):
    __tablename__ = 'dc_catalogue_revision'
    __table_args__ = (
        UniqueConstraint('product_dc_block_id', 'revision_label'),
        CheckConstraint("status IN ('draft', 'parameter_review', 'candidate_only', 'retired')",
                        name='dc_catalogue_revision_status'),
    )
    revision_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    product_dc_block_id: Mapped[str] = mapped_column(
        ForeignKey('product_dc_block.product_dc_block_id', ondelete='RESTRICT'), nullable=False)
    revision_label: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default='draft')
    snapshot_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    snapshot_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by: Mapped[str] = mapped_column(String(128), nullable=False)


class DcCatalogueRevisionEvent(Base, TimestampMixin):
    __tablename__ = 'dc_catalogue_revision_event'
    event_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    revision_id: Mapped[str] = mapped_column(
        ForeignKey('dc_catalogue_revision.revision_id', ondelete='RESTRICT'), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(32))
    to_status: Mapped[str] = mapped_column(String(32), nullable=False)
    actor: Mapped[str] = mapped_column(String(128), nullable=False)
    evidence_ref: Mapped[str] = mapped_column(Text, nullable=False)
