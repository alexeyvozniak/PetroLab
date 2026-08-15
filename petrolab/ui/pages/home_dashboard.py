from __future__ import annotations

import pandas as pd
import streamlit as st

from petrolab.db import list_accessible_datasets
from petrolab.derived import formula_status
from petrolab.minerals.registry import labels as mineral_labels
from petrolab.project_health import project_health
from petrolab.ui.layout import render_badges, render_page_header, render_section_header
from petrolab.ui.navigation import navigate
from petrolab.ui.project_context import active_project


def _go(route: str) -> None:
    navigate(route)
    st.rerun()


def render_home_dashboard_page() -> None:
    project = active_project()
    if project is None:
        render_page_header("ПетроЛаб", "Локальная научная рабочая среда.", eyebrow="Рабочая среда")
        st.info("Создайте первый проект.")
        if st.button("Создать проект", type="primary"):
            _go("projects")
        return

    project_id = int(project["id"])
    datasets = list_accessible_datasets(project_id)
    analyses = sum(int(item.get("row_count") or 0) for item in datasets)
    stale = sum(int(formula_status(int(item["id"])).stale_rows) for item in datasets)
    health = project_health(project_id)
    context = f"{project['name']} · {len(datasets)} наборов · {analyses:,} анализов".replace(",", " ")
    render_page_header(
        "ПетроЛаб",
        "Работа с объектами, анализами, изображениями, расчётами и публикационными данными.",
        eyebrow="Рабочая среда",
        context=context,
    )

    render_section_header("Открыть")
    actions = [
        ("Рабочий стол", "Один Sample или массив со связанными данными", "workspace"),
        ("Добавить данные", "Импорт анализов, статьи/коллеги или полевые Sample", "add_data"),
        ("Поиск", "Sample, минерал, Generation, источник, зерно или точка", "search"),
        ("Требует внимания", f"Необработанных обязательных пунктов: {health['required_count']}", "attention"),
    ]
    cols = st.columns(4)
    for index, (col, (title, note, route)) in enumerate(zip(cols, actions)):
        with col:
            if st.button(
                title,
                key=f"home_{route}",
                type="primary" if index == 0 else "secondary",
                width="stretch",
                help=note,
            ):
                _go(route)

    render_section_header("Проект")
    render_badges([
        (f"{len(datasets)} наборов", "neutral"),
        (f"{analyses:,} анализов".replace(",", " "), "neutral"),
        ("Формулы актуальны" if stale == 0 else f"Пересчитать · {stale}", "success" if stale == 0 else "warning"),
        ("Нет обязательных хвостов" if not health["required_count"] else f"Требует внимания · {health['required_count']}", "success" if not health["required_count"] else "warning"),
    ])
    if health["required_count"]:
        if st.button("Разобрать", key="home_attention_now"):
            _go("attention")

    render_section_header("Недавние данные", "Наборы активного проекта")
    if not datasets:
        st.info("В проекте пока нет аналитических наборов.")
        if st.button("Добавить первые данные", type="primary", key="home_first_data"):
            _go("add_data")
        return
    view = pd.DataFrame(datasets)[["name", "mineral_key", "row_count", "source_filename", "source_sheet", "source_kind"]].copy()
    view["mineral_key"] = view["mineral_key"].map(mineral_labels()).fillna(view["mineral_key"])
    view.columns = ["Набор", "Минерал", "Строк", "Источник", "Лист", "Связь"]
    st.dataframe(view.head(12), width="stretch", hide_index=True, height=390)
