"""Immutable runtime curve packages; supplier originals remain candidates."""
from sqlalchemy import JSON, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from calb_sizing_tool.infra.db.base import Base, TimestampMixin, new_uuid


class CurveRelease(Base, TimestampMixin):
    __tablename__ = 'curve_release'
    release_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    version_label: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    source_import_id: Mapped[str] = mapped_column(ForeignKey('supplier_degradation_import.import_id'), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default='published', nullable=False)
    payload_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    review_note: Mapped[str] = mapped_column(Text, nullable=False)
    actor: Mapped[str] = mapped_column(String(128), nullable=False)


class CurveDefaultBinding(Base, TimestampMixin):
    __tablename__ = 'curve_default_binding'
    scope_key: Mapped[str] = mapped_column(String(128), primary_key=True)
    release_id: Mapped[str] = mapped_column(ForeignKey('curve_release.release_id'), nullable=False)
    family_key: Mapped[str] = mapped_column(String(128), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
