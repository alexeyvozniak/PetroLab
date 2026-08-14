from __future__ import annotations

from collections.abc import Callable

import streamlit as st


def pending_key(name: str) -> str:
    return f"_pending_destructive_{name}"


def render_pending(name: str, text: str, *, cancel_label: str = "Отмена") -> None:
    """Show a pending destructive action and allow the user to cancel it."""
    key = pending_key(name)
    if key not in st.session_state:
        return
    st.warning(text)
    if st.button(cancel_label, key=f"cancel_{name}"):
        st.session_state.pop(key, None)
        st.rerun()


def confirm_then(name: str, target, action: Callable[[], None]) -> bool:
    """Execute only after the same target is requested twice across Streamlit reruns."""
    key = pending_key(name)
    target_value = tuple(target) if isinstance(target, (list, tuple, set)) else target
    if st.session_state.get(key) != target_value:
        st.session_state[key] = target_value
        st.rerun()
        return False
    st.session_state.pop(key, None)
    action()
    return True
