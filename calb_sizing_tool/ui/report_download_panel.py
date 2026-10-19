"""Shared presentation for the existing direct technical proposal download."""
from __future__ import annotations

import streamlit as st

from calb_sizing_tool.ui._ui import section_header


def render_proposal_download(
    data: bytes,
    filename: str,
    *,
    template_name: str,
    alternative_label: str | None = None,
    key: str | None = None,
) -> None:
    """Display already prepared bytes without generating or changing a report."""
    st.markdown(
        """<style>
        .st-key-report_proposal_download_panel {
            border-left: 3px solid var(--calb-blue, #1E4172) !important;
        }
        .st-key-report_proposal_download_panel [data-testid="stDownloadButton"] button {
            background: var(--calb-blue, #1E4172) !important;
            border: 1px solid var(--calb-blue, #1E4172) !important;
            border-radius: 6px !important;
            color: #FFFFFF !important;
            font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif !important;
            font-size: 0.88rem !important;
            font-weight: 650 !important;
            min-height: 2.75rem !important;
            padding: 0.55rem 0.9rem !important;
        }
        .st-key-report_proposal_download_panel [data-testid="stDownloadButton"] button:hover {
            background: var(--calb-navy, #0E2240) !important;
            border-color: var(--calb-navy, #0E2240) !important;
        }
        </style>""",
        unsafe_allow_html=True,
    )
    with st.container(border=True, key="report_proposal_download_panel"):
        summary, action = st.columns([2.2, 1], gap="large", vertical_alignment="center")
        with summary:
            section_header(
                "Technical Proposal",
                "Sizing results and available engineering figures in one editable document.",
            )
            details = ["Word (.docx)", template_name]
            if alternative_label:
                details.append(f"AC Alternative {alternative_label}")
            st.caption(" · ".join(details))
        with action:
            st.download_button(
                "Download Technical Proposal",
                data,
                file_name=filename,
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                type="primary",
                icon=":material/download:",
                use_container_width=True,
                on_click="ignore",
                key=key,
            )
