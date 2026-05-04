"""Shared UI utility functions for consistent CALB-branded components."""
from __future__ import annotations

from html import escape
from typing import Iterable

import streamlit as st


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
