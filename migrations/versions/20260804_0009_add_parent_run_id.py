"""Let a run hang off another run: sizing_run.parent_run_id.

Owner ruling B (2026-08-04): once a DC result is fixed, the AC side may carry
more than one alternative — a different DC Block match, a different SLD, a
different arrangement, and its own report version. That alternative is a CHILD of
the DC run, not another Case: a Case holds DC-side assumptions only
(SizingCaseInput has no AC field at all), so an AC branch does not duplicate it.

Self-referential and CASCADE: deleting a DC run takes its AC branches with it
rather than leaving them pointing at nothing.

This migration only opens the door. Nothing writes AC runs until the persistence
step lands, and existing rows keep parent_run_id NULL, which is exactly what a
top-level DC run means.

Revision ID: 20260804_0009
Revises: 20260804_0008
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260804_0009"
down_revision = "20260804_0008"
branch_labels = None
depends_on = None

_TABLE = "sizing_run"
_COLUMN = "parent_run_id"
_INDEX = "ix_sizing_run_parent_run_id"
_FK = "fk_sizing_run_parent_run_id_sizing_run"


def _has_column(bind) -> bool:
    return _COLUMN in {col["name"] for col in sa.inspect(bind).get_columns(_TABLE)}


def upgrade() -> None:
    bind = op.get_bind()
    if _has_column(bind):
        return
    # SQLite cannot add a foreign key with a plain ALTER; batch mode rebuilds.
    with op.batch_alter_table(_TABLE) as batch:
        batch.add_column(sa.Column(_COLUMN, sa.String(length=36), nullable=True))
        batch.create_foreign_key(
            _FK, _TABLE, [_COLUMN], ["sizing_run_id"], ondelete="CASCADE",
        )
    op.create_index(_INDEX, _TABLE, [_COLUMN], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    if not _has_column(bind):
        return
    indexes = {index["name"] for index in sa.inspect(bind).get_indexes(_TABLE)}
    if _INDEX in indexes:
        op.drop_index(_INDEX, table_name=_TABLE)
    with op.batch_alter_table(_TABLE) as batch:
        batch.drop_column(_COLUMN)
