from __future__ import annotations

import streamlit as st

from petrolab import __version__
from petrolab.settings_service import load_settings
from petrolab.storage import ensure_storage
from petrolab.ui.pages import (
    render_analyses_page,
    render_article_tables_page,
    render_change_log_page,
    render_export_page,
    render_formulae_page,
    render_help_page,
    render_home_page,
    render_images_page,
    render_minerals_page,
    render_plots_page,
    render_projects_page,
    render_rocks_page,
    render_science_plots_page,
    render_settings_page,
    render_sources_page,
    render_statistics_page,
    render_ternary_page,
    render_updates_page,
)
from petrolab.ui.import_page_policy import install as install_import_page_policy
from petrolab.ui.theme import apply_theme

install_import_page_policy()

st.set_page_config(page_title="ПетроЛаб", page_icon="◈", layout="wide")
ensure_storage()
settings = load_settings()
apply_theme(str(settings.get("ui_density", "comfortable")))

if "loaded_recipe" not in st.session_state:
    st.session_state.loaded_recipe = None
if "loaded_ternary_recipe" not in st.session_state:
    st.session_state.loaded_ternary_recipe = None

PAGE_GROUPS = {
    "Работа с данными": {
        "Главная": render_home_page,
        "Проекты": render_projects_page,
        "Источники и импорт": render_sources_page,
        "Единая база": render_analyses_page,
        "Расчёты и формулы": render_formulae_page,
    },
    "Графики и статистика": {
        "XY-диаграммы": render_plots_page,
        "Треугольные диаграммы": render_ternary_page,
        "Научные диаграммы": render_science_plots_page,
        "Статистика и кластеры": render_statistics_page,
    },
    "Породы и изображения": {
        "Породы": render_rocks_page,
        "Изображения минералов": render_images_page,
        "Справочник минералов": render_minerals_page,
    },
    "Публикация": {
        "Таблицы для статьи": render_article_tables_page,
        "Экспорт": render_export_page,
    },
    "Справка и настройки": {
        "Что нового": render_updates_page,
        "Инструкция": render_help_page,
        "Настройки": render_settings_page,
        "Журнал изменений": render_change_log_page,
    },
}

with st.sidebar:
    st.title("◈ ПетроЛаб")
    st.caption(f"Русская версия · v{__version__}")
    group = st.selectbox("Рабочая область", list(PAGE_GROUPS), key="navigation_group")
    page = st.radio("Раздел", list(PAGE_GROUPS[group]), label_visibility="collapsed", key=f"navigation_{group}")
    st.divider()
    st.caption(
        "Данные → расчёт → исследование → публикация. Исходные Excel, derived-поля и "
        "локальная интерпретация остаются отдельными слоями."
    )

PAGE_GROUPS[group][page]()
