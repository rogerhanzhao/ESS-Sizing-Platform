from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from calb_sizing_tool.infra.db.models import (
    BatteryCellType,
    DcBlockTemplate,
    PackType,
    RackType,
    RteCurveBand,
    RteProfile,
    SohCurvePoint,
    SohProfile,
)


class MasterDataRepository:
    def __init__(self, session: Session):
        self.session = session

    def replace_dc_master_data(self, payload: dict[str, list[dict[str, Any]]], *, version_tag: str, source_ref: str) -> dict[str, int]:
        self.session.query(RteCurveBand).delete()
        self.session.query(RteProfile).delete()
        self.session.query(SohCurvePoint).delete()
        self.session.query(SohProfile).delete()
        self.session.query(DcBlockTemplate).delete()
        self.session.query(RackType).delete()
        self.session.query(PackType).delete()
        self.session.query(BatteryCellType).delete()

        counts = {
            "battery_cell_type": 0,
            "pack_type": 0,
            "rack_type": 0,
            "dc_block_template": 0,
            "soh_profile": 0,
            "soh_curve_point": 0,
            "rte_profile": 0,
            "rte_curve_band": 0,
        }

        cell_id_map: dict[int, str] = {}
        pack_id_map: dict[int, str] = {}
        rack_id_map: dict[int, str] = {}
        soh_profile_map: dict[int, str] = {}
        rte_profile_map: dict[int, str] = {}

        for item in payload.get("battery_cell_type", []):
            record = dict(item)
            row = BatteryCellType(version_tag=version_tag, source_ref=source_ref, **record)
            self.session.add(row)
            self.session.flush()
            source_id = record.get("source_cell_type_id")
            if source_id is not None:
                cell_id_map[int(source_id)] = row.battery_cell_type_id
            counts["battery_cell_type"] += 1

        for item in payload.get("pack_type", []):
            record = dict(item)
            source_cell_type_id = record.pop("source_cell_type_id", None)
            row = PackType(
                battery_cell_type_id=cell_id_map.get(int(source_cell_type_id)) if source_cell_type_id is not None else None,
                version_tag=version_tag,
                source_ref=source_ref,
                **record,
            )
            self.session.add(row)
            self.session.flush()
            source_id = record.get("source_pack_type_id")
            if source_id is not None:
                pack_id_map[int(source_id)] = row.pack_type_id
            counts["pack_type"] += 1

        for item in payload.get("rack_type", []):
            record = dict(item)
            source_pack_type_id = record.pop("source_pack_type_id", None)
            row = RackType(
                pack_type_id=pack_id_map.get(int(source_pack_type_id)) if source_pack_type_id is not None else None,
                version_tag=version_tag,
                source_ref=source_ref,
                **record,
            )
            self.session.add(row)
            self.session.flush()
            source_id = record.get("source_rack_type_id")
            if source_id is not None:
                rack_id_map[int(source_id)] = row.rack_type_id
            counts["rack_type"] += 1

        for item in payload.get("dc_block_template", []):
            record = dict(item)
            source_rack_type_id = record.pop("source_rack_type_id", None)
            row = DcBlockTemplate(
                rack_type_id=rack_id_map.get(int(source_rack_type_id)) if source_rack_type_id is not None else None,
                version_tag=version_tag,
                source_ref=source_ref,
                **record,
            )
            self.session.add(row)
            counts["dc_block_template"] += 1

        for item in payload.get("soh_profile", []):
            record = dict(item)
            source_cell_type_id = record.pop("source_cell_type_id", None)
            row = SohProfile(
                battery_cell_type_id=cell_id_map.get(int(source_cell_type_id)) if source_cell_type_id is not None else None,
                version_tag=version_tag,
                source_ref=source_ref,
                **record,
            )
            self.session.add(row)
            self.session.flush()
            source_id = record.get("source_profile_id")
            if source_id is not None:
                soh_profile_map[int(source_id)] = row.soh_profile_id
            counts["soh_profile"] += 1

        for item in payload.get("soh_curve_point", []):
            record = dict(item)
            source_profile_id = record.pop("source_profile_id", None)
            row = SohCurvePoint(
                soh_profile_id=soh_profile_map[int(source_profile_id)],
                version_tag=version_tag,
                source_ref=source_ref,
                **record,
            )
            self.session.add(row)
            counts["soh_curve_point"] += 1

        for item in payload.get("rte_profile", []):
            record = dict(item)
            source_cell_type_id = record.pop("source_cell_type_id", None)
            row = RteProfile(
                battery_cell_type_id=cell_id_map.get(int(source_cell_type_id)) if source_cell_type_id is not None else None,
                version_tag=version_tag,
                source_ref=source_ref,
                **record,
            )
            self.session.add(row)
            self.session.flush()
            source_id = record.get("source_profile_id")
            if source_id is not None:
                rte_profile_map[int(source_id)] = row.rte_profile_id
            counts["rte_profile"] += 1

        for item in payload.get("rte_curve_band", []):
            record = dict(item)
            source_profile_id = record.pop("source_profile_id", None)
            row = RteCurveBand(
                rte_profile_id=rte_profile_map[int(source_profile_id)],
                version_tag=version_tag,
                source_ref=source_ref,
                **record,
            )
            self.session.add(row)
            counts["rte_curve_band"] += 1

        return counts

    def export_dc_master_data_snapshot(self) -> dict[str, list[dict[str, Any]]]:
        cell_map = {
            row.battery_cell_type_id: row.source_cell_type_id
            for row in self.session.query(BatteryCellType).all()
        }
        pack_map = {
            row.pack_type_id: row.source_pack_type_id
            for row in self.session.query(PackType).all()
        }
        rack_map = {
            row.rack_type_id: row.source_rack_type_id
            for row in self.session.query(RackType).all()
        }
        soh_profile_map = {
            row.soh_profile_id: row.source_profile_id
            for row in self.session.query(SohProfile).all()
        }
        rte_profile_map = {
            row.rte_profile_id: row.source_profile_id
            for row in self.session.query(RteProfile).all()
        }

        return {
            "battery_cell_type": [
                {
                    "source_cell_type_id": row.source_cell_type_id,
                    "cell_model": row.cell_model,
                    "chemistry_code": row.chemistry_code,
                    "cell_capacity_ah": row.cell_capacity_ah,
                    "cell_nominal_voltage_v": row.cell_nominal_voltage_v,
                    "cell_energy_wh": row.cell_energy_wh,
                    "is_active": row.is_active,
                    "raw_row_json": row.raw_row_json,
                }
                for row in self.session.query(BatteryCellType).order_by(BatteryCellType.source_cell_type_id.asc()).all()
            ],
            "pack_type": [
                {
                    "source_pack_type_id": row.source_pack_type_id,
                    "source_cell_type_id": cell_map.get(row.battery_cell_type_id),
                    "pack_model": row.pack_model,
                    "cells_in_series": row.cells_in_series,
                    "cells_in_parallel": row.cells_in_parallel,
                    "pack_nominal_voltage_v": row.pack_nominal_voltage_v,
                    "pack_nameplate_capacity_kwh": row.pack_nameplate_capacity_kwh,
                    "is_active": row.is_active,
                    "raw_row_json": row.raw_row_json,
                }
                for row in self.session.query(PackType).order_by(PackType.source_pack_type_id.asc()).all()
            ],
            "rack_type": [
                {
                    "source_rack_type_id": row.source_rack_type_id,
                    "source_pack_type_id": pack_map.get(row.pack_type_id),
                    "rack_model": row.rack_model,
                    "packs_per_rack": row.packs_per_rack,
                    "rack_nameplate_capacity_mwh": row.rack_nameplate_capacity_mwh,
                    "rack_aux_energy_kwh": row.rack_aux_energy_kwh,
                    "is_active": row.is_active,
                    "raw_row_json": row.raw_row_json,
                }
                for row in self.session.query(RackType).order_by(RackType.source_rack_type_id.asc()).all()
            ],
            "dc_block_template": [
                {
                    "source_dc_block_template_id": row.source_dc_block_template_id,
                    "source_rack_type_id": rack_map.get(row.rack_type_id),
                    "dc_block_code": row.dc_block_code,
                    "dc_block_name": row.dc_block_name,
                    "block_form": row.block_form,
                    "container_length_ft": row.container_length_ft,
                    "racks_per_block": row.racks_per_block,
                    "packs_per_block": row.packs_per_block,
                    "block_nameplate_capacity_mwh": row.block_nameplate_capacity_mwh,
                    "block_aux_energy_kwh": row.block_aux_energy_kwh,
                    "design_max_c_rate": row.design_max_c_rate,
                    "is_active": row.is_active,
                    "raw_row_json": row.raw_row_json,
                }
                for row in self.session.query(DcBlockTemplate).order_by(DcBlockTemplate.source_dc_block_template_id.asc()).all()
            ],
            "soh_profile": [
                {
                    "source_profile_id": row.source_profile_id,
                    "source_cell_type_id": cell_map.get(row.battery_cell_type_id),
                    "profile_name": row.profile_name,
                    "cycles_per_year": row.cycles_per_year,
                    "c_rate": row.c_rate,
                    "reference_temperature_c": row.reference_temperature_c,
                    "raw_row_json": row.raw_row_json,
                }
                for row in self.session.query(SohProfile).order_by(SohProfile.source_profile_id.asc()).all()
            ],
            "soh_curve_point": [
                {
                    "source_profile_id": soh_profile_map.get(row.soh_profile_id),
                    "life_year_index": row.life_year_index,
                    "cycle_index": row.cycle_index,
                    "soh_dc_pct": row.soh_dc_pct,
                }
                for row in self.session.query(SohCurvePoint).order_by(SohCurvePoint.life_year_index.asc()).all()
            ],
            "rte_profile": [
                {
                    "source_profile_id": row.source_profile_id,
                    "source_cell_type_id": cell_map.get(row.battery_cell_type_id),
                    "profile_name": row.profile_name,
                    "cycles_per_year": row.cycles_per_year,
                    "c_rate": row.c_rate,
                    "raw_row_json": row.raw_row_json,
                }
                for row in self.session.query(RteProfile).order_by(RteProfile.source_profile_id.asc()).all()
            ],
            "rte_curve_band": [
                {
                    "source_profile_id": rte_profile_map.get(row.rte_profile_id),
                    "soh_band_min_pct": row.soh_band_min_pct,
                    "soh_band_max_pct": row.soh_band_max_pct,
                    "rte_dc_pct": row.rte_dc_pct,
                }
                for row in self.session.query(RteCurveBand).order_by(RteCurveBand.soh_band_min_pct.asc()).all()
            ],
        }
