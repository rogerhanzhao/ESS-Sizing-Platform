from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20260502_0004"
down_revision = "20260410_0003"
branch_labels = None
depends_on = None


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
    op.create_table(
        "product_cell",
        sa.Column("product_cell_id", sa.String(length=36), primary_key=True),
        sa.Column("cell_code", sa.String(length=128), nullable=False),
        sa.Column("model_name", sa.String(length=255), nullable=False),
        sa.Column("chemistry", sa.String(length=64), nullable=False),
        sa.Column("manufacturer", sa.String(length=255), nullable=True),
        sa.Column("nominal_capacity_ah", sa.Float(), nullable=True),
        sa.Column("nominal_voltage_v", sa.Float(), nullable=True),
        sa.Column("min_voltage_v", sa.Float(), nullable=True),
        sa.Column("max_voltage_v", sa.Float(), nullable=True),
        sa.Column("length_mm", sa.Float(), nullable=True),
        sa.Column("width_mm", sa.Float(), nullable=True),
        sa.Column("height_mm", sa.Float(), nullable=True),
        sa.Column("weight_kg", sa.Float(), nullable=True),
        sa.Column("gravimetric_density_wh_kg", sa.Float(), nullable=True),
        sa.Column("volumetric_density_wh_l", sa.Float(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        *_source_and_status(),
        *_timestamps(),
        sa.UniqueConstraint("cell_code"),
    )
    op.create_index("ix_product_cell_cell_code", "product_cell", ["cell_code"])

    op.create_table(
        "product_dc_block",
        sa.Column("product_dc_block_id", sa.String(length=36), primary_key=True),
        sa.Column("block_code", sa.String(length=128), nullable=False),
        sa.Column("block_name", sa.String(length=255), nullable=False),
        sa.Column("product_cell_id", sa.String(length=36), nullable=True),
        sa.Column("cells_in_series", sa.Integer(), nullable=True),
        sa.Column("strings_in_parallel", sa.Integer(), nullable=True),
        sa.Column("racks_per_block", sa.Integer(), nullable=True),
        sa.Column("container_type", sa.String(length=128), nullable=True),
        sa.Column("thermal_management", sa.String(length=128), nullable=True),
        sa.Column("gross_energy_mwh", sa.Float(), nullable=True),
        sa.Column("usable_energy_mwh", sa.Float(), nullable=True),
        sa.Column("nominal_voltage_v", sa.Float(), nullable=True),
        sa.Column("max_c_rate", sa.Float(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        *_source_and_status(),
        *_timestamps(),
        sa.ForeignKeyConstraint(["product_cell_id"], ["product_cell.product_cell_id"], ondelete="SET NULL"),
        sa.UniqueConstraint("block_code"),
    )
    op.create_index("ix_product_dc_block_block_code", "product_dc_block", ["block_code"])
    op.create_index("ix_product_dc_block_product_cell_id", "product_dc_block", ["product_cell_id"])

    op.create_table(
        "product_ac_block",
        sa.Column("product_ac_block_id", sa.String(length=36), primary_key=True),
        sa.Column("block_code", sa.String(length=128), nullable=False),
        sa.Column("block_name", sa.String(length=255), nullable=False),
        sa.Column("pcs_model", sa.String(length=255), nullable=True),
        sa.Column("pcs_power_kw", sa.Float(), nullable=True),
        sa.Column("pcs_count", sa.Integer(), nullable=True),
        sa.Column("transformer_kva", sa.Float(), nullable=True),
        sa.Column("hv_voltage_kv", sa.Float(), nullable=True),
        sa.Column("lv_voltage_v", sa.Float(), nullable=True),
        sa.Column("peak_efficiency_pct", sa.Float(), nullable=True),
        sa.Column("aux_load_kw", sa.Float(), nullable=True),
        sa.Column("efficiency_curve_json", sa.JSON(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        *_source_and_status(),
        *_timestamps(),
        sa.UniqueConstraint("block_code"),
    )
    op.create_index("ix_product_ac_block_block_code", "product_ac_block", ["block_code"])

    op.create_table(
        "degradation_curve",
        sa.Column("degradation_curve_id", sa.String(length=36), primary_key=True),
        sa.Column("curve_code", sa.String(length=128), nullable=False),
        sa.Column("product_cell_id", sa.String(length=36), nullable=True),
        sa.Column("condition_label", sa.String(length=255), nullable=False),
        sa.Column("temperature_c", sa.Float(), nullable=True),
        sa.Column("dod_pct", sa.Float(), nullable=True),
        sa.Column("c_rate", sa.Float(), nullable=True),
        sa.Column("calendar_years", sa.Float(), nullable=True),
        sa.Column("cycle_points_json", sa.JSON(), nullable=False),
        sa.Column("calendar_points_json", sa.JSON(), nullable=False),
        sa.Column("source", sa.String(length=255), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        *_source_and_status(),
        *_timestamps(),
        sa.ForeignKeyConstraint(["product_cell_id"], ["product_cell.product_cell_id"], ondelete="SET NULL"),
        sa.UniqueConstraint("curve_code"),
    )
    op.create_index("ix_degradation_curve_curve_code", "degradation_curve", ["curve_code"])
    op.create_index("ix_degradation_curve_product_cell_id", "degradation_curve", ["product_cell_id"])

    op.create_table(
        "rte_curve",
        sa.Column("rte_curve_id", sa.String(length=36), primary_key=True),
        sa.Column("curve_code", sa.String(length=128), nullable=False),
        sa.Column("product_cell_id", sa.String(length=36), nullable=True),
        sa.Column("condition_label", sa.String(length=255), nullable=False),
        sa.Column("soc_min_pct", sa.Float(), nullable=True),
        sa.Column("soc_max_pct", sa.Float(), nullable=True),
        sa.Column("temperature_c", sa.Float(), nullable=True),
        sa.Column("c_rate", sa.Float(), nullable=True),
        sa.Column("rte_pct", sa.Float(), nullable=True),
        sa.Column("matrix_json", sa.JSON(), nullable=False),
        sa.Column("source", sa.String(length=255), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        *_source_and_status(),
        *_timestamps(),
        sa.ForeignKeyConstraint(["product_cell_id"], ["product_cell.product_cell_id"], ondelete="SET NULL"),
        sa.UniqueConstraint("curve_code"),
    )
    op.create_index("ix_rte_curve_curve_code", "rte_curve", ["curve_code"])
    op.create_index("ix_rte_curve_product_cell_id", "rte_curve", ["product_cell_id"])

    op.create_table(
        "degradation_plugin",
        sa.Column("degradation_plugin_id", sa.String(length=36), primary_key=True),
        sa.Column("plugin_key", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("plugin_version", sa.String(length=64), nullable=False),
        sa.Column("entrypoint", sa.String(length=512), nullable=False),
        sa.Column("schema_version", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("schema_json", sa.JSON(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        *_source_and_status(),
        *_timestamps(),
        sa.UniqueConstraint("plugin_key"),
    )
    op.create_index("ix_degradation_plugin_plugin_key", "degradation_plugin", ["plugin_key"])


def downgrade() -> None:
    op.drop_index("ix_degradation_plugin_plugin_key", table_name="degradation_plugin")
    op.drop_table("degradation_plugin")
    op.drop_index("ix_rte_curve_product_cell_id", table_name="rte_curve")
    op.drop_index("ix_rte_curve_curve_code", table_name="rte_curve")
    op.drop_table("rte_curve")
    op.drop_index("ix_degradation_curve_product_cell_id", table_name="degradation_curve")
    op.drop_index("ix_degradation_curve_curve_code", table_name="degradation_curve")
    op.drop_table("degradation_curve")
    op.drop_index("ix_product_ac_block_block_code", table_name="product_ac_block")
    op.drop_table("product_ac_block")
    op.drop_index("ix_product_dc_block_product_cell_id", table_name="product_dc_block")
    op.drop_index("ix_product_dc_block_block_code", table_name="product_dc_block")
    op.drop_table("product_dc_block")
    op.drop_index("ix_product_cell_cell_code", table_name="product_cell")
    op.drop_table("product_cell")
