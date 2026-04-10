"""add external artifact submission and layout review

Revision ID: 20260410_0003
Revises: 20260410_0002
Create Date: 2026-04-10 22:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260410_0003"
down_revision = "20260410_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "external_artifact_submission",
        sa.Column("submission_id", sa.String(length=36), primary_key=True),
        sa.Column("sizing_run_id", sa.String(length=36), nullable=False),
        sa.Column("plugin_id", sa.String(length=128), nullable=False),
        sa.Column("plugin_version", sa.String(length=64), nullable=False),
        sa.Column("artifact_kind", sa.String(length=64), nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("file_path", sa.String(length=1024), nullable=False),
        sa.Column("media_type", sa.String(length=128), nullable=True),
        sa.Column("content_hash", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=64), nullable=False, server_default="pending_review"),
        sa.Column("ai_label", sa.String(length=64), nullable=False, server_default="ai_generated_preview"),
        sa.Column("actor", sa.String(length=128), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("version_tag", sa.String(length=64), nullable=True),
        sa.Column("source_ref", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["sizing_run_id"], ["sizing_run.sizing_run_id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_external_artifact_submission_sizing_run_id",
        "external_artifact_submission",
        ["sizing_run_id"],
    )

    op.create_table(
        "layout_review",
        sa.Column("review_id", sa.String(length=36), primary_key=True),
        sa.Column("submission_id", sa.String(length=36), nullable=False),
        sa.Column("decision", sa.String(length=64), nullable=False),
        sa.Column("reviewer", sa.String(length=128), nullable=True),
        sa.Column("comments", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["submission_id"], ["external_artifact_submission.submission_id"], ondelete="CASCADE"),
    )
    op.create_index("ix_layout_review_submission_id", "layout_review", ["submission_id"])


def downgrade() -> None:
    for table in [
        "layout_review",
        "external_artifact_submission",
    ]:
        op.drop_table(table)
