from __future__ import annotations

import streamlit as st

from petrolab.db import list_accessible_datasets, list_projects
from petrolab.settings_service import load_settings
from petrolab.ui.project_context import active_project_id, set_active_project
from petrolab.ui.work_context import clear_work_context, get_work_context
from petrolab.update_checker import available_update


DAILY_NAV = [
    ("home", "Главная"),
    ("workspace", "Рабочий стол"),
    ("thin_section", "Работать со шлифом"),
    ("add_data", "Добавить данные"),
    ("database", "Вся база"),
    ("plots", "XY-диаграммы"),
    ("article_tables", "Таблицы для статьи"),
    ("attention", "Требует внимания"),
]

TOOL_SECTIONS = {
    "Сценарии": [
        ("compare", "Сравнить данные"),
        ("calculate", "Посчитать"),
        ("publish", "Подготовить рисунок / таблицу"),
    ],
    "Данные": [
        ("search", "Глобальный поиск"),
        ("quick_import", "Быстрый импорт"),
        ("workflow", "Рабочий процесс"),
        ("analyses", "База анализов"),
        ("sources", "Новые анализы"),
        ("sessions", "Аналитические сессии"),
        ("intake", "Источники и литература"),
    ],
    "Материалы": [
        ("images", "Изображения"),
        ("slides", "Шлифы и поля · расширенно"),
        ("measurements", "Образцы и измерения"),
        ("mixed_minerals", "Фазы и выбросы"),
        ("batch_edit", "Массовые действия"),
        ("formulae", "Расчёты"),
        ("generations", "Поколения"),
        ("minerals", "Минералогические модули"),
        ("rocks", "Породы"),
    ],
    "Исследование": [
        ("thermobarometry", "Термодинамика"),
        ("ternary", "Треугольные"),
        ("science_plots", "Научные диаграммы"),
        ("statistics", "Статистика"),
        ("equilibrium", "Равновесные пары"),
        ("distribution", "Распределение элементов"),
    ],
    "Публикация": [
        ("export", "Экспорт"),
    ],
    "Система": [
        ("projects", "Проекты"),
        ("collaboration", "Совместная работа"),
        ("change_log", "История правок данных"),
        ("settings", "Настройки"),
        ("help", "Справка"),
        ("updates", "Что нового"),
    ],
}

_ALL_ENTRIES = DAILY_NAV + [item for entries in TOOL_SECTIONS.values() for item in entries]
ROUTE_LABELS = {route: label for route, label in _ALL_ENTRIES}


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


def _nav_button(route: str, label: str, current: str, *, prefix: str = "nav") -> None:
    if st.button(
        label,
        key=f"{prefix}_{route}",
        type="primary" if route == current else "secondary",
        width="stretch",
    ):
        st.session_state["nav_route"] = route
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

        context = get_work_context(int(selected))
        if context:
            context_col, clear_col = st.columns([5, 1])
            with context_col:
                st.caption(f"Сейчас: {context.get('label', '')}")
            with clear_col:
                if st.button("×", key="sidebar_clear_context", help="Сбросить текущий контекст"):
                    clear_work_context()
                    st.rerun()

        st.markdown('<div class="petrolab-nav-section">Поиск</div>', unsafe_allow_html=True)
        search = st.text_input(
            "Найти везде",
            key="sidebar_object_search",
            label_visibility="collapsed",
            placeholder="🔎 Найти везде…",
        )
        if st.button("Найти", key="sidebar_object_search_go", width="stretch"):
            st.session_state["global_search_query_pending"] = str(search or "").strip()
            st.session_state["global_search_scope_pending"] = "all"
            st.session_state["nav_route"] = "search"
            st.rerun()
    else:
        st.session_state.pop("_sidebar_project_ready", None)
        st.caption("Создайте первый проект")

    _render_update_notice(version)

    current = str(st.session_state.get("nav_route", "home"))
    if current not in ROUTE_LABELS:
        current = "home"
        st.session_state["nav_route"] = current

    st.markdown('<div class="petrolab-nav-section">Основное</div>', unsafe_allow_html=True)
    for route, label in DAILY_NAV:
        _nav_button(route, label, current, prefix="daily_nav")

    daily_routes = {route for route, _ in DAILY_NAV}
    with st.expander("Все инструменты", expanded=current not in daily_routes):
        for section, entries in TOOL_SECTIONS.items():
            st.markdown(f'<div class="petrolab-nav-section">{section}</div>', unsafe_allow_html=True)
            for route, label in entries:
                _nav_button(route, label, current, prefix="tool_nav")
    return current
