"""Shared UI utility functions for consistent CALB-branded components."""
from __future__ import annotations

from html import escape

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
