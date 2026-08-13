from __future__ import annotations

import streamlit as st

from petrolab import __version__
from petrolab.release_notes import RELEASE_NOTES
from petrolab.ui.layout import render_badges, render_page_header


def render_updates_page() -> None:
    render_page_header(
        "Что нового",
        "История версий самой программы PetroLab. Правки научных данных находятся отдельно в «Истории правок данных».",
        eyebrow="Система",
    )
    render_badges([(f"Установлена v{__version__}", "accent")])
    for index, release in enumerate(RELEASE_NOTES):
        with st.expander(f"v{release.version} · {release.title}", expanded=index == 0):
            for item in release.items:
                st.markdown(f"- {item}")
