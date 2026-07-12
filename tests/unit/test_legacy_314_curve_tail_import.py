from __future__ import annotations

from calb_sizing_tool.config import DC_DATA_PATH
from calb_sizing_tool.importers.excel_dictionary_importer import ExcelDictionaryImporter
from calb_sizing_tool.importers.import_validators import collect_dc_import_validation_issues
from calb_sizing_tool.infra.db.base import Base
from calb_sizing_tool.infra.db.models import RteCurveBand, SohCurvePoint
from calb_sizing_tool.infra.db.session import session_scope


def test_legacy_314_curve_tails_are_audited_and_never_coerced_to_zero(tmp_path):
    issues = collect_dc_import_validation_issues(DC_DATA_PATH)

    assert not [issue for issue in issues if issue.severity == "error"]
    assert len([issue for issue in issues if issue.severity == "warning"]) == 80

    db_url = f"sqlite:///{(tmp_path / 'legacy-314.sqlite').as_posix()}"
    with session_scope(db_url) as session:
        Base.metadata.create_all(bind=session.get_bind())

    with session_scope(db_url) as session:
        summary = ExcelDictionaryImporter(session).apply_import(
            DC_DATA_PATH,
            version_tag="legacy-314-tail-audit",
        )
        assert summary.applied
        assert next(item for item in summary.object_summaries if item.object_name == "soh_curve_point").source_row_count == 178
        assert next(item for item in summary.object_summaries if item.object_name == "rte_curve_band").source_row_count == 51
        assert session.query(SohCurvePoint).count() == 178
        assert session.query(RteCurveBand).count() == 51
        assert session.query(SohCurvePoint).filter(SohCurvePoint.soh_dc_pct == 0.0).count() == 0
        assert session.query(RteCurveBand).filter(RteCurveBand.rte_dc_pct == 0.0).count() == 0
