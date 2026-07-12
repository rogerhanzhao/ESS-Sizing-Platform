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

from html import escape
import os
from pathlib import Path

import streamlit as st

import calb_sizing_tool.config as config  # noqa: F401
from calb_sizing_tool.infra.db.base import Base
from calb_sizing_tool.infra.db.session import create_engine_for_url, session_scope
from calb_sizing_tool.state.auth_state import clear_auth_context, get_auth_context
from calb_sizing_tool.state.workspace_state import apply_pending_navigation, get_workspace_context, navigate_now
from calb_sizing_tool.ui._styles import inject_global_styles
from calb_sizing_tool.ui.login_view import show as show_login


st.set_page_config(
    page_title="CALB ESS SIZING PLATFORM",
    layout="wide",
    page_icon="⚡",
)

inject_global_styles()

# ── DB schema (once at startup) ───────────────────────────────────────────────
# Prefer Alembic so that alembic_version is populated correctly (required for
# future incremental migrations).  Falls back to create_all when alembic.ini
# is not reachable (e.g. unusual working-directory situations).
def _allow_create_all_fallback() -> bool:
    return os.environ.get("CALB_ALLOW_CREATE_ALL_FALLBACK", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


@st.cache_resource
def _run_startup_migrations() -> None:
    try:
        from pathlib import Path as _Path
        from alembic import command as _alembic_cmd
        from alembic.config import Config as _AlembicCfg
        _ini = _Path(__file__).resolve().parent / "alembic.ini"
        _cfg = _AlembicCfg(str(_ini))
        _alembic_cmd.upgrade(_cfg, "head")
    except Exception as exc:
        if not _allow_create_all_fallback():
            raise RuntimeError(
                "Alembic migration failed. Refusing to fall back to create_all(). "
                "Set CALB_ALLOW_CREATE_ALL_FALLBACK=true only for local throwaway databases."
            ) from exc
        with session_scope() as _s:
            Base.metadata.create_all(bind=_s.get_bind())

_run_startup_migrations()

@st.cache_resource
def _db_schema_revision() -> str:
    try:
        engine = create_engine_for_url()
        with engine.connect() as _c:
            row = _c.execute(
                __import__("sqlalchemy").text("SELECT version_num FROM alembic_version LIMIT 1")
            ).fetchone()
            return row[0][:14] if row else "unversioned"
    except Exception:
        return "unversioned"

auth_context = get_auth_context()
if auth_context is None:
    show_login()
    st.stop()

_TYPICAL_AC_BLOCK_ARRANGEMENT = "Typical AC Block Arrangement"
_LEGACY_NAV_ALIASES = {"Site Layout": _TYPICAL_AC_BLOCK_ARRANGEMENT}
for _nav_state_key in ("main_nav", "_pending_main_nav"):
    if st.session_state.get(_nav_state_key) in _LEGACY_NAV_ALIASES:
        st.session_state[_nav_state_key] = _LEGACY_NAV_ALIASES[st.session_state[_nav_state_key]]

_ALL_NAV = [
    "Workbench",
    "DC Sizing",
    "AC Sizing",
    "Single Line Diagram",
    _TYPICAL_AC_BLOCK_ARRANGEMENT,
    "Report Export",
    "Engineering Settings",
    "Project Directory",
    "Case Directory",
    "Run Registry",
]
# Guests can size but cannot access project/run management or export
_GUEST_NAV = ["DC Sizing", "AC Sizing", "Single Line Diagram", _TYPICAL_AC_BLOCK_ARRANGEMENT]

NAV_OPTIONS = _GUEST_NAV if auth_context.is_guest else _ALL_NAV
apply_pending_navigation(NAV_OPTIONS, default_page="DC Sizing" if auth_context.is_guest else "Workbench")

# Admin portal: separate from the main nav, activated via session flag
_ADMIN_PORTAL_ACTIVE = bool(st.session_state.get("__admin_portal__")) and auth_context.is_admin
# Safe default so `nav` is always defined; radio below overwrites it when portal is inactive
nav: str = st.session_state.get("main_nav") or NAV_OPTIONS[0]
# Clamp to the allowed set for this user's role — prevents stale session state from routing guests
# to restricted pages (e.g. a guest inheriting main_nav="Workbench" from a previous login session)
if nav not in NAV_OPTIONS:
    nav = NAV_OPTIONS[0]
    st.session_state["main_nav"] = nav

with st.sidebar:
    logo_path = Path("calb_logo.png")
    if logo_path.exists():
        st.image(str(logo_path), width=180)
    else:
        st.markdown("## CALB ESS")

    st.markdown("---")
    display_name = auth_context.display_name or auth_context.username
    st.caption(f"Signed in as  **{display_name}**")
    if auth_context.is_guest:
        st.caption("👁 Guest  ·  sizing only")
    elif auth_context.is_admin:
        st.caption("🔑 Admin")
    else:
        st.caption("👤 User")
    if st.button("Logout", use_container_width=True):
        clear_auth_context()
        st.session_state.pop("__admin_portal__", None)
        st.rerun()

    if not auth_context.is_guest:
        workspace_context = get_workspace_context()
        _run_id = workspace_context.get("run_id")
        _run_short = f"··{_run_id[-8:]}" if _run_id and len(_run_id) >= 8 else (_run_id or "—")
        st.markdown("---")
        st.markdown(
            '<div class="sb-nav-group" style="margin-top:0">Workspace</div>'
            '<div class="sb-workspace">'
            '<div class="sb-ws-item">'
            f'<span class="sb-ws-label">Project</span>'
            f'<span class="sb-ws-value">{escape(workspace_context.get("project_name") or "—")}</span>'
            "</div>"
            '<div class="sb-ws-item">'
            f'<span class="sb-ws-label">Case</span>'
            f'<span class="sb-ws-value">{escape(workspace_context.get("case_name") or "—")}</span>'
            "</div>"
            '<div class="sb-ws-item">'
            f'<span class="sb-ws-label">Run</span>'
            f'<span class="sb-ws-value">{escape(_run_short)}</span>'
            "</div>"
            "</div>",
            unsafe_allow_html=True,
        )

    st.markdown("---")
    if _ADMIN_PORTAL_ACTIVE:
        st.markdown(
            '<div class="sb-nav-group" style="margin-top:0">Admin Portal</div>'
            '<div class="sb-nav-active">&#9881; Product &amp; Database</div>',
            unsafe_allow_html=True,
        )
        if st.button("← Back to Sizing", use_container_width=True):
            st.session_state.pop("__admin_portal__", None)
            st.rerun()
    else:
        _NAV_GROUPS: list[tuple[str, list[str]]] = (
            [
                ("Workspace",       ["Workbench", "Project Directory", "Case Directory", "Engineering Settings"]),
                ("Sizing Pipeline", ["DC Sizing", "AC Sizing", "Single Line Diagram", _TYPICAL_AC_BLOCK_ARRANGEMENT, "Report Export"]),
                ("History",         ["Run Registry"]),
            ]
            if not auth_context.is_guest
            else [
                ("Sizing Pipeline", ["DC Sizing", "AC Sizing", "Single Line Diagram", _TYPICAL_AC_BLOCK_ARRANGEMENT]),
            ]
        )
        for _grp_i, (_grp_label, _grp_pages) in enumerate(_NAV_GROUPS):
            _visible = [p for p in _grp_pages if p in NAV_OPTIONS]
            if not _visible:
                continue
            _top_style = ' style="margin-top:0"' if _grp_i == 0 else ""
            st.markdown(
                f'<div class="sb-nav-group"{_top_style}>{escape(_grp_label)}</div>',
                unsafe_allow_html=True,
            )
            for _page in _visible:
                if _page == nav:
                    st.markdown(
                        f'<div class="sb-nav-active">{escape(_page)}</div>',
                        unsafe_allow_html=True,
                    )
                else:
                    if st.button(_page, use_container_width=True, key=f"nav_btn_{_page}"):
                        navigate_now(_page)

    if auth_context.is_admin:
        st.markdown("---")
        st.caption("ADMINISTRATION")
        _admin_btn_label = "← Back to Sizing" if _ADMIN_PORTAL_ACTIVE else "⚙ Product & Database"
        if not _ADMIN_PORTAL_ACTIVE and st.button("⚙ Product & Database", use_container_width=True):
            st.session_state["__admin_portal__"] = True
            st.rerun()

    st.markdown("---")
    st.caption(f"v2.1 · CALB ESS Sizing Platform · db:{_db_schema_revision()}")

# ── Route ─────────────────────────────────────────────────────────────────────
if _ADMIN_PORTAL_ACTIVE:
    from calb_sizing_tool.ui.admin_portal_view import show as show_admin
    show_admin()
    st.stop()

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

elif nav == _TYPICAL_AC_BLOCK_ARRANGEMENT:
    from calb_sizing_tool.ui.site_layout_view import show
    show()

elif nav == "Report Export":
    from calb_sizing_tool.ui.report_export_view import show
    show()

elif nav == "Engineering Settings":
    from calb_sizing_tool.ui.engineering_settings_view import show
    show()
