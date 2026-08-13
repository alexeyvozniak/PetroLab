from __future__ import annotations

import streamlit as st


def confirm_action(
    label: str,
    *,
    key: str,
    confirm_label: str = "Да, удалить",
    warning: str = "Действие нельзя отменить.",
    button_type: str = "secondary",
    confirm_type: str = "primary",
    width: str = "stretch",
) -> bool:
    """Render a two-step confirmation control and return True only on confirmation."""
    state_key = f"_confirm_action_{key}"
    if not st.session_state.get(state_key, False):
        if st.button(label, key=f"{key}_ask", type=button_type, width=width):
            st.session_state[state_key] = True
            st.rerun()
        return False

    st.warning(warning)
    yes, no = st.columns(2)
    if yes.button(confirm_label, key=f"{key}_yes", type=confirm_type, width="stretch"):
        st.session_state.pop(state_key, None)
        return True
    if no.button("Отмена", key=f"{key}_no", width="stretch"):
        st.session_state.pop(state_key, None)
        st.rerun()
    return False


def clear_confirmation(key: str) -> None:
    st.session_state.pop(f"_confirm_action_{key}", None)
