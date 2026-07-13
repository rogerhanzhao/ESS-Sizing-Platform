"""Shared UI utility functions for consistent CALB-branded components."""
from __future__ import annotations

from html import escape
from typing import Any, Iterable

import pandas as pd
import streamlit as st

from calb_sizing_tool.state.workspace_state import navigate_now


_PIPELINE_NEXT_STEPS: dict[str, tuple[tuple[str, str], ...]] = {
    "AC Sizing": (
        ("Single Line Diagram →", "Single Line Diagram"),
        ("Typical AC Block Arrangement →", "Typical AC Block Arrangement"),
        ("Report Export →", "Report Export"),
    ),
    "Single Line Diagram": (
        ("Typical AC Block Arrangement →", "Typical AC Block Arrangement"),
        ("Report Export →", "Report Export"),
    ),
    "Typical AC Block Arrangement": (
        ("Report Export →", "Report Export"),
    ),
}


def page_header(title: str, subtitle: str = "") -> None:
    """Render a CALB-branded page header with optional subtitle.

    Relies on the .calb-ph / .calb-ph-title / .calb-ph-sub CSS classes
    injected by ui._styles.inject_global_styles().
    """
    sub_html = (
        f'<p class="calb-ph-sub">{escape(subtitle)}</p>' if subtitle else ""
    )
    st.markdown(
        f'<div class="calb-ph">'
        f'<p class="calb-ph-title">{escape(title)}</p>'
        f"{sub_html}"
        f"</div>",
        unsafe_allow_html=True,
    )


def section_header(title: str, caption: str = "", eyebrow: str = "") -> None:
    """Render a compact section heading for dense engineering screens."""
    eyebrow_html = (
        f'<span class="calb-section-eyebrow">{escape(eyebrow)}</span>' if eyebrow else ""
    )
    caption_html = (
        f'<p class="calb-section-caption">{escape(caption)}</p>' if caption else ""
    )
    st.markdown(
        f'<div class="calb-section-header">'
        f'{eyebrow_html}'
        f'<span class="calb-section-title">{escape(title)}</span>'
        f'{caption_html}'
        f'</div>',
        unsafe_allow_html=True,
    )


def workspace_status_bar(items: Iterable[tuple[str, object]]) -> None:
    """Render a compact label/value workspace status strip."""
    cells: list[str] = []
    for label, value in items:
        value_text = "None" if value in (None, "") else str(value)
        cells.append(
            '<div class="calb-status-cell">'
            f'<span class="calb-status-label">{escape(str(label))}</span>'
            f'<span class="calb-status-value">{escape(value_text)}</span>'
            '</div>'
        )
    st.markdown(
        f'<div class="calb-status-bar">{"".join(cells)}</div>',
        unsafe_allow_html=True,
    )


def compact_note(text: str) -> None:
    """Render a low-height informational note."""
    st.markdown(
        f'<div class="calb-note">{escape(text)}</div>',
        unsafe_allow_html=True,
    )


def static_table_html(data: Any) -> str:
    """Return escaped HTML for a non-Arrow static table.

    Streamlit's dataframe and table elements serialize through PyArrow.  The
    production runtime has shown native PyArrow crashes during that conversion,
    which restarts Streamlit and loses the authenticated session.  This helper
    intentionally uses Markdown/HTML only; it is for read-only display tables,
    not editable or sortable grids.
    """
    if isinstance(data, pd.DataFrame):
        frame = data
    elif isinstance(data, dict):
        frame = pd.DataFrame([data])
    else:
        frame = pd.DataFrame(data)

    headers = [escape(str(column)) for column in frame.columns]
    header_html = "".join(
        '<th style="text-align:left; padding:0.45rem 0.65rem; '
        'border-bottom:1px solid #c8d4e3; background:#edf3fa; '
        'white-space:nowrap;">'
        f"{header}</th>"
        for header in headers
    )

    rows_html: list[str] = []
    for row in frame.itertuples(index=False, name=None):
        cells: list[str] = []
        for value in row:
            try:
                is_missing = bool(pd.isna(value))
            except (TypeError, ValueError):
                is_missing = False
            text = "" if is_missing else str(value)
            cells.append(
                '<td style="padding:0.4rem 0.65rem; border-bottom:1px solid #e1e8f0; '
                'vertical-align:top;">'
                f"{escape(text)}</td>"
            )
        rows_html.append(f"<tr>{''.join(cells)}</tr>")

    if not headers:
        return '<div class="calb-static-table-empty">No columns to display.</div>'

    return (
        '<div class="calb-static-table" style="overflow-x:auto;">'
        '<table style="width:100%; border-collapse:collapse; font-size:0.9rem;">'
        f'<thead><tr>{header_html}</tr></thead>'
        f'<tbody>{"".join(rows_html)}</tbody>'
        '</table></div>'
    )


def render_static_table(data: Any) -> None:
    """Render a read-only table without Streamlit's PyArrow serialization."""
    st.markdown(static_table_html(data), unsafe_allow_html=True)


def render_pipeline_next_steps(current_page: str, *, is_guest: bool) -> None:
    """Keep the sizing-to-proposal workflow visible on every output page."""
    actions = [
        (label, destination)
        for label, destination in _PIPELINE_NEXT_STEPS.get(current_page, ())
        if not (is_guest and destination == "Report Export")
    ]
    if not actions:
        return

    st.markdown('<div class="calb-muted-line"></div>', unsafe_allow_html=True)
    section_header("Next Steps", eyebrow="Continue")
    columns = st.columns(len(actions))
    for index, ((label, destination), column) in enumerate(zip(actions, columns)):
        if column.button(
            label,
            use_container_width=True,
            key=f"pipeline_next_{current_page}_{index}",
        ):
            navigate_now(destination)
