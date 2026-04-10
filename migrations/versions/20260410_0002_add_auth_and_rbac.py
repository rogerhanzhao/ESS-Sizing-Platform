"""add auth and rbac

Revision ID: 20260410_0002
Revises: 20260410_0001
Create Date: 2026-04-10 21:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260410_0002"
down_revision = "20260410_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_account",
        sa.Column("user_id", sa.String(length=36), primary_key=True),
        sa.Column("username", sa.String(length=128), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("password_salt", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version_tag", sa.String(length=64), nullable=True),
        sa.Column("source_ref", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_published", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("username"),
        sa.UniqueConstraint("email"),
    )
    op.create_index("ix_user_account_username", "user_account", ["username"])
    op.create_index("ix_user_account_email", "user_account", ["email"])

    op.create_table(
        "role_definition",
        sa.Column("role_id", sa.String(length=36), primary_key=True),
        sa.Column("role_code", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("version_tag", sa.String(length=64), nullable=True),
        sa.Column("source_ref", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_published", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("role_code"),
    )
    op.create_index("ix_role_definition_role_code", "role_definition", ["role_code"])

    op.create_table(
        "user_role_binding",
        sa.Column("user_role_binding_id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("role_id", sa.String(length=36), nullable=False),
        sa.Column("version_tag", sa.String(length=64), nullable=True),
        sa.Column("source_ref", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["role_id"], ["role_definition.role_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["user_account.user_id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "role_id"),
    )
    op.create_index("ix_user_role_binding_user_id", "user_role_binding", ["user_id"])
    op.create_index("ix_user_role_binding_role_id", "user_role_binding", ["role_id"])

    op.create_table(
        "project_member",
        sa.Column("project_member_id", sa.String(length=36), primary_key=True),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("role_id", sa.String(length=36), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("version_tag", sa.String(length=64), nullable=True),
        sa.Column("source_ref", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["project.project_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["role_id"], ["role_definition.role_id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["user_account.user_id"], ondelete="CASCADE"),
        sa.UniqueConstraint("project_id", "user_id"),
    )
    op.create_index("ix_project_member_project_id", "project_member", ["project_id"])
    op.create_index("ix_project_member_user_id", "project_member", ["user_id"])
    op.create_index("ix_project_member_role_id", "project_member", ["role_id"])


def downgrade() -> None:
    for table in [
        "project_member",
        "user_role_binding",
        "role_definition",
        "user_account",
    ]:
        op.drop_table(table)
