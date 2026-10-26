"""Add isolated special-configuration lineage; no catalogue activation."""
import sqlalchemy as sa
from alembic import op

revision = '20261020_0012'
down_revision = '20261020_0011'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'dc_configuration_variant',
        sa.Column('relation_id', sa.String(36), primary_key=True),
        sa.Column('parent_revision_id', sa.String(36), sa.ForeignKey(
            'dc_catalogue_revision.revision_id', ondelete='RESTRICT'), nullable=False),
        sa.Column('child_revision_id', sa.String(36), sa.ForeignKey(
            'dc_catalogue_revision.revision_id', ondelete='RESTRICT'), nullable=False),
        sa.Column('parent_product_id', sa.String(36), sa.ForeignKey(
            'product_dc_block.product_dc_block_id', ondelete='RESTRICT'), nullable=False),
        sa.Column('child_product_id', sa.String(36), sa.ForeignKey(
            'product_dc_block.product_dc_block_id', ondelete='RESTRICT'), nullable=False),
        sa.Column('parent_revision_sha256', sa.String(64), nullable=False),
        sa.Column('child_revision_sha256', sa.String(64), nullable=False),
        sa.Column('version_label', sa.String(64), nullable=False),
        sa.Column('family_code', sa.String(128), nullable=False),
        sa.Column('use_scope', sa.String(32), nullable=False),
        sa.Column('status', sa.String(32), nullable=False),
        sa.Column('evidence_json', sa.JSON(), nullable=False),
        sa.Column('relation_sha256', sa.String(64), nullable=False),
        sa.Column('created_by', sa.String(128), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('child_revision_id'),
        sa.CheckConstraint("status IN ('draft', 'candidate_only', 'retired')",
                           name='dc_configuration_variant_status'),
        sa.CheckConstraint("use_scope = 'special_scenario_only'",
                           name='dc_configuration_variant_scope'),
        sa.CheckConstraint('parent_revision_id <> child_revision_id',
                           name='dc_configuration_variant_different_revisions'),
        sa.CheckConstraint('parent_product_id <> child_product_id',
                           name='dc_configuration_variant_different_products'),
    )
    op.create_index('ix_dc_configuration_variant_child_product_id',
                    'dc_configuration_variant', ['child_product_id'])
    op.create_table(
        'dc_configuration_variant_event',
        sa.Column('event_id', sa.String(36), primary_key=True),
        sa.Column('relation_id', sa.String(36), sa.ForeignKey(
            'dc_configuration_variant.relation_id', ondelete='RESTRICT'), nullable=False),
        sa.Column('from_status', sa.String(32)),
        sa.Column('to_status', sa.String(32), nullable=False),
        sa.Column('actor', sa.String(128), nullable=False),
        sa.Column('evidence_ref', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )


def downgrade():
    op.drop_table('dc_configuration_variant_event')
    op.drop_table('dc_configuration_variant')
