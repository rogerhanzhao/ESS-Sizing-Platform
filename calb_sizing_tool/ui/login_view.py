from __future__ import annotations

import streamlit as st

from calb_sizing_tool.infra.db.base import Base
from calb_sizing_tool.infra.db.session import session_scope
from calb_sizing_tool.services.auth_service import AuthService
from calb_sizing_tool.state.auth_state import AuthContext, set_auth_context


def _ensure_schema() -> None:
    with session_scope() as session:
        Base.metadata.create_all(bind=session.get_bind())


def show() -> None:
    _ensure_schema()
    auth_service = AuthService()
    auth_service.ensure_system_roles()

    st.title("Sign In")

    if not auth_service.has_users():
        st.info("No users found. Create the initial admin account.")
        with st.form("bootstrap_admin"):
            username = st.text_input("Admin Username")
            display_name = st.text_input("Display Name", value="Administrator")
            password = st.text_input("Password", type="password")
            confirm = st.text_input("Confirm Password", type="password")
            submitted = st.form_submit_button("Create Admin")
            if submitted:
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
                    set_auth_context(
                        AuthContext(
                            user_id=user.user_id,
                            username=user.username,
                            display_name=user.display_name,
                            roles=user.roles,
                        )
                    )
                    st.success("Admin account created.")
                    st.rerun()
        return

    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Login")
        if submitted:
            user = auth_service.authenticate(username=username.strip(), password=password)
            if not user:
                st.error("Invalid credentials.")
            else:
                set_auth_context(
                    AuthContext(
                        user_id=user.user_id,
                        username=user.username,
                        display_name=user.display_name,
                        roles=user.roles,
                    )
                )
                st.success("Login successful.")
                st.rerun()
