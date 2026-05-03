from __future__ import annotations

import base64
from pathlib import Path

import streamlit as st

from calb_sizing_tool.services.auth_service import AuthService
from calb_sizing_tool.state.auth_state import AuthContext, set_auth_context
from calb_sizing_tool.state.workspace_state import navigate_to

_FEATURES = [
    ("DC Sizing",           "String sizing from POI targets — cell selection, thermal derating, capacity margin."),
    ("AC Sizing",           "PCS block count, transformer sizing, auxiliary load budget, AC/DC validation."),
    ("Single Line Diagram", "Auto-generated engineering SLD — bus topology, protection annotation, PNG export."),
    ("Site Layout",         "Block-level arrangement with footprint checks and scaled plan-view export."),
    ("Report Export",       "Word (.docx) report: executive summary, sizing tables, SLD, and site layout."),
]

_CSS = """
<style>
/* ── Page ────────────────────────────────────────────────────────────── */
.stApp { background-color: #E2EBF5 !important; }
.block-container { padding-top: 5vh !important; padding-bottom: 5vh !important; }

/* ── Left info panel column ──────────────────────────────────────────── */
div[data-testid="stHorizontalBlock"]
  > div[data-testid="column"]:first-child
  > div[data-testid="stVerticalBlock"] {
    background: #EEF3FA;
    border: 1px solid #C2D3E8;
    border-radius: 10px;
    padding: 2rem 1.75rem 1.5rem !important;
    box-shadow: 0 4px 18px rgba(20,50,100,0.07);
}

/* ── Right login card (st.container border=True) ─────────────────────── */
div[data-testid="stVerticalBlockBorderWrapper"] {
    border: 1px solid #C2D3E8 !important;
    border-radius: 10px !important;
    background: #FFFFFF !important;
    box-shadow: 0 6px 24px rgba(20,50,100,0.10) !important;
}
/* Tighten internal padding of the bordered card */
div[data-testid="stVerticalBlockBorderWrapper"]
  > div[data-testid="stVerticalBlock"] {
    padding: 1.5rem 1.5rem 1.25rem !important;
    gap: 0.4rem !important;
}
</style>
"""


def _logo_b64() -> str | None:
    p = Path("calb_logo.png")
    return base64.b64encode(p.read_bytes()).decode() if p.exists() else None


def _left_html() -> str:
    b64 = _logo_b64()
    logo = (
        f'<img src="data:image/png;base64,{b64}" '
        f'style="height:40px;width:auto;display:block;margin-bottom:0.5rem">'
        if b64 else
        '<div style="color:#1E4172;font-size:1.5rem;font-weight:900;margin-bottom:0.5rem">CALB</div>'
    )

    rows = "".join(
        f'<tr valign="top">'
        f'<td style="white-space:nowrap;padding:0.25rem 0.8rem 0.25rem 0;'
        f'color:#1E4172;font-weight:700;font-size:0.78rem">&#9656;&nbsp;{t}</td>'
        f'<td style="color:#4A6A84;font-size:0.75rem;line-height:1.55;padding:0.25rem 0">{d}</td>'
        f'</tr>'
        for t, d in _FEATURES
    )

    return f"""
{logo}
<div style="color:#1A2635;font-size:0.92rem;font-weight:700;margin-bottom:0.65rem;line-height:1.3">
    Utility-Scale BESS Sizing Platform
</div>
<div style="color:#3A5A7A;font-size:0.77rem;line-height:1.65;
     margin-bottom:1rem;padding-bottom:0.9rem;border-bottom:1px solid #C2D3E8">
    An integrated sizing and documentation workflow for utility-scale Battery Energy
    Storage Systems — from DC cell selection through AC interconnect and report delivery.
</div>
<div style="color:#1E4172;font-size:0.62rem;font-weight:700;letter-spacing:0.09em;
     text-transform:uppercase;margin-bottom:0.65rem">
    Platform Capabilities
</div>
<table style="border-collapse:collapse;width:100%">{rows}</table>
<div style="color:#A8BED4;font-size:0.63rem;margin-top:1.25rem">
    © 2026 Alex Zhao &nbsp;·&nbsp; MIT License &nbsp;·&nbsp; v2.1
</div>
"""


def show() -> None:
    auth_service = AuthService()
    auth_service.ensure_system_roles()

    st.markdown(_CSS, unsafe_allow_html=True)

    left_col, right_col = st.columns([1.45, 1.0])

    with left_col:
        st.markdown(_left_html(), unsafe_allow_html=True)

    with right_col:
        with st.container(border=True):
            # Compact header — title + subtitle in one block, thin divider via border-bottom
            st.markdown("""
<div style="border-bottom:1px solid #D8E6F2;padding-bottom:0.65rem;margin-bottom:0.55rem">
    <div style="color:#1A2635;font-size:1.0rem;font-weight:700;margin-bottom:0.18rem">Sign In</div>
    <div style="color:#6A8AA4;font-size:0.74rem">
        Project → Case → Run is the primary working boundary.
    </div>
</div>
""", unsafe_allow_html=True)

            if not auth_service.has_users():
                st.info("No users found. Create the initial admin account.")
                with st.form("bootstrap_admin"):
                    username     = st.text_input("Admin Username", placeholder="username")
                    display_name = st.text_input("Display Name", value="Administrator")
                    password     = st.text_input("Password", type="password", placeholder="••••••••")
                    confirm      = st.text_input("Confirm Password", type="password", placeholder="••••••••")
                    if st.form_submit_button("Create Admin Account", use_container_width=True):
                        if not username.strip():
                            st.error("Username is required.")
                        elif not password:
                            st.error("Password is required.")
                        elif password != confirm:
                            st.error("Passwords do not match.")
                        else:
                            user = auth_service.create_user(
                                username=username.strip(),
                                password=password,
                                display_name=display_name.strip() or None,
                                role_codes=["admin"],
                            )
                            set_auth_context(AuthContext(
                                user_id=user.user_id,
                                username=user.username,
                                display_name=user.display_name,
                                roles=user.roles,
                            ))
                            navigate_to("Workbench")
                            st.rerun()
            else:
                with st.form("login_form"):
                    username = st.text_input(
                        "Username",
                        placeholder="Enter username",
                        label_visibility="collapsed",
                    )
                    password = st.text_input(
                        "Password",
                        type="password",
                        placeholder="Enter password",
                        label_visibility="collapsed",
                    )
                    if st.form_submit_button("Login", use_container_width=True):
                        user = auth_service.authenticate(username=username.strip(), password=password)
                        if not user:
                            st.error("Invalid credentials.")
                        else:
                            set_auth_context(AuthContext(
                                user_id=user.user_id,
                                username=user.username,
                                display_name=user.display_name,
                                roles=user.roles,
                            ))
                            navigate_to("Workbench")
                            st.rerun()

                st.markdown(
                    '<div style="text-align:center;margin-top:0.5rem">'
                    '<span style="color:#A0B8CC;font-size:0.72rem">or</span></div>',
                    unsafe_allow_html=True,
                )
                if st.button(
                    "Continue as Guest  —  DC / AC Sizing only",
                    use_container_width=True,
                    help="Guest mode: sizing and SLD are enabled. Export / report download is disabled.",
                ):
                    set_auth_context(AuthContext(
                        user_id="guest-session",
                        username="guest",
                        display_name="Guest",
                        roles=["guest"],
                    ))
                    navigate_to("DC Sizing")
                    st.rerun()
