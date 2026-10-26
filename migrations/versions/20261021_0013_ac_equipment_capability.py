"""Add isolated equipment capability evidence; no legacy product activation."""

import sqlalchemy as sa
from alembic import op

revision = "20261021_0013"
down_revision = "20261020_0012"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "ac_equipment_capability_revision",
        sa.Column("revision_id", sa.String(36), primary_key=True),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("package_code", sa.String(128), nullable=False),
        sa.Column("revision", sa.String(64), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("payload_sha256", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("is_published", sa.Boolean(), nullable=False),
        sa.Column("created_by", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("kind", "package_code", "revision"),
        sa.CheckConstraint("kind IN ('pcs', 'transformer')", name="equipment_capability_kind"),
        sa.CheckConstraint("status IN ('draft', 'parameter_review', 'candidate_only', 'retired')",
                           name="equipment_capability_status"),
    )
    op.create_table(
        "ac_equipment_capability_event",
        sa.Column("event_id", sa.String(36), primary_key=True),
        sa.Column("revision_id", sa.String(36), sa.ForeignKey(
            "ac_equipment_capability_revision.revision_id", ondelete="RESTRICT"), nullable=False),
        sa.Column("event_number", sa.Integer(), nullable=False),
        sa.Column("from_status", sa.String(32)),
        sa.Column("to_status", sa.String(32), nullable=False),
        sa.Column("actor", sa.String(128), nullable=False),
        sa.Column("evidence_ref", sa.Text(), nullable=False),
        sa.Column("previous_event_sha256", sa.String(64)),
        sa.Column("event_sha256", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("revision_id", "event_number"),
        sa.CheckConstraint("event_number > 0", name="equipment_capability_event_number"),
    )


def downgrade():
    op.drop_table("ac_equipment_capability_event")
    op.drop_table("ac_equipment_capability_revision")
