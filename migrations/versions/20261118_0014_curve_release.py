"""Versioned runtime SOH/RTE packages and an explicit default pointer."""
import sqlalchemy as sa
from alembic import op

revision = '20261118_0014'
down_revision = '20261021_0013'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('curve_release',
        sa.Column('release_id', sa.String(36), primary_key=True),
        sa.Column('version_label', sa.String(128), nullable=False, unique=True),
        sa.Column('source_import_id', sa.String(36), sa.ForeignKey('supplier_degradation_import.import_id'), nullable=False),
        sa.Column('status', sa.String(32), nullable=False),
        sa.Column('payload_json', sa.JSON(), nullable=False),
        sa.Column('payload_sha256', sa.String(64), nullable=False),
        sa.Column('review_note', sa.Text(), nullable=False),
        sa.Column('actor', sa.String(128), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False))
    op.create_table('curve_default_binding',
        sa.Column('scope_key', sa.String(128), primary_key=True),
        sa.Column('release_id', sa.String(36), sa.ForeignKey('curve_release.release_id'), nullable=False),
        sa.Column('family_key', sa.String(128), nullable=False),
        sa.Column('revision', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False))


def downgrade():
    op.drop_table('curve_default_binding')
    op.drop_table('curve_release')
