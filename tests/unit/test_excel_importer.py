from __future__ import annotations

from calb_sizing_tool.importers.excel_dictionary_importer import ExcelDictionaryImporter
from calb_sizing_tool.infra.db.base import Base
from calb_sizing_tool.infra.db.session import session_scope
import calb_sizing_tool.infra.db.models  # noqa: F401


def test_excel_importer_preview_and_import(sample_excel_path, tmp_path):
    db_url = f"sqlite:///{(tmp_path / 'importer.sqlite').as_posix()}"

    with session_scope(db_url) as session:
        Base.metadata.create_all(bind=session.get_bind())
        importer = ExcelDictionaryImporter(session)
        preview = importer.preview(sample_excel_path)
        counts = importer.import_dc_dictionary(sample_excel_path, version_tag="sample-v1")

    assert preview.workbook_name == "dc_dictionary_minimal.xlsx"
    assert preview.row_counts["dc_block_template_314_data"] == 2
    assert counts["battery_cell_type"] == 1
    assert counts["dc_block_template"] == 2
    assert counts["soh_curve_point"] == 2
