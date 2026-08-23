from __future__ import annotations

import streamlit as st

from petrolab.db import list_accessible_datasets, list_projects
from petrolab.settings_service import load_settings
from petrolab.ui.project_context import active_project_id, set_active_project
from petrolab.update_checker import available_update


# The daily menu is grouped by the question that a researcher has at the moment.
# This prevents "find" from looking like a second version of the analyses table.
PRIMARY_NAV_SECTIONS = {
    "Начать": [
        ("home", "Обзор"),
        ("add_data", "Добавить данные"),
        ("search", "Найти в проектах"),
    ],
    "Материал": [
        ("samples", "Образцы"),
        ("slides", "Шлифы"),
        ("rocks", "Породы"),
    ],
    "Анализы и графики": [
        ("analyses", "Анализы"),
        ("plots", "Графики"),
    ],
}
PRIMARY_NAVIGATION = [entry for entries in PRIMARY_NAV_SECTIONS.values() for entry in entries]

SECONDARY_NAV_SECTIONS = {
    "Выборки и файлы": [
        ("selections", "Рабочие выборки"),
        ("images", "Изображения"),
        ("database", "Вся база"),
        ("measurements", "Объекты и измерения"),
        ("attention", "Требует внимания"),
        ("workflow", "Рабочий процесс"),
    ],
    "Научные инструменты": [
        ("ternary", "Треугольные диаграммы"),
        ("linked_views", "Связанные представления"),
        ("science_plots", "Научные диаграммы"),
        ("statistics", "Статистика"),
        ("equilibrium", "Равновесные пары"),
        ("distribution", "Распределение элементов"),
        ("thermobarometry", "Термобарометрия"),
        ("mixed_minerals", "Фазы и выбросы"),
        ("batch_edit", "Массовые действия"),
        ("formulae", "Расчёты"),
        ("generations", "Поколения"),
    ],
    "Публикация": [
        ("figure_recipes", "Figure Recipe"),
        ("article_tables", "Таблицы для статьи"),
        ("export", "Экспорт"),
    ],
    "Администрирование": [
        ("sources", "Новые анализы"),
        ("sessions", "Аналитические сессии"),
        ("intake", "Источники и литература"),
        ("minerals", "Минералогические модули"),
        ("projects", "Проекты"),
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
    "samples": "Физические Sample: паспорт, местность и связанные с ними данные.",
    "search": "Когда известен хотя бы фрагмент названия: найти Sample, минерал, точку, породу или изображение во всех проектах.",
    "plots": "Построить график по текущей выборке или набору анализов.",
    "slides": "Фотографии шлифов, прямоугольные поля, точки и привязанные BSE.",
    "rocks": "Валовая химия, изотопия, фотографии и связи с Sample.",
    "analyses": "Рабочая таблица импортированных анализов: фильтр, QC, расчёты и правки.",
    "add_data": "Добавить анализы, фотографии, источник или полевые Sample.",
    "measurements": "Физические зёрна и точки с отдельными результатами разных методов.",
    "database": "Полный каталог данных активного проекта или всех проектов.",
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
    st.markdown('<div class="petrolab-nav-section">Активный проект</div>', unsafe_allow_html=True)
    if projects:
        by_id = {int(row["id"]): row for row in projects}
        ids = list(by_id)
        current_id = active_project_id()
        active_id = current_id if current_id in by_id else ids[0]
        if st.session_state.get("sidebar_project") != active_id:
            st.session_state["sidebar_project"] = active_id
        selected = st.selectbox(
            "Активный проект", ids,
            format_func=lambda value: str(by_id[int(value)]["name"]),
            key="sidebar_project",
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
    for section, entries in PRIMARY_NAV_SECTIONS.items():
        st.markdown(f'<div class="petrolab-nav-section">{section}</div>', unsafe_allow_html=True)
        for route, label in entries:
            if st.button(label, key=f"nav_{route}", type="primary" if route == current else "secondary", width="stretch", help=NAV_HELP.get(route)):
                navigate(route)
                st.rerun()

    secondary_routes = {route for entries in SECONDARY_NAV_SECTIONS.values() for route, _ in entries}
    with st.expander("Дополнительные инструменты", expanded=current in secondary_routes):
        for section, entries in SECONDARY_NAV_SECTIONS.items():
            st.markdown(f'<div class="petrolab-nav-section">{section}</div>', unsafe_allow_html=True)
            for route, label in entries:
                if st.button(label, key=f"nav_{route}", type="primary" if route == current else "secondary", width="stretch", help=NAV_HELP.get(route)):
                    navigate(route)
                    st.rerun()

    st.markdown('<div class="petrolab-nav-section">Система</div>', unsafe_allow_html=True)
    for route, label in SYSTEM_NAVIGATION:
        if st.button(label, key=f"nav_{route}", type="primary" if route == current else "secondary", width="stretch", help=NAV_HELP.get(route)):
            navigate(route)
            st.rerun()
    return current
