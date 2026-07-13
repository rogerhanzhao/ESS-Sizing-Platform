"""Regression checks for UI table rendering after PyArrow crash containment."""
from __future__ import annotations

import ast
from pathlib import Path

import pandas as pd

from calb_sizing_tool.ui._ui import static_table_html


def test_static_table_html_escapes_headers_and_cell_values() -> None:
    html = static_table_html(pd.DataFrame({"<User>": ["<script>alert(1)</script>"]}))

    assert "&lt;User&gt;" in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "<script>" not in html


def test_no_streamlit_arrow_table_calls_remain_in_ui() -> None:
    ui_dir = Path("calb_sizing_tool/ui")
    violations: list[str] = []
    for source_path in ui_dir.rglob("*.py"):
        tree = ast.parse(source_path.read_text(encoding="utf-8-sig"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if (
                node.func.attr in {"dataframe", "table"}
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "st"
            ):
                violations.append(f"{source_path}:{node.lineno} st.{node.func.attr}")

    assert violations == []
