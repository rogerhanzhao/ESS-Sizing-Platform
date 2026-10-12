"""Immutable source versions, isolated from the active sizing SOH tables."""
from sqlalchemy import CheckConstraint, JSON, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column

from calb_sizing_tool.infra.db.base import Base, TimestampMixin, new_uuid


class SupplierDegradationImport(Base, TimestampMixin):
    __tablename__ = "supplier_degradation_import"
    __table_args__ = (CheckConstraint("status = 'candidate'", name="candidate_only"),)

    import_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    source_sha256: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    version_label: Mapped[str] = mapped_column(String(128), nullable=False)
    actor: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="candidate", nullable=False)
    source_bytes: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    dataset_json: Mapped[dict] = mapped_column(JSON, nullable=False)
