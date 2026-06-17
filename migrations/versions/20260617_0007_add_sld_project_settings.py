from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op


revision = "20260617_0007"
down_revision = "20260502_0006"
branch_labels = None
depends_on = None


def _tables() -> set[str]:
    bind = op.get_bind()
    return set(sa.inspect(bind).get_table_names())


def _json_dict(value) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except Exception:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _backfill_from_case_json() -> None:
    bind = op.get_bind()
    now = datetime.now(timezone.utc)
    rows = bind.execute(sa.text("SELECT sizing_case_id, input_json FROM sizing_case")).fetchall()
    for row in rows:
        input_json = _json_dict(row.input_json)
        project_settings = input_json.get("project_settings")
        if not isinstance(project_settings, dict) or not project_settings:
            continue
        existing = bind.execute(
            sa.text("SELECT 1 FROM sld_project_settings WHERE sizing_case_id = :case_id"),
            {"case_id": row.sizing_case_id},
        ).first()
        if existing is not None:
            continue
        bind.execute(
            sa.text(
                """
                INSERT INTO sld_project_settings (
                    sld_project_settings_id,
                    sizing_case_id,
                    settings_json,
                    notes,
                    version_tag,
                    source_ref,
                    is_active,
                    is_published,
                    created_at,
                    updated_at
                )
                VALUES (
                    :settings_id,
                    :case_id,
                    :settings_json,
                    NULL,
                    NULL,
                    :source_ref,
                    1,
                    0,
                    :created_at,
                    :updated_at
                )
                """
            ),
            {
                "settings_id": str(uuid.uuid4()),
                "case_id": row.sizing_case_id,
                "settings_json": json.dumps(project_settings, sort_keys=True),
                "source_ref": "migration:case_input_json_project_settings",
                "created_at": now,
                "updated_at": now,
            },
        )


def upgrade() -> None:
    if "sld_project_settings" not in _tables():
        op.create_table(
            "sld_project_settings",
            sa.Column("sld_project_settings_id", sa.String(length=36), primary_key=True),
            sa.Column("sizing_case_id", sa.String(length=36), nullable=False),
            sa.Column("settings_json", sa.JSON(), nullable=False),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("version_tag", sa.String(length=64), nullable=True),
            sa.Column("source_ref", sa.String(length=255), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("is_published", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["sizing_case_id"], ["sizing_case.sizing_case_id"], ondelete="CASCADE"),
            sa.UniqueConstraint("sizing_case_id"),
        )
        op.create_index("ix_sld_project_settings_sizing_case_id", "sld_project_settings", ["sizing_case_id"])
    _backfill_from_case_json()


def downgrade() -> None:
    if "sld_project_settings" in _tables():
        op.drop_index("ix_sld_project_settings_sizing_case_id", table_name="sld_project_settings")
        op.drop_table("sld_project_settings")
