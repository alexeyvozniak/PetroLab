from __future__ import annotations

import streamlit as st


def apply_release_chrome() -> None:
    """Hide Streamlit hosting controls that are irrelevant in the local PetroLab desktop app.

    The runtime status widget is intentionally left visible so a long calculation can still
    be interrupted by the user. Only deploy/menu/footer chrome is removed.
    """
    st.markdown(
        """
        <style>
        #MainMenu,
        footer,
        [data-testid="stAppDeployButton"],
        [data-testid="stToolbarActions"] {
            display: none !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
