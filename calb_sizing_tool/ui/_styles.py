"""Shared CALB visual system styles for Streamlit pages."""
from __future__ import annotations

import streamlit as st


def inject_global_styles() -> None:
    """Inject the global CALB VI stylesheet once per Streamlit run."""
    st.markdown(
        """
        <style>
        :root {
            --calb-navy: #0E2240;
            --calb-blue: #1E4172;
            --calb-blue-2: #2A527A;
            --calb-cyan: #5CC3E4;
            --calb-text: #1A2635;
            --calb-muted: #6F7E8F;
            --calb-line: #D0DAE8;
            --calb-soft: #EDF1F7;
            --calb-soft-2: #F5F8FC;
            --calb-white: #FFFFFF;
        }

        html,
        body,
        .stApp {
            color: var(--calb-text);
            font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif;
            letter-spacing: 0;
        }

        .block-container {
            padding-top: 4rem !important;
            padding-bottom: 2rem !important;
        }

        .block-container h1,
        .block-container h2,
        .block-container h3 {
            color: var(--calb-text) !important;
            letter-spacing: 0 !important;
            line-height: 1.18 !important;
            text-transform: none !important;
        }

        .block-container p,
        .block-container label {
            letter-spacing: 0;
        }

        hr {
            border-color: var(--calb-line) !important;
        }

        section[data-testid="stSidebar"] {
            background-color: var(--calb-navy) !important;
        }

        section[data-testid="stSidebar"] p,
        section[data-testid="stSidebar"] span,
        section[data-testid="stSidebar"] label,
        section[data-testid="stSidebar"] .stMarkdown,
        section[data-testid="stSidebar"] .stCaption > * {
            color: #B8CADE !important;
        }

        section[data-testid="stSidebar"] h1,
        section[data-testid="stSidebar"] h2,
        section[data-testid="stSidebar"] h3 {
            color: var(--calb-white) !important;
        }

        section[data-testid="stSidebar"] hr {
            border-color: #1E3A5C !important;
            margin: 0.5rem 0;
        }

        section[data-testid="stSidebar"] [data-baseweb="radio"] div[aria-checked="true"] ~ div {
            color: var(--calb-white) !important;
            font-weight: 600;
        }

        .calb-ph {
            border-left: 4px solid var(--calb-blue);
            margin-bottom: 0.65rem;
            overflow: visible;
            padding: 0.28rem 0 0.3rem 0.8rem;
        }

        .calb-ph-title {
            color: var(--calb-text) !important;
            display: block !important;
            font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif !important;
            font-size: 1.55rem !important;
            font-weight: 760 !important;
            letter-spacing: 0 !important;
            line-height: 1.22 !important;
            margin: 0 !important;
            overflow: visible;
            padding: 0 !important;
            text-align: left !important;
            text-transform: none !important;
        }

        .calb-ph-sub {
            color: #3A5A80 !important;
            font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif !important;
            font-size: 0.72rem !important;
            font-weight: 650 !important;
            letter-spacing: 0.06em !important;
            line-height: 1.3 !important;
            margin: 0.2rem 0 0 0 !important;
            padding: 0 !important;
            text-align: left !important;
            text-transform: uppercase !important;
        }

        .calb-card {
            background: var(--calb-white);
            border: 1px solid var(--calb-line);
            border-radius: 4px;
            box-shadow: none;
            margin-bottom: 1rem;
            padding: 1rem 1.1rem;
        }

        .calb-section-header {
            align-items: baseline;
            display: flex;
            flex-wrap: wrap;
            gap: 0.35rem 0.55rem;
            margin: 0.15rem 0 0.8rem;
        }

        .calb-section-eyebrow {
            color: #506F94;
            font-size: 0.72rem;
            font-weight: 750;
            letter-spacing: 0.06em;
            line-height: 1.25;
            text-transform: uppercase;
        }

        .calb-section-title {
            color: var(--calb-text);
            font-size: 1.05rem;
            font-weight: 720;
            letter-spacing: 0;
            line-height: 1.24;
        }

        .calb-section-caption {
            color: var(--calb-muted);
            flex-basis: 100%;
            font-size: 0.82rem;
            line-height: 1.35;
            margin: 0.1rem 0 0 0 !important;
        }

        .calb-status-bar {
            background: var(--calb-soft-2);
            border: 1px solid var(--calb-line);
            border-left: 4px solid var(--calb-blue);
            border-radius: 5px;
            display: grid;
            gap: 0;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            margin: 0.6rem 0 1rem;
            overflow: hidden;
        }

        .calb-status-cell {
            min-width: 0;
            padding: 0.58rem 0.8rem;
        }

        .calb-status-cell + .calb-status-cell {
            border-left: 1px solid var(--calb-line);
        }

        .calb-status-label {
            color: #506F94;
            display: block;
            font-size: 0.68rem;
            font-weight: 760;
            letter-spacing: 0.06em;
            line-height: 1.25;
            text-transform: uppercase;
        }

        .calb-status-value {
            color: var(--calb-text);
            display: block;
            font-size: 0.9rem;
            font-weight: 720;
            line-height: 1.28;
            margin-top: 0.18rem;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }

        .calb-note {
            background: #EAF2FB;
            border-left: 3px solid var(--calb-blue);
            border-radius: 5px;
            color: #164170;
            font-size: 0.86rem;
            line-height: 1.35;
            margin-top: 0.25rem;
            padding: 0.62rem 0.75rem;
        }

        .calb-muted-line {
            border-top: 1px solid var(--calb-line);
            margin: 1.35rem 0;
        }

        div[data-testid="stVerticalBlockBorderWrapper"] {
            background: var(--calb-white) !important;
            border: 1px solid var(--calb-line) !important;
            border-radius: 6px !important;
            box-shadow: none !important;
            padding: 0.85rem 1rem !important;
        }

        .metric-label {
            color: #506F94 !important;
            font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif;
            font-size: 0.72rem;
            font-weight: 700;
            letter-spacing: 0.06em;
            text-transform: uppercase;
        }

        .metric-value {
            color: var(--calb-text) !important;
            font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif;
            font-size: 1.08rem;
            font-weight: 700;
            line-height: 1.25;
        }

        [data-testid="stMetric"] {
            background-color: var(--calb-soft);
            border-left: 3px solid var(--calb-blue);
            border-radius: 4px;
            padding: 0.6rem 0.8rem !important;
        }

        [data-testid="stMetricLabel"] > div {
            color: #3A5A80 !important;
            font-size: 0.72rem !important;
            font-weight: 650;
            letter-spacing: 0.06em;
            text-transform: uppercase;
        }

        [data-testid="stMetricValue"] > div {
            color: var(--calb-text) !important;
            font-size: 1.1rem !important;
            font-weight: 700;
        }

        .stButton > button {
            align-items: center !important;
            background: var(--calb-soft-2) !important;
            border: 1px solid var(--calb-blue-2) !important;
            border-radius: 6px !important;
            box-shadow: none !important;
            color: var(--calb-blue) !important;
            display: inline-flex !important;
            font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif !important;
            font-size: 0.84rem !important;
            font-weight: 650 !important;
            height: 2.5rem !important;
            justify-content: center !important;
            letter-spacing: 0 !important;
            min-height: 2.5rem !important;
            padding: 0 0.75rem !important;
            text-align: center !important;
            transition: background 0.12s ease, border-color 0.12s ease, color 0.12s ease !important;
            width: 100%;
        }

        .stButton > button p {
            text-align: center !important;
            width: 100%;
        }

        .stButton > button:hover:not(:disabled) {
            background: var(--calb-blue) !important;
            border-color: var(--calb-blue) !important;
            color: var(--calb-white) !important;
        }

        .stButton > button:disabled {
            background: var(--calb-soft-2) !important;
            border-color: #CDD8E6 !important;
            color: #A4AFBA !important;
            opacity: 1 !important;
        }

        div[data-testid="stNumberInput"] label p,
        div[data-testid="stSelectbox"] label p,
        div[data-testid="stTextInput"] label p,
        div[data-testid="stCheckbox"] label p {
            line-height: 1.28 !important;
        }

        div[data-testid="stCheckbox"] {
            margin: 0.25rem 0 0.65rem !important;
        }

        div[data-testid="stCheckbox"] label {
            align-items: flex-start !important;
            gap: 0.55rem !important;
        }

        section[data-testid="stSidebar"] .stButton > button {
            background-color: #1E3A5C !important;
            border: 1px solid #2A4F7A !important;
            border-radius: 4px !important;
            color: #B8CADE !important;
        }

        section[data-testid="stSidebar"] .stButton > button:hover {
            background-color: #1E4172 !important;
            color: var(--calb-white) !important;
        }

        div[data-testid="stDataFrame"] {
            border: 1px solid #D7DEE8;
            border-radius: 6px;
        }

        /* ── Sidebar: workspace context strip ──────────────────────── */
        .sb-workspace {
            padding: 0.25rem 0 0.1rem;
        }

        .sb-ws-item {
            display: flex;
            flex-direction: column;
            padding: 0.18rem 0;
        }

        .sb-ws-label {
            color: #7A9EC4;
            font-size: 0.62rem;
            font-weight: 760;
            letter-spacing: 0.07em;
            line-height: 1.25;
            text-transform: uppercase;
        }

        .sb-ws-value {
            color: #D4E4F4;
            font-size: 0.82rem;
            font-weight: 650;
            line-height: 1.25;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }

        /* ── Sidebar: navigation group labels ──────────────────────── */
        .sb-nav-group {
            color: #6A8EB0;
            font-size: 0.62rem;
            font-weight: 760;
            letter-spacing: 0.09em;
            margin-bottom: 0.3rem;
            margin-top: 0.75rem;
            text-transform: uppercase;
        }

        /* ── Sidebar: active navigation item (filled chip) ─────────── */
        .sb-nav-active {
            background: var(--calb-blue);
            border: 1px solid var(--calb-blue);
            border-radius: 4px;
            box-sizing: border-box;
            color: #FFFFFF;
            display: block;
            font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif;
            font-size: 0.84rem;
            font-weight: 650;
            margin-bottom: 0.38rem;
            padding: 0.62rem 0.75rem;
            text-align: center;
            width: 100%;
        }

        /* Suppress extra Streamlit wrapper margins for these sidebar elements */
        section[data-testid="stSidebar"] .stMarkdown:has(.sb-nav-active),
        section[data-testid="stSidebar"] .stMarkdown:has(.sb-nav-group),
        section[data-testid="stSidebar"] .stMarkdown:has(.sb-workspace) {
            margin-bottom: 0 !important;
        }

        @media (max-width: 900px) {
            .block-container {
                padding-left: 1rem !important;
                padding-right: 1rem !important;
            }

            .calb-ph-title {
                font-size: 1.35rem !important;
            }

            .calb-ph-sub {
                font-size: 0.68rem !important;
            }

            .stButton > button {
                min-height: 2.45rem !important;
            }

            .calb-status-bar {
                grid-template-columns: 1fr;
            }

            .calb-status-cell + .calb-status-cell {
                border-left: 0;
                border-top: 1px solid var(--calb-line);
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
