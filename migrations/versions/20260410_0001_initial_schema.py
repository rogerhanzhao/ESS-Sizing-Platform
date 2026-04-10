"""initial schema

Revision ID: 20260410_0001
Revises:
Create Date: 2026-04-10 13:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260410_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "parameter_definition",
        sa.Column("parameter_definition_id", sa.String(length=36), primary_key=True),
        sa.Column("field_code", sa.String(length=128), nullable=False),
        sa.Column("display_name_en", sa.String(length=255), nullable=False),
        sa.Column("display_name_zh", sa.String(length=255), nullable=False),
        sa.Column("unit", sa.String(length=32), nullable=False),
        sa.Column("data_type", sa.String(length=32), nullable=False),
        sa.Column("nullable", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("required_for_stage", sa.String(length=64), nullable=False),
        sa.Column("validation_rule", sa.Text(), nullable=False),
        sa.Column("source_sheet", sa.String(length=128), nullable=False),
        sa.Column("legacy_field_name", sa.String(length=128), nullable=False),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column("version_tag", sa.String(length=64), nullable=True),
        sa.Column("source_ref", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_published", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("field_code"),
    )
    op.create_index("ix_parameter_definition_field_code", "parameter_definition", ["field_code"])

    op.create_table(
        "parameter_set",
        sa.Column("parameter_set_id", sa.String(length=36), primary_key=True),
        sa.Column("set_code", sa.String(length=128), nullable=False),
        sa.Column("set_name", sa.String(length=255), nullable=False),
        sa.Column("stage_scope", sa.String(length=64), nullable=False),
        sa.Column("parameter_values_json", sa.JSON(), nullable=False),
        sa.Column("version_tag", sa.String(length=64), nullable=True),
        sa.Column("source_ref", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_published", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("set_code"),
    )
    op.create_index("ix_parameter_set_set_code", "parameter_set", ["set_code"])

    op.create_table(
        "battery_cell_type",
        sa.Column("battery_cell_type_id", sa.String(length=36), primary_key=True),
        sa.Column("source_cell_type_id", sa.Integer(), nullable=True),
        sa.Column("cell_model", sa.String(length=128), nullable=True),
        sa.Column("chemistry_code", sa.String(length=64), nullable=True),
        sa.Column("cell_capacity_ah", sa.Float(), nullable=True),
        sa.Column("cell_nominal_voltage_v", sa.Float(), nullable=True),
        sa.Column("cell_energy_wh", sa.Float(), nullable=True),
        sa.Column("raw_row_json", sa.JSON(), nullable=False),
        sa.Column("version_tag", sa.String(length=64), nullable=True),
        sa.Column("source_ref", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_published", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_battery_cell_type_source_cell_type_id", "battery_cell_type", ["source_cell_type_id"])

    op.create_table(
        "pack_type",
        sa.Column("pack_type_id", sa.String(length=36), primary_key=True),
        sa.Column("battery_cell_type_id", sa.String(length=36), nullable=True),
        sa.Column("source_pack_type_id", sa.Integer(), nullable=True),
        sa.Column("pack_model", sa.String(length=128), nullable=True),
        sa.Column("cells_in_series", sa.Integer(), nullable=True),
        sa.Column("cells_in_parallel", sa.Integer(), nullable=True),
        sa.Column("pack_nominal_voltage_v", sa.Float(), nullable=True),
        sa.Column("pack_nameplate_capacity_kwh", sa.Float(), nullable=True),
        sa.Column("raw_row_json", sa.JSON(), nullable=False),
        sa.Column("version_tag", sa.String(length=64), nullable=True),
        sa.Column("source_ref", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_published", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["battery_cell_type_id"], ["battery_cell_type.battery_cell_type_id"], ondelete="SET NULL"),
    )
    op.create_index("ix_pack_type_battery_cell_type_id", "pack_type", ["battery_cell_type_id"])
    op.create_index("ix_pack_type_source_pack_type_id", "pack_type", ["source_pack_type_id"])

    op.create_table(
        "rack_type",
        sa.Column("rack_type_id", sa.String(length=36), primary_key=True),
        sa.Column("pack_type_id", sa.String(length=36), nullable=True),
        sa.Column("source_rack_type_id", sa.Integer(), nullable=True),
        sa.Column("rack_model", sa.String(length=128), nullable=True),
        sa.Column("packs_per_rack", sa.Integer(), nullable=True),
        sa.Column("rack_nameplate_capacity_mwh", sa.Float(), nullable=True),
        sa.Column("rack_aux_energy_kwh", sa.Float(), nullable=True),
        sa.Column("raw_row_json", sa.JSON(), nullable=False),
        sa.Column("version_tag", sa.String(length=64), nullable=True),
        sa.Column("source_ref", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_published", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["pack_type_id"], ["pack_type.pack_type_id"], ondelete="SET NULL"),
    )
    op.create_index("ix_rack_type_pack_type_id", "rack_type", ["pack_type_id"])
    op.create_index("ix_rack_type_source_rack_type_id", "rack_type", ["source_rack_type_id"])

    op.create_table(
        "dc_block_template",
        sa.Column("dc_block_template_id", sa.String(length=36), primary_key=True),
        sa.Column("rack_type_id", sa.String(length=36), nullable=True),
        sa.Column("source_dc_block_template_id", sa.Integer(), nullable=True),
        sa.Column("dc_block_code", sa.String(length=128), nullable=False),
        sa.Column("dc_block_name", sa.String(length=255), nullable=False),
        sa.Column("block_form", sa.String(length=32), nullable=False),
        sa.Column("container_length_ft", sa.Integer(), nullable=True),
        sa.Column("racks_per_block", sa.Integer(), nullable=True),
        sa.Column("packs_per_block", sa.Integer(), nullable=True),
        sa.Column("block_nameplate_capacity_mwh", sa.Float(), nullable=True),
        sa.Column("block_aux_energy_kwh", sa.Float(), nullable=True),
        sa.Column("design_max_c_rate", sa.Float(), nullable=True),
        sa.Column("raw_row_json", sa.JSON(), nullable=False),
        sa.Column("version_tag", sa.String(length=64), nullable=True),
        sa.Column("source_ref", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_published", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["rack_type_id"], ["rack_type.rack_type_id"], ondelete="SET NULL"),
    )
    op.create_index("ix_dc_block_template_dc_block_code", "dc_block_template", ["dc_block_code"])
    op.create_index("ix_dc_block_template_rack_type_id", "dc_block_template", ["rack_type_id"])
    op.create_index("ix_dc_block_template_source_dc_block_template_id", "dc_block_template", ["source_dc_block_template_id"])

    op.create_table(
        "soh_profile",
        sa.Column("soh_profile_id", sa.String(length=36), primary_key=True),
        sa.Column("battery_cell_type_id", sa.String(length=36), nullable=True),
        sa.Column("source_profile_id", sa.Integer(), nullable=True),
        sa.Column("profile_name", sa.String(length=255), nullable=True),
        sa.Column("cycles_per_year", sa.Integer(), nullable=True),
        sa.Column("c_rate", sa.Float(), nullable=True),
        sa.Column("reference_temperature_c", sa.Float(), nullable=True),
        sa.Column("raw_row_json", sa.JSON(), nullable=False),
        sa.Column("version_tag", sa.String(length=64), nullable=True),
        sa.Column("source_ref", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_published", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["battery_cell_type_id"], ["battery_cell_type.battery_cell_type_id"], ondelete="SET NULL"),
    )
    op.create_index("ix_soh_profile_battery_cell_type_id", "soh_profile", ["battery_cell_type_id"])
    op.create_index("ix_soh_profile_source_profile_id", "soh_profile", ["source_profile_id"])

    op.create_table(
        "soh_curve_point",
        sa.Column("soh_curve_point_id", sa.String(length=36), primary_key=True),
        sa.Column("soh_profile_id", sa.String(length=36), nullable=False),
        sa.Column("life_year_index", sa.Integer(), nullable=False),
        sa.Column("cycle_index", sa.Integer(), nullable=True),
        sa.Column("soh_dc_pct", sa.Float(), nullable=False),
        sa.Column("version_tag", sa.String(length=64), nullable=True),
        sa.Column("source_ref", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["soh_profile_id"], ["soh_profile.soh_profile_id"], ondelete="CASCADE"),
    )
    op.create_index("ix_soh_curve_point_soh_profile_id", "soh_curve_point", ["soh_profile_id"])

    op.create_table(
        "rte_profile",
        sa.Column("rte_profile_id", sa.String(length=36), primary_key=True),
        sa.Column("battery_cell_type_id", sa.String(length=36), nullable=True),
        sa.Column("source_profile_id", sa.Integer(), nullable=True),
        sa.Column("profile_name", sa.String(length=255), nullable=True),
        sa.Column("cycles_per_year", sa.Integer(), nullable=True),
        sa.Column("c_rate", sa.Float(), nullable=True),
        sa.Column("raw_row_json", sa.JSON(), nullable=False),
        sa.Column("version_tag", sa.String(length=64), nullable=True),
        sa.Column("source_ref", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_published", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["battery_cell_type_id"], ["battery_cell_type.battery_cell_type_id"], ondelete="SET NULL"),
    )
    op.create_index("ix_rte_profile_battery_cell_type_id", "rte_profile", ["battery_cell_type_id"])
    op.create_index("ix_rte_profile_source_profile_id", "rte_profile", ["source_profile_id"])

    op.create_table(
        "rte_curve_band",
        sa.Column("rte_curve_band_id", sa.String(length=36), primary_key=True),
        sa.Column("rte_profile_id", sa.String(length=36), nullable=False),
        sa.Column("soh_band_min_pct", sa.Float(), nullable=False),
        sa.Column("soh_band_max_pct", sa.Float(), nullable=True),
        sa.Column("rte_dc_pct", sa.Float(), nullable=False),
        sa.Column("version_tag", sa.String(length=64), nullable=True),
        sa.Column("source_ref", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["rte_profile_id"], ["rte_profile.rte_profile_id"], ondelete="CASCADE"),
    )
    op.create_index("ix_rte_curve_band_rte_profile_id", "rte_curve_band", ["rte_profile_id"])

    op.create_table(
        "project",
        sa.Column("project_id", sa.String(length=36), primary_key=True),
        sa.Column("project_code", sa.String(length=128), nullable=False),
        sa.Column("project_name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("version_tag", sa.String(length=64), nullable=True),
        sa.Column("source_ref", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_published", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("project_code"),
    )
    op.create_index("ix_project_project_code", "project", ["project_code"])

    op.create_table(
        "sizing_case",
        sa.Column("sizing_case_id", sa.String(length=36), primary_key=True),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("case_code", sa.String(length=128), nullable=False),
        sa.Column("case_name", sa.String(length=255), nullable=False),
        sa.Column("stage_scope", sa.String(length=64), nullable=False),
        sa.Column("scenario_mode", sa.String(length=64), nullable=False),
        sa.Column("input_json", sa.JSON(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("version_tag", sa.String(length=64), nullable=True),
        sa.Column("source_ref", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_published", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["project.project_id"], ondelete="CASCADE"),
        sa.UniqueConstraint("case_code"),
    )
    op.create_index("ix_sizing_case_case_code", "sizing_case", ["case_code"])
    op.create_index("ix_sizing_case_project_id", "sizing_case", ["project_id"])

    op.create_table(
        "sizing_run",
        sa.Column("sizing_run_id", sa.String(length=36), primary_key=True),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("sizing_case_id", sa.String(length=36), nullable=True),
        sa.Column("run_type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("input_summary_json", sa.JSON(), nullable=False),
        sa.Column("output_summary_json", sa.JSON(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("version_tag", sa.String(length=64), nullable=True),
        sa.Column("source_ref", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_published", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["project.project_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sizing_case_id"], ["sizing_case.sizing_case_id"], ondelete="SET NULL"),
    )
    op.create_index("ix_sizing_run_project_id", "sizing_run", ["project_id"])
    op.create_index("ix_sizing_run_run_type", "sizing_run", ["run_type"])
    op.create_index("ix_sizing_run_sizing_case_id", "sizing_run", ["sizing_case_id"])

    op.create_table(
        "run_input_snapshot",
        sa.Column("run_input_snapshot_id", sa.String(length=36), primary_key=True),
        sa.Column("sizing_run_id", sa.String(length=36), nullable=False),
        sa.Column("snapshot_kind", sa.String(length=64), nullable=False),
        sa.Column("content_hash", sa.String(length=128), nullable=True),
        sa.Column("snapshot_json", sa.JSON(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("version_tag", sa.String(length=64), nullable=True),
        sa.Column("source_ref", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["sizing_run_id"], ["sizing_run.sizing_run_id"], ondelete="CASCADE"),
    )
    op.create_index("ix_run_input_snapshot_sizing_run_id", "run_input_snapshot", ["sizing_run_id"])

    op.create_table(
        "run_output_snapshot",
        sa.Column("run_output_snapshot_id", sa.String(length=36), primary_key=True),
        sa.Column("sizing_run_id", sa.String(length=36), nullable=False),
        sa.Column("snapshot_kind", sa.String(length=64), nullable=False),
        sa.Column("content_hash", sa.String(length=128), nullable=True),
        sa.Column("snapshot_json", sa.JSON(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("version_tag", sa.String(length=64), nullable=True),
        sa.Column("source_ref", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["sizing_run_id"], ["sizing_run.sizing_run_id"], ondelete="CASCADE"),
    )
    op.create_index("ix_run_output_snapshot_sizing_run_id", "run_output_snapshot", ["sizing_run_id"])

    op.create_table(
        "artifact_registry",
        sa.Column("artifact_registry_id", sa.String(length=36), primary_key=True),
        sa.Column("sizing_run_id", sa.String(length=36), nullable=False),
        sa.Column("artifact_kind", sa.String(length=64), nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("file_path", sa.String(length=1024), nullable=False),
        sa.Column("media_type", sa.String(length=128), nullable=True),
        sa.Column("content_hash", sa.String(length=128), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("version_tag", sa.String(length=64), nullable=True),
        sa.Column("source_ref", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_published", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["sizing_run_id"], ["sizing_run.sizing_run_id"], ondelete="CASCADE"),
    )
    op.create_index("ix_artifact_registry_sizing_run_id", "artifact_registry", ["sizing_run_id"])

    op.create_table(
        "audit_log",
        sa.Column("audit_log_id", sa.String(length=36), primary_key=True),
        sa.Column("entity_type", sa.String(length=128), nullable=False),
        sa.Column("entity_id", sa.String(length=36), nullable=False),
        sa.Column("action", sa.String(length=128), nullable=False),
        sa.Column("actor", sa.String(length=128), nullable=True),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column("version_tag", sa.String(length=64), nullable=True),
        sa.Column("source_ref", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_audit_log_entity_id", "audit_log", ["entity_id"])
    op.create_index("ix_audit_log_entity_type", "audit_log", ["entity_type"])


def downgrade() -> None:
    for table in [
        "audit_log",
        "artifact_registry",
        "run_output_snapshot",
        "run_input_snapshot",
        "sizing_run",
        "sizing_case",
        "project",
        "rte_curve_band",
        "rte_profile",
        "soh_curve_point",
        "soh_profile",
        "dc_block_template",
        "rack_type",
        "pack_type",
        "battery_cell_type",
        "parameter_set",
        "parameter_definition",
    ]:
        op.drop_table(table)
