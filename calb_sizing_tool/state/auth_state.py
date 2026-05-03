from __future__ import annotations

from dataclasses import dataclass

import streamlit as st


@dataclass
class AuthContext:
    user_id: str
    username: str
    display_name: str | None
    roles: list[str]

    @property
    def is_admin(self) -> bool:
        return "admin" in self.roles

    @property
    def is_guest(self) -> bool:
        return "guest" in self.roles


def get_auth_context() -> AuthContext | None:
    payload = st.session_state.get("auth_context")
    if not isinstance(payload, dict):
        return None
    user_id = payload.get("user_id")
    username = payload.get("username")
    roles = payload.get("roles")
    if not user_id or not username or not isinstance(roles, list):
        return None
    return AuthContext(
        user_id=user_id,
        username=username,
        display_name=payload.get("display_name"),
        roles=roles,
    )


def set_auth_context(context: AuthContext) -> None:
    st.session_state["auth_context"] = {
        "user_id": context.user_id,
        "username": context.username,
        "display_name": context.display_name,
        "roles": list(context.roles),
    }


def clear_auth_context() -> None:
    st.session_state.pop("auth_context", None)


def get_auth_user():
    """Return an AuthUser built from the current session auth context, or None."""
    context = get_auth_context()
    if context is None:
        return None
    from calb_sizing_tool.services.auth_service import AuthUser  # lazy to avoid circular import
    return AuthUser(
        user_id=context.user_id,
        username=context.username,
        display_name=context.display_name,
        roles=context.roles,
    )
