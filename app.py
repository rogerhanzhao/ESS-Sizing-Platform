# -----------------------------------------------------------------------------
# Personal Open-Source Notice
#
# Copyright (c) 2026 Alex.Zhao. All rights reserved.
#
# This repository is released under the MIT License (see LICENSE file).
# Intended use: learning, evaluation, and engineering reference for Utility-scale
# BESS/ESS sizing and Reporting workflows.
#
# DISCLAIMER: This software is provided "AS IS", without warranty of any kind,
# express or implied. In no event shall the author(s) be liable for any claim,
# damages, or other liability arising from, out of, or in connection with the
# software or the use or other dealings in the software.
#
# NOTE: This is a personal project. It is not an official product or statement
# of any company or organization.
# -----------------------------------------------------------------------------

from pathlib import Path

import streamlit as st

import calb_sizing_tool.config as config  # noqa: F401
from calb_sizing_tool.infra.db.base import Base
from calb_sizing_tool.infra.db.session import session_scope
from calb_sizing_tool.state.auth_state import clear_auth_context, get_auth_context
from calb_sizing_tool.state.workspace_state import apply_pending_navigation, get_workspace_context
from calb_sizing_tool.ui.login_view import show as show_login


st.set_page_config(
    page_title="CALB ESS SIZING PLATFORM",
    layout="wide",
    page_icon="⚡",
)

# ── CALB VI global styles ─────────────────────────────────────────────────────
st.markdown(
    """
    <style>
    /* ── Sidebar: CALB dark navy ──────────────────────────────────────── */
    section[data-testid="stSidebar"] {
        background-color: #0E2240 !important;
    }
    section[data-testid="stSidebar"] p,
    section[data-testid="stSidebar"] span,
    section[data-testid="stSidebar"] label,
    section[data-testid="stSidebar"] .stMarkdown,
    section[data-testid="stSidebar"] .stCaption > *  {
        color: #B8CADE !important;
    }
    section[data-testid="stSidebar"] h1,
    section[data-testid="stSidebar"] h2,
    section[data-testid="stSidebar"] h3 {
        color: #FFFFFF !important;
    }
    section[data-testid="stSidebar"] hr {
        border-color: #1E3A5C !important;
        margin: 0.5rem 0;
    }
    /* Sidebar radio: current page highlight */
    section[data-testid="stSidebar"] [data-baseweb="radio"] div[aria-checked="true"] ~ div {
        color: #FFFFFF !important;
        font-weight: 600;
    }
    /* Sidebar logout button */
    section[data-testid="stSidebar"] .stButton > button {
        background-color: #1E3A5C;
        color: #B8CADE;
        border: 1px solid #2A4F7A;
        border-radius: 4px;
    }
    section[data-testid="stSidebar"] .stButton > button:hover {
        background-color: #1E4172;
        color: #FFFFFF;
    }

    /* ── Main content: header spacing ─────────────────────────────────── */
    .block-container {
        padding-top: 1.5rem !important;
        padding-bottom: 2rem !important;
    }

    /* ── Metric cards: tighter, branded ───────────────────────────────── */
    [data-testid="stMetric"] {
        background-color: #EDF1F7;
        border-left: 3px solid #1E4172;
        border-radius: 4px;
        padding: 0.6rem 0.8rem !important;
    }
    [data-testid="stMetricLabel"] > div {
        font-size: 0.72rem !important;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        color: #3A5A80 !important;
    }
    [data-testid="stMetricValue"] > div {
        font-size: 1.1rem !important;
        font-weight: 700;
        color: #1A2635 !important;
    }

    /* ── Dividers ──────────────────────────────────────────────────────── */
    hr {
        border-color: #D0DAE8 !important;
    }

    /* ── Subheader: CALB blue left border ─────────────────────────────── */
    h2, h3 {
        color: #1A2635 !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── DB schema (once at startup) ───────────────────────────────────────────────
with session_scope() as _s:
    Base.metadata.create_all(bind=_s.get_bind())

auth_context = get_auth_context()
if auth_context is None:
    show_login()
    st.stop()

NAV_OPTIONS = [
    "Workbench",
    "DC Sizing",
    "AC Sizing",
    "Single Line Diagram",
    "Site Layout",
    "Report Export",
    "Project Directory",
    "Case Directory",
    "Run Registry",
]
apply_pending_navigation(NAV_OPTIONS, default_page="Workbench")

with st.sidebar:
    logo_path = Path("calb_logo.png")
    if logo_path.exists():
        st.image(str(logo_path), width=180)
    else:
        st.markdown("## CALB ESS")

    st.markdown("---")
    display_name = auth_context.display_name or auth_context.username
    st.caption(f"Signed in as  **{display_name}**")
    st.caption("🔑 Admin" if auth_context.is_admin else "👤 User")
    if st.button("Logout", use_container_width=True):
        clear_auth_context()
        st.rerun()

    workspace_context = get_workspace_context()
    st.markdown("---")
    st.caption("WORKSPACE")
    st.caption(f"Project: {workspace_context.get('project_name') or '—'}")
    st.caption(f"Case:    {workspace_context.get('case_name') or '—'}")
    _run_id = workspace_context.get("run_id")
    _run_short = f"··{_run_id[-8:]}" if _run_id and len(_run_id) >= 8 else (_run_id or "—")
    st.caption(f"Run:     {_run_short}")

    st.markdown("---")
    st.caption("NAVIGATION")
    nav = st.radio(
        "Go to",
        NAV_OPTIONS,
        key="main_nav",
        label_visibility="collapsed",
    )

    st.markdown("---")
    st.caption("v2.1 · CALB ESS Sizing Platform")

if nav == "Workbench":
    from calb_sizing_tool.ui.workbench_view import show
    show()

elif nav == "Project Directory":
    from calb_sizing_tool.ui.projects_view import show
    show()

elif nav == "Case Directory":
    from calb_sizing_tool.ui.cases_view import show
    show()

elif nav == "Run Registry":
    from calb_sizing_tool.ui.run_history_view import show
    show()

elif nav == "DC Sizing":
    from calb_sizing_tool.ui.dc_view import show
    show()

elif nav == "AC Sizing":
    from calb_sizing_tool.ui.ac_view import show
    show()

elif nav == "Single Line Diagram":
    from calb_sizing_tool.ui.single_line_diagram_view import show
    show()

elif nav == "Site Layout":
    from calb_sizing_tool.ui.site_layout_view import show
    show()

elif nav == "Report Export":
    from calb_sizing_tool.ui.report_export_view import show
    show()
