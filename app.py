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


st.set_page_config(
    page_title="CALB ESS SIZING PLATFORM",
    layout="wide",
    page_icon="CALB",
)

with st.sidebar:
    logo_path = Path("calb_logo.png")
    if logo_path.exists():
        st.image(str(logo_path), width=200)
    else:
        st.markdown("## CALB ESS")

    st.title("Navigation")
    st.markdown("---")
    nav = st.radio(
        "Go to",
        [
            "Dashboard",
            "Projects",
            "Cases",
            "Run History",
            "DC Sizing",
            "AC Sizing",
            "Single Line Diagram",
            "Site Layout",
            "Report Export",
        ],
    )

    st.markdown("---")
    st.caption("v2.1 Refactored")

if nav == "Dashboard":
    st.title("CALB ESS SIZING PLATFORM")
    st.markdown("### Utility-Scale Energy Storage Sizing Tool")
    st.info("Follow the standard workflow:")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown("#### 1. DC Sizing")
        st.write("Define capacity, select battery technology, and calculate degradation.")
    with col2:
        st.markdown("#### 2. AC Sizing")
        st.write("Configure grid voltage, transformers, and PCS blocks based on DC results.")
    with col3:
        st.markdown("#### 3. SLD Generation")
        st.write("Generate the Single Line Diagram for the system.")

elif nav == "Projects":
    from calb_sizing_tool.ui.projects_view import show

    show()

elif nav == "Cases":
    from calb_sizing_tool.ui.cases_view import show

    show()

elif nav == "Run History":
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
