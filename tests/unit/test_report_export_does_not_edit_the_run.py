"""Exporting a report must not change the sizing result it is reporting on.

`_docx_add_lifetime_table` fills any missing Stage 3 column with NaN so the
table always has its seven columns. It used to do that on the caller's frame.

The frame it is handed is not a scratch copy: `dc_view.show()` stores the very
same object in `dc_results["results_dict"]` (and `export_docx` re-reads it from
the run bundle), so an export could add columns to the Stage 3 result the page
is displaying. Today all seven columns exist on a real run, which is why this
never showed up as a wrong number — it was a live frame being written to on a
path that only had to read.
"""
from __future__ import annotations

import pandas as pd
import pytest

docx = pytest.importorskip("docx")

from calb_sizing_tool.ui import dc_view


def _partial_stage3() -> pd.DataFrame:
    """A Stage 3 frame missing most of the report's columns."""
    return pd.DataFrame({"Year_Index": [0, 1], "DC_Usable_MWh": [10.0, 9.5]})


def test_the_lifetime_table_leaves_the_callers_frame_alone():
    df = _partial_stage3()
    before = list(df.columns)

    dc_view._docx_add_lifetime_table(docx.Document(), df)

    assert list(df.columns) == before, (
        "the export added placeholder columns to the caller's Stage 3 result"
    )


def test_the_table_is_still_written_in_full():
    """The copy must not cost the behaviour the fill-in was there for."""
    doc = docx.Document()
    dc_view._docx_add_lifetime_table(doc, _partial_stage3())

    table = doc.tables[-1]
    assert len(table.columns) == 7
    assert len(table.rows) == 3                      # header + 2 years
    assert table.rows[0].cells[0].text == "Year (From COD)"
    assert table.rows[1].cells[0].text == "0"
    assert table.rows[1].cells[3].text == "10.00"    # the column that was present
    assert table.rows[1].cells[1].text == ""         # the ones that were not
