from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20260502_0006"
down_revision = "20260502_0005"
branch_labels = None
depends_on = None


def _columns(table_name: str) -> set[str]:
    bind = op.get_bind()
    return {column["name"] for column in sa.inspect(bind).get_columns(table_name)}


def _tables() -> set[str]:
    bind = op.get_bind()
    return set(sa.inspect(bind).get_table_names())


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def _source_and_status() -> list[sa.Column]:
    return [
        sa.Column("version_tag", sa.String(length=64), nullable=True),
        sa.Column("source_ref", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_published", sa.Boolean(), nullable=False, server_default=sa.false()),
    ]


def upgrade() -> None:
    if "block_form" not in _columns("product_dc_block"):
        with op.batch_alter_table("product_dc_block") as batch:
            batch.add_column(sa.Column("block_form", sa.String(length=32), nullable=True))

    if "product_asset" not in _tables():
        op.create_table(
            "product_asset",
            sa.Column("product_asset_id", sa.String(length=36), primary_key=True),
            sa.Column("asset_code", sa.String(length=160), nullable=False),
            sa.Column("owner_entity", sa.String(length=64), nullable=False),
            sa.Column("owner_id", sa.String(length=36), nullable=True),
            sa.Column("owner_code", sa.String(length=128), nullable=True),
            sa.Column("asset_kind", sa.String(length=64), nullable=False),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("file_name", sa.String(length=255), nullable=True),
            sa.Column("mime_type", sa.String(length=128), nullable=True),
            sa.Column("source_path", sa.Text(), nullable=True),
            sa.Column("storage_uri", sa.Text(), nullable=True),
            sa.Column("content_sha256", sa.String(length=64), nullable=True),
            sa.Column("caption", sa.Text(), nullable=True),
            sa.Column("proposal_section", sa.String(length=128), nullable=True),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("data_json", sa.JSON(), nullable=False),
            sa.Column("metadata_json", sa.JSON(), nullable=False),
            *_source_and_status(),
            *_timestamps(),
            sa.UniqueConstraint("asset_code"),
        )
        op.create_index("ix_product_asset_asset_code", "product_asset", ["asset_code"])
        op.create_index("ix_product_asset_owner_entity", "product_asset", ["owner_entity"])
        op.create_index("ix_product_asset_owner_id", "product_asset", ["owner_id"])
        op.create_index("ix_product_asset_owner_code", "product_asset", ["owner_code"])
        op.create_index("ix_product_asset_asset_kind", "product_asset", ["asset_kind"])


def downgrade() -> None:
    if "product_asset" in _tables():
        op.drop_index("ix_product_asset_asset_kind", table_name="product_asset")
        op.drop_index("ix_product_asset_owner_code", table_name="product_asset")
        op.drop_index("ix_product_asset_owner_id", table_name="product_asset")
        op.drop_index("ix_product_asset_owner_entity", table_name="product_asset")
        op.drop_index("ix_product_asset_asset_code", table_name="product_asset")
        op.drop_table("product_asset")

    # Do not drop product_dc_block.block_form on downgrade. Some local DBs already
    # had it from the historical app.py startup patch before this migration.
