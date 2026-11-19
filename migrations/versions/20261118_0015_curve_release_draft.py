"""Editable RTE review drafts, separate from immutable runtime packages."""
import sqlalchemy as sa
from alembic import op

revision = '20261118_0015'
down_revision = '20261118_0014'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('curve_release_draft',
        sa.Column('draft_id', sa.String(36), primary_key=True),
        sa.Column('base_release_id', sa.String(36), sa.ForeignKey('curve_release.release_id'), nullable=False),
        sa.Column('version_label', sa.String(128), nullable=False),
        sa.Column('payload_json', sa.JSON(), nullable=False),
        sa.Column('payload_sha256', sa.String(64), nullable=False),
        sa.Column('review_note', sa.Text(), nullable=False),
        sa.Column('actor', sa.String(128), nullable=False),
        sa.Column('status', sa.String(32), nullable=False),
        sa.Column('published_release_id', sa.String(36), sa.ForeignKey('curve_release.release_id'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False))


def downgrade():
    op.drop_table('curve_release_draft')
