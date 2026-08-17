from __future__ import annotations

import streamlit as st

from petrolab.dataset_visibility import visible_working_datasets
from petrolab.db import list_accessible_datasets, list_projects
from petrolab.settings_service import load_settings
from petrolab.ui.navigation_state import can_go_back, go_back as restore_previous_route, push_current
from petrolab.ui.project_context import active_project_id, set_active_project
from petrolab.ui.work_context import clear_work_context, get_work_context
from petrolab.update_checker import available_update


# Nine task-oriented entries are the normal navigation. Implementation pages
# remain addressable for old recipes/internal links, but they are not menu items.
PRIMARY_NAV = [
    ("home", "Главная"),
    ("workspace", "Данные"),
    ("plots", "Графики"),
    ("statistics", "Статистика"),
    ("thin_section", "Шлифы и изображения"),
    ("calculate", "Расчёты"),
    ("publish", "Публикация"),
    ("search", "Поиск"),
    ("settings", "Настройки"),
]
DAILY_NAV = PRIMARY_NAV

TOOL_SECTIONS = {
    "Данные": [
        ("add_data", "Добавить данные"),
        ("sessions", "Аналитические сессии"),
        ("measurements", "Образцы и измерения"),
        ("mixed_minerals", "Фазы и выбросы"),
        ("batch_edit", "Массовые действия"),
        ("generations", "Поколения"),
    ],
    "Исследование": [
        ("multi_panel", "Сравнить на нескольких диаграммах"),
        ("grain_profile", "Профиль по зерну"),
        ("whole_rock_compare", "Породы + литература"),
        ("thermobarometry", "Термодинамика"),
        ("ternary", "Треугольные диаграммы"),
        ("science_plots", "Научные диаграммы"),
        ("equilibrium", "Равновесные пары"),
        ("distribution", "Распределение элементов"),
        ("composite_points", "Совместить EDS / EPMA / LA"),
    ],
    "Публикация": [
        ("article_tables", "Таблицы для статьи"),
        ("publication_composer", "Собрать рисунок A/B/C"),
        ("export", "Экспорт"),
    ],
    "Система": [
        ("projects", "Проекты"),
        ("collaboration", "Совместная работа"),
        ("change_log", "История правок данных"),
        ("attention", "Требует внимания"),
        ("help", "Справка"),
        ("updates", "Что нового"),
    ],
}

# Compatibility-only routes. They stay routable because old recipes, deep links,
# and internal actions may still target them, but they are deliberately absent
# from the normal sidebar.
_HIDDEN_ROUTE_LABELS = {
    "database": "Вся база",
    "compare": "Сравнить данные",
    "quick_import": "Быстрый импорт",
    "workflow": "Рабочий процесс",
    "analyses": "База анализов",
    "sources": "Новые анализы",
    "intake": "Источники и литература",
    "images": "Изображения",
    "slides": "Шлифы и поля",
    "formulae": "Формулы / APFU",
    "minerals": "Минералогические модули",
    "rock_workspace": "Породы",
    "rocks": "Редактор пород",
}

_ALL_VISIBLE_ENTRIES = PRIMARY_NAV + [item for entries in TOOL_SECTIONS.values() for item in entries]
ROUTE_LABELS = {route: label for route, label in _ALL_VISIBLE_ENTRIES}
ROUTE_LABELS.update(_HIDDEN_ROUTE_LABELS)


def navigate(route: str, *, record_history: bool = True) -> None:
    if route not in ROUTE_LABELS:
        return
    current = str(st.session_state.get("nav_route", "home"))
    if record_history and current in ROUTE_LABELS and current != route:
        push_current(st.session_state, current_route=current)
    if current != route:
        # Streamlit keeps the scroll offset across reruns. That is useful inside one
        # page, but surprising when the route changes (for example thin section ->
        # plots could open halfway down the new page). The app consumes this flag
        # after the destination page has rendered and resets the main viewport once.
        st.session_state["_scroll_to_top_pending"] = True
    st.session_state["nav_route"] = route


def go_back() -> str | None:
    current = str(st.session_state.get("nav_route", "home"))
    restored = restore_previous_route(
        st.session_state,
        current_route=current,
        valid_routes=set(ROUTE_LABELS),
    )
    if restored is not None and restored != current:
        st.session_state["_scroll_to_top_pending"] = True
    return restored


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
        navigate(route)
        st.rerun()


def render_sidebar(version: str) -> str:
    st.markdown(
        '<div class="petrolab-sidebar-brand-block">'
        '<div class="petrolab-sidebar-brand">◈ ПетроЛаб</div>'
        f'<div class="petrolab-sidebar-version">v{version} | локальные данные</div>'
        '</div>',
        unsafe_allow_html=True,
    )

    current = str(st.session_state.get("nav_route", "home"))
    if current not in ROUTE_LABELS:
        current = "home"
        st.session_state["nav_route"] = current

    if can_go_back(st.session_state):
        if st.button("← Назад", key="sidebar_go_back", width="stretch", help="Вернуться в предыдущий рабочий контекст"):
            if go_back() is not None:
                st.rerun()

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
        datasets = visible_working_datasets(list_accessible_datasets(int(selected)))
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

        search = st.text_input(
            "Найти везде",
            key="sidebar_object_search",
            label_visibility="collapsed",
            placeholder="🔎 Найти везде…",
        )
        if st.button("Найти", key="sidebar_object_search_go", width="stretch"):
            st.session_state["global_search_query_pending"] = str(search or "").strip()
            st.session_state["global_search_scope_pending"] = "all"
            navigate("search")
            st.rerun()
    else:
        st.session_state.pop("_sidebar_project_ready", None)
        st.caption("Создайте первый проект")

    _render_update_notice(version)

    current = str(st.session_state.get("nav_route", "home"))
    st.markdown('<div class="petrolab-nav-section">Основное</div>', unsafe_allow_html=True)
    for route, label in PRIMARY_NAV:
        _nav_button(route, label, current, prefix="primary_nav")

    primary_routes = {route for route, _ in PRIMARY_NAV}
    visible_advanced_routes = {route for entries in TOOL_SECTIONS.values() for route, _ in entries}
    with st.expander("Дополнительно", expanded=current in visible_advanced_routes and current not in primary_routes):
        for section, entries in TOOL_SECTIONS.items():
            st.markdown(f'<div class="petrolab-nav-section">{section}</div>', unsafe_allow_html=True)
            for route, label in entries:
                _nav_button(route, label, current, prefix="tool_nav")
    return current
