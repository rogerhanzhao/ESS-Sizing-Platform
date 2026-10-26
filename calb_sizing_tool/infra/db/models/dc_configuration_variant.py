"""Local pilot lineage for special-scenario 20ft DC configurations."""
from sqlalchemy import CheckConstraint, ForeignKey, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from calb_sizing_tool.infra.db.base import Base, TimestampMixin, new_uuid


class DcConfigurationVariant(Base, TimestampMixin):
    __tablename__ = 'dc_configuration_variant'
    __table_args__ = (
        UniqueConstraint('child_revision_id'),
        CheckConstraint("status IN ('draft', 'candidate_only', 'retired')",
                        name='dc_configuration_variant_status'),
        CheckConstraint("use_scope = 'special_scenario_only'",
                        name='dc_configuration_variant_scope'),
        CheckConstraint('parent_revision_id <> child_revision_id',
                        name='dc_configuration_variant_different_revisions'),
        CheckConstraint('parent_product_id <> child_product_id',
                        name='dc_configuration_variant_different_products'),
    )
    relation_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    parent_revision_id: Mapped[str] = mapped_column(
        ForeignKey('dc_catalogue_revision.revision_id', ondelete='RESTRICT'), nullable=False)
    child_revision_id: Mapped[str] = mapped_column(
        ForeignKey('dc_catalogue_revision.revision_id', ondelete='RESTRICT'), nullable=False)
    parent_product_id: Mapped[str] = mapped_column(
        ForeignKey('product_dc_block.product_dc_block_id', ondelete='RESTRICT'), nullable=False)
    child_product_id: Mapped[str] = mapped_column(
        ForeignKey('product_dc_block.product_dc_block_id', ondelete='RESTRICT'), nullable=False,
        index=True)
    parent_revision_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    child_revision_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    version_label: Mapped[str] = mapped_column(String(64), nullable=False)
    family_code: Mapped[str] = mapped_column(String(128), nullable=False)
    use_scope: Mapped[str] = mapped_column(String(32), nullable=False,
                                         default='special_scenario_only')
    status: Mapped[str] = mapped_column(String(32), nullable=False, default='draft')
    evidence_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    relation_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by: Mapped[str] = mapped_column(String(128), nullable=False)


class DcConfigurationVariantEvent(Base, TimestampMixin):
    __tablename__ = 'dc_configuration_variant_event'
    event_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    relation_id: Mapped[str] = mapped_column(
        ForeignKey('dc_configuration_variant.relation_id', ondelete='RESTRICT'), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(32))
    to_status: Mapped[str] = mapped_column(String(32), nullable=False)
    actor: Mapped[str] = mapped_column(String(128), nullable=False)
    evidence_ref: Mapped[str] = mapped_column(Text, nullable=False)
