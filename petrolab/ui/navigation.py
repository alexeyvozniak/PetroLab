from __future__ import annotations

import streamlit as st

from petrolab.db import list_accessible_datasets, list_projects
from petrolab.settings_service import load_settings
from petrolab.ui.project_context import active_project_id, set_active_project
from petrolab.update_checker import available_update


NAV_SECTIONS = {
    "Данные": [
        ("home", "Главная"), ("sources", "Новые анализы"), ("intake", "Источники и литература"), ("sessions", "Сессии"),
        ("mixed_minerals", "Разбор фаз"), ("measurements", "Образцы и измерения"), ("database", "Вся база"),
        ("analyses", "База анализов"), ("formulae", "Расчёты"),
    ],
    "Исследование": [
        ("plots", "XY-диаграммы"), ("ternary", "Треугольные"),
        ("science_plots", "Научные диаграммы"), ("statistics", "Статистика"),
        ("generations", "Поколения"), ("equilibrium", "Равновесные пары"), ("distribution", "Распределение элементов"), ("thermobarometry", "Термобарометрия"),
    ],
    "Материалы": [
        ("rocks", "Породы"), ("slides", "Шлифы и поля"), ("images", "Изображения"),
        ("minerals", "Минералогические модули"),
    ],
    "Публикация": [("article_tables", "Таблицы для статьи"), ("export", "Экспорт")],
    "Система": [
        ("projects", "Проекты"), ("collaboration", "Совместная работа"),
        ("settings", "Настройки"), ("help", "Справка"), ("updates", "Что нового"),
        ("change_log", "История правок данных"),
    ],
}
ROUTE_LABELS = {route: label for entries in NAV_SECTIONS.values() for route, label in entries}


def navigate(route: str) -> None:
    if route in ROUTE_LABELS:
        st.session_state["nav_route"] = route


@st.cache_data(ttl=6 * 60 * 60, show_spinner=False)
def _available_update(installed_version: str) -> str | None:
    return available_update(installed_version)


def _render_update_notice(installed_version: str) -> None:
    if not bool(load_settings().get("check_updates_automatically", True)):
        return
    remote_version = _available_update(installed_version)
    if remote_version is None:
        return
    st.divider()
    st.warning(f"Доступна новая версия v{remote_version}")
    st.caption("Закройте программу и дважды щёлкните UPDATE_PETROLAB.bat. Ваши данные не изменятся.")
    if st.button("Как обновить", key="sidebar_open_updates", width="stretch"):
        navigate("updates")
        st.rerun()


def render_sidebar(version: str) -> str:
    st.markdown('<div class="petrolab-sidebar-brand">◈ ПетроЛаб</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="petrolab-sidebar-version">v{version} · локальные данные</div>', unsafe_allow_html=True)

    projects = list_projects()
    st.markdown('<div class="petrolab-nav-section">Проект</div>', unsafe_allow_html=True)
    if projects:
        by_id = {int(row["id"]): row for row in projects}
        ids = list(by_id)
        current_id = active_project_id()
        active_id = current_id if current_id in by_id else ids[0]
        if st.session_state.get("sidebar_project") != active_id:
            st.session_state["sidebar_project"] = active_id
        selected = st.selectbox(
            "Проект", ids,
            format_func=lambda value: str(by_id[int(value)]["name"]),
            key="sidebar_project", label_visibility="collapsed",
        )
        set_active_project(int(selected))
        datasets = list_accessible_datasets(int(selected))
        rows = sum(int(item.get("row_count") or 0) for item in datasets)
        st.caption(f"{len(datasets)} наборов · {rows:,} анализов".replace(",", " "))
        st.session_state["_sidebar_project_ready"] = True
    else:
        st.session_state.pop("_sidebar_project_ready", None)
        st.caption("Создайте первый проект")

    _render_update_notice(version)

    current = str(st.session_state.get("nav_route", "home"))
    if current not in ROUTE_LABELS:
        current = "home"
        st.session_state["nav_route"] = current
    for section, entries in NAV_SECTIONS.items():
        st.markdown(f'<div class="petrolab-nav-section">{section}</div>', unsafe_allow_html=True)
        for route, label in entries:
            if st.button(label, key=f"nav_{route}", type="primary" if route == current else "secondary", width="stretch"):
                st.session_state["nav_route"] = route
                st.rerun()
    return current
