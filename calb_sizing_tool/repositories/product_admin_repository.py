from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from calb_sizing_tool.infra.db.models import (
    DegradationCurve,
    DegradationPlugin,
    ProductACBlock,
    ProductAsset,
    ProductCell,
    ProductDCBlock,
    RTECurve,
)

_ENTITY_MODELS = {
    "cell": (ProductCell, "product_cell_id"),
    "dc_block": (ProductDCBlock, "product_dc_block_id"),
    "ac_block": (ProductACBlock, "product_ac_block_id"),
    "asset": (ProductAsset, "product_asset_id"),
    "degradation_curve": (DegradationCurve, "degradation_curve_id"),
    "rte_curve": (RTECurve, "rte_curve_id"),
    "plugin": (DegradationPlugin, "degradation_plugin_id"),
}


class ProductAdminRepository:
    def __init__(self, session: Session):
        self.session = session

    def counts(self) -> dict[str, int]:
        return {
            "product_cell": self.session.query(ProductCell).count(),
            "product_dc_block": self.session.query(ProductDCBlock).count(),
            "product_ac_block": self.session.query(ProductACBlock).count(),
            "product_asset": self.session.query(ProductAsset).count(),
            "degradation_curve": self.session.query(DegradationCurve).count(),
            "rte_curve": self.session.query(RTECurve).count(),
            "degradation_plugin": self.session.query(DegradationPlugin).count(),
        }

    def list_cells(self) -> list[ProductCell]:
        return self.session.query(ProductCell).order_by(ProductCell.cell_code.asc()).all()

    def list_dc_blocks(self) -> list[ProductDCBlock]:
        return self.session.query(ProductDCBlock).order_by(ProductDCBlock.block_code.asc()).all()

    def list_ac_blocks(self) -> list[ProductACBlock]:
        return self.session.query(ProductACBlock).order_by(ProductACBlock.block_code.asc()).all()

    def list_assets(self) -> list[ProductAsset]:
        return (
            self.session.query(ProductAsset)
            .order_by(ProductAsset.owner_entity.asc(), ProductAsset.owner_code.asc(), ProductAsset.sort_order.asc())
            .all()
        )

    def list_degradation_curves(self) -> list[DegradationCurve]:
        return self.session.query(DegradationCurve).order_by(DegradationCurve.curve_code.asc()).all()

    def list_rte_curves(self) -> list[RTECurve]:
        return self.session.query(RTECurve).order_by(RTECurve.curve_code.asc()).all()

    def list_plugins(self) -> list[DegradationPlugin]:
        return self.session.query(DegradationPlugin).order_by(DegradationPlugin.plugin_key.asc()).all()

    def create_cell(self, **values: Any) -> ProductCell:
        values.setdefault("metadata_json", {})
        values.setdefault("source_ref", "admin_portal")
        row = ProductCell(**values)
        self.session.add(row)
        self.session.flush()
        return row

    def create_dc_block(self, **values: Any) -> ProductDCBlock:
        values.setdefault("metadata_json", {})
        values.setdefault("source_ref", "admin_portal")
        row = ProductDCBlock(**values)
        self.session.add(row)
        self.session.flush()
        return row

    def create_ac_block(self, **values: Any) -> ProductACBlock:
        values.setdefault("efficiency_curve_json", {})
        values.setdefault("metadata_json", {})
        values.setdefault("source_ref", "admin_portal")
        row = ProductACBlock(**values)
        self.session.add(row)
        self.session.flush()
        return row

    def create_asset(self, **values: Any) -> ProductAsset:
        values.setdefault("data_json", {})
        values.setdefault("metadata_json", {})
        values.setdefault("source_ref", "admin_portal")
        row = ProductAsset(**values)
        self.session.add(row)
        self.session.flush()
        return row

    def create_degradation_curve(self, **values: Any) -> DegradationCurve:
        values.setdefault("cycle_points_json", [])
        values.setdefault("calendar_points_json", [])
        values.setdefault("metadata_json", {})
        values.setdefault("source_ref", "admin_portal")
        row = DegradationCurve(**values)
        self.session.add(row)
        self.session.flush()
        return row

    def create_rte_curve(self, **values: Any) -> RTECurve:
        values.setdefault("matrix_json", {})
        values.setdefault("metadata_json", {})
        values.setdefault("source_ref", "admin_portal")
        row = RTECurve(**values)
        self.session.add(row)
        self.session.flush()
        return row

    def create_plugin(self, **values: Any) -> DegradationPlugin:
        values.setdefault("schema_json", {})
        values.setdefault("metadata_json", {})
        values.setdefault("source_ref", "admin_portal")
        row = DegradationPlugin(**values)
        self.session.add(row)
        self.session.flush()
        return row

    def get_record(self, entity: str, record_id: str) -> Any | None:
        model, id_field = _ENTITY_MODELS[entity]
        return self.session.query(model).filter(getattr(model, id_field) == record_id).one_or_none()

    def update_record(self, entity: str, record_id: str, values: dict[str, Any]) -> Any | None:
        row = self.get_record(entity, record_id)
        if row is None:
            return None
        valid_columns = {column.name for column in row.__table__.columns}
        for key, value in values.items():
            if key in valid_columns:
                setattr(row, key, value)
        self.session.add(row)
        self.session.flush()
        return row
