from __future__ import annotations

import streamlit as st

from petrolab import __version__
from petrolab.db import ensure_storage
from petrolab.ui.pages import (
    render_analyses_page,
    render_change_log_page,
    render_export_page,
    render_formulae_page,
    render_home_page,
    render_images_page,
    render_minerals_page,
    render_plots_page,
    render_projects_page,
    render_sources_page,
)

st.set_page_config(page_title="ПетроЛаб", page_icon="◈", layout="wide")
ensure_storage()

st.markdown(
    """
    <style>
    .block-container {padding-top: 1.2rem; padding-bottom: 3rem; max-width: 1650px;}
    h1, h2, h3 {letter-spacing: -0.02em;}
    [data-testid="stMetric"] {border: 1px solid rgba(80,80,80,.14); padding: 12px; border-radius: 12px;}
    .small-note {font-size: .88rem; opacity: .75;}
    </style>
    """,
    unsafe_allow_html=True,
)

if "loaded_recipe" not in st.session_state:
    st.session_state.loaded_recipe = None

PAGES = {
    "Главная": render_home_page,
    "Проекты": render_projects_page,
    "Источники и импорт": render_sources_page,
    "Единая база": render_analyses_page,
    "Расчёты и формулы": render_formulae_page,
    "Диаграммы": render_plots_page,
    "Изображения": render_images_page,
    "Минералы": render_minerals_page,
    "Экспорт": render_export_page,
    "Журнал изменений": render_change_log_page,
}

with st.sidebar:
    st.title("◈ ПетроЛаб")
    st.caption(f"Русская версия · v{__version__}")
    page = st.radio("Раздел", list(PAGES), label_visibility="collapsed")
    st.divider()
    st.caption(
        "Рабочий путь: импорт → расчёт → диаграмма. Исходные Excel остаются источником, "
        "а расчётные поля хранятся отдельно и связываются с аналитическими точками."
    )

PAGES[page]()
