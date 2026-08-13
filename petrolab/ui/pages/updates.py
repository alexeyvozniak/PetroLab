from __future__ import annotations

import streamlit as st

from petrolab import __version__
from petrolab.release_notes import RELEASE_NOTES


def render_updates_page() -> None:
    st.title("Что нового")
    st.caption(f"Установленная версия: {__version__}")
    for index, release in enumerate(RELEASE_NOTES):
        with st.expander(f"v{release.version} · {release.title}", expanded=index == 0):
            for item in release.items:
                st.markdown(f"- {item}")
