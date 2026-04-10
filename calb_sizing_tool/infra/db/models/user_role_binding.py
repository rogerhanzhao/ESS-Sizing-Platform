from __future__ import annotations

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from calb_sizing_tool.infra.db.base import Base, SourceVersionMixin, TimestampMixin, new_uuid


class UserRoleBinding(Base, TimestampMixin, SourceVersionMixin):
    __tablename__ = "user_role_binding"
    __table_args__ = (UniqueConstraint("user_id", "role_id"),)

    user_role_binding_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("user_account.user_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("role_definition.role_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
