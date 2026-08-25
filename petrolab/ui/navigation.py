from __future__ import annotations

import streamlit as st

from petrolab.db import list_accessible_datasets, list_projects
from petrolab.settings_service import load_settings
from petrolab.ui.project_context import active_project_id, set_active_project
from petrolab.ui.selection_context import clear_selection, read_selection
from petrolab.update_checker import available_update


# The primary rail mirrors the approved Product Design reference: short,
# task-oriented and stable. Specialist tools stay one level deeper.
PRIMARY_NAV_SECTIONS = {
    "": [
        ("home", "Обзор"),
        ("projects", "Проекты"),
        ("search", "Поиск"),
        ("samples", "Образцы"),
        ("slides", "Шлифы"),
        ("analyses", "Анализы"),
        ("linked_views", "Построение"),
        ("add_data", "Добавить"),
    ],
}
PRIMARY_NAVIGATION = [entry for entries in PRIMARY_NAV_SECTIONS.values() for entry in entries]

SECONDARY_NAV_SECTIONS = {
    "Материалы": [
        ("rocks", "Породы"),
        ("images", "Фотографии"),
        ("measurements", "Объекты и измерения"),
        ("database", "Вся база"),
    ],
    "Выборки и процесс": [
        ("selections", "Рабочие выборки"),
        ("attention", "Требует внимания"),
        ("workflow", "Рабочий процесс"),
        ("batch_edit", "Массовые действия"),
        ("generations", "Поколения"),
    ],
    "Научные инструменты": [
        ("plots", "Обычные графики"),
        ("ternary", "Треугольные диаграммы"),
        ("science_plots", "Научные диаграммы"),
        ("statistics", "Статистика"),
        ("equilibrium", "Равновесные пары"),
        ("distribution", "Распределение элементов"),
        ("thermobarometry", "Термобарометрия"),
        ("mixed_minerals", "Фазы и выбросы"),
        ("formulae", "Расчёты"),
    ],
    "Публикация": [
        ("figure_recipes", "Figure Recipe"),
        ("article_tables", "Таблицы для статьи"),
        ("export", "Экспорт"),
    ],
    "Служебное": [
        ("sources", "Новые анализы"),
        ("sessions", "Аналитические сессии"),
        ("intake", "Источники и литература"),
        ("minerals", "Минералогические модули"),
        ("collaboration", "Совместная работа"),
        ("change_log", "История правок данных"),
        ("help", "Справка"),
        ("updates", "Что нового"),
    ],
}
SYSTEM_NAVIGATION = [("settings", "Настройки")]
ROUTE_LABELS = {
    route: label
    for entries in [PRIMARY_NAVIGATION, *SECONDARY_NAV_SECTIONS.values(), SYSTEM_NAVIGATION]
    for route, label in entries
}
NAV_HELP = {
    "home": "Состояние активного проекта и следующий разумный шаг.",
    "projects": "Создать новый проект или открыть переносимый PetroLab.",
    "search": "Найти анализы, образцы, шлифы, изображения и источники во всех проектах.",
    "samples": "Образцы, их паспорт и связанные данные.",
    "slides": "Фотографии шлифов, поля и привязанные аналитические точки.",
    "analyses": "Таблица импортированных анализов, ручной отбор, QC, расчёты и правки.",
    "linked_views": "Несколько синхронизированных научных диаграмм и одна общая выборка.",
    "add_data": "Добавить Excel/CSV, изображения и привязать их к точкам.",
}


def navigate(route: str) -> None:
    if route in ROUTE_LABELS:
        st.session_state["nav_route"] = route
        st.session_state["_scroll_to_top_pending"] = True


@st.cache_data(ttl=6 * 60 * 60, show_spinner=False)
def _available_update(installed_version: str) -> str | None:
    return available_update(installed_version)


def _render_update_notice(installed_version: str) -> None:
    if not bool(load_settings().get("check_updates_automatically", True)):
        return
    if not st.session_state.get("_petrolab_first_paint_complete"):
        st.session_state["_petrolab_first_paint_complete"] = True
        return
    remote_version = _available_update(installed_version)
    if remote_version is None:
        return
    with st.expander(f"Доступна v{remote_version}", expanded=False):
        st.caption("Закройте программу и запустите UPDATE_PETROLAB.bat. Данные не изменятся.")
        if st.button("Как обновить", key="sidebar_open_updates", width="stretch"):
            navigate("updates")
            st.rerun()


def _render_selection_tray() -> None:
    selection = read_selection()
    if not selection.analysis_ids:
        return
    with st.expander(f"Выборка · {selection.count}", expanded=False):
        st.caption(selection.label or f"Источник: {selection.origin or 'текущий экран'}")
        if st.button("Показать на графиках", key="sidebar_selection_to_linked", width="stretch"):
            st.session_state["selection_analysis_ids"] = list(selection.analysis_ids)
            st.session_state["active_selection_analysis_ids"] = list(selection.analysis_ids)
            navigate("linked_views")
            st.rerun()
        if st.button("Очистить", key="sidebar_selection_clear", width="stretch"):
            clear_selection()
            st.session_state["selection_analysis_ids"] = []
            st.session_state["active_selection_analysis_ids"] = []
            st.rerun()


def render_sidebar(version: str) -> str:
    st.markdown('<div class="petrolab-sidebar-brand">PetroLab</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="petrolab-sidebar-version">v{version} · локальные данные</div>', unsafe_allow_html=True)

    projects = list_projects()
    if projects:
        by_id = {int(row["id"]): row for row in projects}
        ids = list(by_id)
        current_id = active_project_id()
        active_id = current_id if current_id in by_id else ids[0]
        if st.session_state.get("sidebar_project") != active_id:
            st.session_state["sidebar_project"] = active_id
        selected = st.selectbox(
            "Активный проект",
            ids,
            format_func=lambda value: str(by_id[int(value)]["name"]),
            key="sidebar_project",
            label_visibility="collapsed",
        )
        set_active_project(int(selected))
        datasets = list_accessible_datasets(int(selected))
        rows = sum(int(item.get("row_count") or 0) for item in datasets)
        st.caption(f"{len(datasets)} наборов · {rows:,} анализов".replace(",", " "))
        st.session_state["_sidebar_project_ready"] = True
    else:
        st.session_state.pop("_sidebar_project_ready", None)
        st.caption("Проект ещё не создан")

    current = str(st.session_state.get("nav_route", "home"))
    if current not in ROUTE_LABELS:
        current = "home"
        st.session_state["nav_route"] = current

    for section, entries in PRIMARY_NAV_SECTIONS.items():
        if section:
            st.markdown(f'<div class="petrolab-nav-section">{section}</div>', unsafe_allow_html=True)
        for route, label in entries:
            if st.button(
                label,
                key=f"nav_{route}",
                type="primary" if route == current else "secondary",
                width="stretch",
                help=NAV_HELP.get(route),
            ):
                navigate(route)
                st.rerun()

    _render_selection_tray()

    secondary_routes = {route for entries in SECONDARY_NAV_SECTIONS.values() for route, _ in entries}
    with st.expander("Ещё", expanded=current in secondary_routes):
        for section, entries in SECONDARY_NAV_SECTIONS.items():
            st.markdown(f'<div class="petrolab-nav-section">{section}</div>', unsafe_allow_html=True)
            for route, label in entries:
                if st.button(
                    label,
                    key=f"nav_{route}",
                    type="primary" if route == current else "secondary",
                    width="stretch",
                ):
                    navigate(route)
                    st.rerun()

    st.markdown('<div class="petrolab-nav-section">Система</div>', unsafe_allow_html=True)
    for route, label in SYSTEM_NAVIGATION:
        if st.button(label, key=f"nav_{route}", type="primary" if route == current else "secondary", width="stretch"):
            navigate(route)
            st.rerun()

    _render_update_notice(version)
    return current