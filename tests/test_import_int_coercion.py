"""Bulk import must coerce spreadsheet-style integer strings ("10000.0").

pandas read_excel(dtype=str) can yield "2024.0" for integer cells; the old
int("2024.0") raised ValueError and silently dropped the value to None.
"""
import pandas as pd

from calb_sizing_tool.infra.db.base import Base
from calb_sizing_tool.infra.db.session import create_engine_for_url
from calb_sizing_tool.services.product_admin_service import ProductAdminService


def test_import_coerces_spreadsheet_style_int_floats(tmp_path):
    db_url = f"sqlite:///{(tmp_path / 'imp.sqlite').as_posix()}"
    Base.metadata.create_all(bind=create_engine_for_url(db_url))
    service = ProductAdminService(db_url)

    df = pd.DataFrame(
        [
            {
                "cell_code": "C1",
                "model_name": "M1",
                "chemistry": "LFP",
                "cycle_life_cycles": "10000.0",
                "launch_year": "2024.0",
            }
        ]
    )
    result = service.import_records_from_df("cell", df)
    assert result["imported"] == 1, result
    assert result["skipped"] == 0

    cell = service.snapshot()["cells"][0]
    assert cell["cycle_life_cycles"] == 10000
    assert cell["launch_year"] == 2024


def test_import_non_numeric_int_still_becomes_none(tmp_path):
    db_url = f"sqlite:///{(tmp_path / 'imp2.sqlite').as_posix()}"
    Base.metadata.create_all(bind=create_engine_for_url(db_url))
    service = ProductAdminService(db_url)

    df = pd.DataFrame(
        [{"cell_code": "C2", "model_name": "M2", "chemistry": "LFP", "launch_year": "n/a"}]
    )
    result = service.import_records_from_df("cell", df)
    assert result["imported"] == 1, result
    assert service.snapshot()["cells"][0]["launch_year"] is None
