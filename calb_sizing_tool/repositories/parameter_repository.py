from __future__ import annotations

from sqlalchemy.orm import Session

from calb_sizing_tool.infra.db.models import ParameterDefinition, ParameterSet
from calb_sizing_tool.schemas.master_data import ParameterDefinitionSchema, ParameterSetSchema


class ParameterRepository:
    def __init__(self, session: Session):
        self.session = session

    def upsert_definitions(
        self,
        definitions: list[ParameterDefinitionSchema],
        *,
        version_tag: str | None = None,
        source_ref: str | None = None,
    ) -> list[ParameterDefinition]:
        persisted: list[ParameterDefinition] = []
        for item in definitions:
            row = self.session.query(ParameterDefinition).filter_by(field_code=item.field_code).one_or_none()
            payload = item.model_dump()
            payload["version_tag"] = version_tag
            payload["source_ref"] = source_ref
            if row is None:
                row = ParameterDefinition(**payload)
                self.session.add(row)
            else:
                for key, value in payload.items():
                    setattr(row, key, value)
            persisted.append(row)
        return persisted

    def create_parameter_set(self, schema: ParameterSetSchema, *, is_published: bool = False):
        row = ParameterSet(
            set_code=schema.set_code,
            set_name=schema.set_name,
            stage_scope=schema.stage_scope,
            parameter_values_json=schema.parameter_values,
            version_tag=schema.version_tag,
            source_ref=schema.source_ref,
            is_published=is_published,
        )
        self.session.add(row)
        return row

    def export_definition_snapshot(self) -> list[dict]:
        rows = self.session.query(ParameterDefinition).order_by(ParameterDefinition.field_code.asc()).all()
        return [
            {
                "field_code": row.field_code,
                "display_name_en": row.display_name_en,
                "display_name_zh": row.display_name_zh,
                "unit": row.unit,
                "data_type": row.data_type,
                "nullable": row.nullable,
                "required_for_stage": row.required_for_stage,
                "validation_rule": row.validation_rule,
                "source_sheet": row.source_sheet,
                "legacy_field_name": row.legacy_field_name,
                "remarks": row.remarks or "",
            }
            for row in rows
        ]
