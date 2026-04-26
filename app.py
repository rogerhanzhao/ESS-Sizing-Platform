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
from calb_sizing_tool.state.auth_state import clear_auth_context, get_auth_context
from calb_sizing_tool.state.workspace_state import apply_pending_navigation, get_workspace_context
from calb_sizing_tool.ui.login_view import show as show_login


st.set_page_config(
    page_title="CALB ESS SIZING PLATFORM",
    layout="wide",
    page_icon="CALB",
)

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
        st.image(str(logo_path), width=200)
    else:
        st.markdown("## CALB ESS")

    display_name = auth_context.display_name or auth_context.username
    st.caption(f"Signed in as {display_name}")
    st.caption("Role: Admin" if auth_context.is_admin else "Role: Normal User")
    if st.button("Logout", use_container_width=True):
        clear_auth_context()
        st.rerun()

    workspace_context = get_workspace_context()
    st.markdown("---")
    st.caption("Current Workspace")
    st.caption(f"Project: {workspace_context.get('project_name') or 'None'}")
    st.caption(f"Case: {workspace_context.get('case_name') or 'None'}")
    st.caption(f"Run: {workspace_context.get('run_id') or 'None'}")

    st.title("Navigation")
    st.markdown("---")
    nav = st.radio(
        "Go to",
        NAV_OPTIONS,
        key="main_nav",
    )

    st.markdown("---")
    st.caption("v2.1 Workbench")

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
