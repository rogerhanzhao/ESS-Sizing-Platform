from __future__ import annotations

import pandas as pd
import pyarrow as pa

from calb_sizing_tool.common.arrow_safe import arrow_safe


def test_arrow_safe_stringifies_mixed_object_columns_without_mutating_source() -> None:
    source = pd.DataFrame(
        {
            "mixed": ["ready", 3, None],
            "numeric": [1.0, 2.0, 3.0],
            "active": [True, False, True],
        }
    )

    safe = arrow_safe(source)

    assert safe is not source
    assert safe["mixed"].tolist() == ["ready", "3", ""]
    assert safe["numeric"].tolist() == [1.0, 2.0, 3.0]
    assert safe["active"].tolist() == [True, False, True]
    assert source["mixed"].tolist() == ["ready", 3, None]


def test_arrow_safe_normalises_row_records_before_stringifying_mixed_values() -> None:
    safe = arrow_safe([{"status": "ready"}, {"status": 3}, {"status": None}])

    assert isinstance(safe, pd.DataFrame)
    assert safe["status"].tolist() == ["ready", "3", ""]


def test_arrow_safe_output_serialises_with_pyarrow() -> None:
    safe = arrow_safe(pd.DataFrame({"mixed": ["ready", 3, None]}))

    table = pa.Table.from_pandas(safe, preserve_index=False)

    assert table.schema.field("mixed").type == pa.string()
    assert table.column("mixed").to_pylist() == ["ready", "3", ""]


def test_arrow_safe_leaves_non_tabular_values_untouched() -> None:
    marker = object()

    assert arrow_safe(marker) is marker
