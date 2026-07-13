"""Make DataFrames safe for Streamlit's Arrow serialisation.

`st.dataframe`/`st.table` serialise via pyarrow, whose C code can hard-crash
(SIGSEGV, no Python exception) on mixed-type ``object`` columns instead of
raising. That kills the whole process and logs every user out. Coercing object
columns to strings yields Arrow-safe input while leaving numeric/bool/datetime
columns (already Arrow-safe) untouched.
"""
from __future__ import annotations

from typing import Any


def arrow_safe(data: Any) -> Any:
    """Return an Arrow-serialisable version of ``data``.

    Lists, tuples, and dictionaries are first normalised to a DataFrame, as
    Streamlit accepts those values directly and sends them to the same Arrow
    serializer. Other values (for example ``Styler`` and ``None``) pass
    through unchanged.
    """
    try:
        import pandas as pd
    except Exception:
        return data
    if isinstance(data, (list, tuple, dict)):
        try:
            data = pd.DataFrame(data)
        except Exception:
            return data
    if not isinstance(data, pd.DataFrame):
        return data
    out = data.copy()
    for col in out.columns:
        if out[col].dtype == object:
            out[col] = out[col].map(lambda v: "" if v is None else str(v))
    return out
