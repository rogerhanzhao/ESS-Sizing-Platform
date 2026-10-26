"""Add isolated product revision evidence; never backfill sizing eligibility."""
import sqlalchemy as sa
from alembic import op

revision = '20261020_0011'
down_revision = '20261013_0010'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'dc_catalogue_revision',
        sa.Column('revision_id', sa.String(36), primary_key=True),
        sa.Column('product_dc_block_id', sa.String(36), sa.ForeignKey(
            'product_dc_block.product_dc_block_id', ondelete='RESTRICT'), nullable=False),
        sa.Column('revision_label', sa.String(64), nullable=False),
        sa.Column('status', sa.String(32), nullable=False),
        sa.Column('snapshot_json', sa.JSON(), nullable=False),
        sa.Column('snapshot_sha256', sa.String(64), nullable=False),
        sa.Column('created_by', sa.String(128), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('product_dc_block_id', 'revision_label'),
        sa.CheckConstraint("status IN ('draft', 'parameter_review', 'candidate_only', 'retired')",
                           name='dc_catalogue_revision_status'),
    )
    op.create_table(
        'dc_catalogue_revision_event',
        sa.Column('event_id', sa.String(36), primary_key=True),
        sa.Column('revision_id', sa.String(36), sa.ForeignKey(
            'dc_catalogue_revision.revision_id', ondelete='RESTRICT'), nullable=False),
        sa.Column('from_status', sa.String(32)),
        sa.Column('to_status', sa.String(32), nullable=False),
        sa.Column('actor', sa.String(128), nullable=False),
        sa.Column('evidence_ref', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )


def downgrade():
    op.drop_table('dc_catalogue_revision_event')
    op.drop_table('dc_catalogue_revision')
