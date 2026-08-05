"""Scope sizing_case.case_code uniqueness to its project.

A Case is 方案 x scenario WITHIN one project (owner ruling 2026-08-04). Its
identity is therefore (project_id, case_code), not case_code alone.

The old schema made case_code GLOBALLY unique while
CaseRepository.create_case_if_needed looked it up per project. The two disagreed,
so two reachable situations raised a raw IntegrityError instead of resolving:

- a second project reusing a case code;
- the same code created under a different scenario (the lookup included
  scenario_mode, missed the existing row, then collided on insert).

Existing data: codes are generated as "{project_code}-{slug}", so real rows are
already project-unique and this migration only widens what is allowed. Should a
database somehow hold a duplicate (project_id, case_code) pair, the upgrade
fails loudly on the new constraint rather than silently dropping a Case.

Downgrade restores the global unique index. It will fail if the data has since
taken advantage of per-project reuse — which is the correct outcome, not a
reason to discard rows.

Revision ID: 20260804_0008
Revises: 20260617_0007
"""

from __future__ import annotations

from alembic import op

revision = "20260804_0008"
down_revision = "20260617_0007"
branch_labels = None
depends_on = None

_TABLE = "sizing_case"
_COMPOSITE = "uq_sizing_case_project_code"


def _existing_index_names(bind) -> set[str]:
    from sqlalchemy import inspect

    inspector = inspect(bind)
    return {index["name"] for index in inspector.get_indexes(_TABLE) if index.get("name")}


def _existing_unique_constraint_names(bind) -> set[str]:
    from sqlalchemy import inspect

    inspector = inspect(bind)
    try:
        return {uq["name"] for uq in inspector.get_unique_constraints(_TABLE) if uq.get("name")}
    except NotImplementedError:
        return set()


def upgrade() -> None:
    bind = op.get_bind()
    indexes = _existing_index_names(bind)
    uniques = _existing_unique_constraint_names(bind)

    # SQLite cannot ALTER a constraint in place; batch mode rebuilds the table.
    with op.batch_alter_table(_TABLE) as batch:
        # The old declaration produced a UNIQUE index named ix_sizing_case_case_code
        # (SQLAlchemy emits one index for unique=True + index=True). Drop whichever
        # form this database actually has.
        if "ix_sizing_case_case_code" in indexes:
            batch.drop_index("ix_sizing_case_case_code")
        for name in ("uq_sizing_case_case_code", "sizing_case_case_code_key"):
            if name in uniques:
                batch.drop_constraint(name, type_="unique")
        batch.create_unique_constraint(_COMPOSITE, ["project_id", "case_code"])

    # Keep the plain (non-unique) lookup index the model still declares.
    if "ix_sizing_case_case_code" not in _existing_index_names(bind):
        op.create_index("ix_sizing_case_case_code", _TABLE, ["case_code"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    indexes = _existing_index_names(bind)
    uniques = _existing_unique_constraint_names(bind)

    with op.batch_alter_table(_TABLE) as batch:
        if _COMPOSITE in uniques:
            batch.drop_constraint(_COMPOSITE, type_="unique")
        if "ix_sizing_case_case_code" in indexes:
            batch.drop_index("ix_sizing_case_case_code")
        batch.create_index("ix_sizing_case_case_code", ["case_code"], unique=True)
