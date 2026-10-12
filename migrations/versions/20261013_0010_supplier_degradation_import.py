"""Persist supplier curve candidates without modifying active sizing tables."""
import sqlalchemy as sa
from alembic import op

revision = "20261013_0010"
down_revision = "20260804_0009"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "supplier_degradation_import",
        sa.Column("import_id", sa.String(36), primary_key=True),
        sa.Column("source_sha256", sa.String(64), nullable=False, unique=True),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("version_label", sa.String(128), nullable=False),
        sa.Column("actor", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("source_bytes", sa.LargeBinary(), nullable=False),
        sa.Column("dataset_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status = 'candidate'", name="ck_supplier_degradation_import_candidate_only"),
    )


def downgrade():
    op.drop_table("supplier_degradation_import")
