from __future__ import annotations

from calb_sizing_tool.importers.excel_dictionary_importer import ExcelDictionaryImporter
from calb_sizing_tool.infra.db.base import Base
from calb_sizing_tool.infra.db.models import (
    BatteryCellType,
    DcBlockTemplate,
    PackType,
    ParameterDefinition,
    RackType,
    RteCurveBand,
    RteProfile,
    SohCurvePoint,
    SohProfile,
)
from calb_sizing_tool.infra.db.session import session_scope


def _count_master_tables(session) -> dict[str, int]:
    return {
        "parameter_definition": session.query(ParameterDefinition).count(),
        "battery_cell_type": session.query(BatteryCellType).count(),
        "pack_type": session.query(PackType).count(),
        "rack_type": session.query(RackType).count(),
        "dc_block_template": session.query(DcBlockTemplate).count(),
        "soh_profile": session.query(SohProfile).count(),
        "soh_curve_point": session.query(SohCurvePoint).count(),
        "rte_profile": session.query(RteProfile).count(),
        "rte_curve_band": session.query(RteCurveBand).count(),
    }


def test_excel_importer_modes_and_idempotency(sample_excel_path, tmp_path):
    db_url = f"sqlite:///{(tmp_path / 'importer-modes.sqlite').as_posix()}"

    with session_scope(db_url) as session:
        Base.metadata.create_all(bind=session.get_bind())
        importer = ExcelDictionaryImporter(session)

        dry_summary = importer.dry_run(sample_excel_path, version_tag="sample-v1")
        preview_summary = importer.preview_diff(sample_excel_path, version_tag="sample-v1")
        session.flush()
        counts_after_preview = _count_master_tables(session)

        assert not dry_summary.applied
        assert not preview_summary.applied
        assert all(value == 0 for value in counts_after_preview.values())

        apply_summary = importer.apply_import(sample_excel_path, version_tag="sample-v1")
        session.flush()
        counts_after_apply = _count_master_tables(session)

        assert apply_summary.applied
        for summary in apply_summary.object_summaries:
            if summary.object_name in counts_after_apply:
                assert counts_after_apply[summary.object_name] == summary.source_row_count

        apply_summary_repeat = importer.apply_import(sample_excel_path, version_tag="sample-v1")
        session.flush()
        counts_after_repeat = _count_master_tables(session)

        assert apply_summary_repeat.applied
        assert counts_after_repeat == counts_after_apply
        assert set(dry_summary.model_dump().keys()) == set(apply_summary.model_dump().keys())
