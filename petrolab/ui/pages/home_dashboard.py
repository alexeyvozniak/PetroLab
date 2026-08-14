from __future__ import annotations

import pandas as pd
import streamlit as st

from petrolab.db import list_accessible_datasets
from petrolab.derived import formula_status
from petrolab.minerals.registry import labels as mineral_labels
from petrolab.project_health import project_health
from petrolab.repositories.image_repository import list_image_records
from petrolab.services.rock_service import rock_summary
from petrolab.ui.layout import render_badges, render_page_header, render_section_header
from petrolab.ui.navigation import navigate
from petrolab.ui.project_context import active_project


def _go(route: str) -> None:
    navigate(route)
    st.rerun()


def render_home_dashboard_page() -> None:
    project = active_project()
    if project is None:
        render_page_header("ПетроЛаб", "Локальное научное рабочее пространство.", eyebrow="Научный дашборд")
        st.info("Создайте первый проект. После этого PetroLab сам предложит следующий разумный шаг.")
        if st.button("Создать проект", type="primary"):
            _go("projects")
        return

    project_id = int(project["id"])
    datasets = list_accessible_datasets(project_id)
    analyses = sum(int(item.get("row_count") or 0) for item in datasets)
    images = list_image_records(project_id=project_id)
    stale = sum(int(formula_status(int(item["id"])).stale_rows) for item in datasets)
    health = project_health(project_id)
    context = f"{project['name']} · {len(datasets)} наборов · {analyses:,} анализов".replace(",", " ")
    render_page_header(
        "ПетроЛаб",
        "Минералогия, геохимия, изображения, расчёты и публикационные данные в одном рабочем пространстве.",
        eyebrow="Научный дашборд",
        context=context,
    )

    render_section_header("Что делать сейчас", "PetroLab предлагает путь, но любой модуль можно открыть напрямую")
    actions = [
        ("01 · Рабочий процесс", "Продолжить выбранный набор от контекста до первых графиков", "workflow"),
        ("02 · Добавить данные", "Свои анализы, статья/коллега или полевые Sample", "add_data"),
        ("03 · Требует внимания", f"Важных хвостов: {health['required_count']}", "attention"),
        ("04 · Массовые действия", "Исправить фазу, Generation или морфологию у группы точек", "batch_edit"),
    ]
    cols = st.columns(4)
    for index, (col, (title, note, route)) in enumerate(zip(cols, actions)):
        with col:
            st.markdown(f"**{title}**")
            st.caption(note)
            if st.button(
                "Открыть", key=f"home_{route}",
                type="primary" if index == 0 else "secondary", width="stretch",
            ):
                _go(route)

    render_section_header("Состояние проекта")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Анализов", f"{analyses:,}".replace(",", " "))
    m2.metric("Наборов", len(datasets))
    m3.metric("Изображений", len(images))
    m4.metric("Порядок", f"{health['score']}%")
    render_badges([
        (f"{len({item['mineral_key'] for item in datasets})} минералогических модулей", "accent"),
        (f"{len(rock_summary(project_id))} пород", "neutral"),
        ("Расчёты актуальны" if stale == 0 else f"Пересчитать формулы · {stale}", "success" if stale == 0 else "warning"),
        ("Нет важных хвостов" if not health["required_count"] else f"Требуют внимания · {health['required_count']}", "success" if not health["required_count"] else "warning"),
    ])
    if health["required_count"]:
        if st.button("Разобрать важные хвосты", key="home_attention_now", width="stretch"):
            _go("attention")

    render_section_header("Последние наборы", "Активный проект")
    if not datasets:
        st.info("В проекте пока нет аналитических наборов.")
        if st.button("Добавить первые данные", type="primary", key="home_first_data"):
            _go("add_data")
        return
    view = pd.DataFrame(datasets)[["name", "mineral_key", "row_count", "source_filename", "source_sheet", "source_kind"]].copy()
    view["mineral_key"] = view["mineral_key"].map(mineral_labels()).fillna(view["mineral_key"])
    view.columns = ["Набор", "Минерал", "Строк", "Источник", "Лист", "Связь"]
    st.dataframe(view.head(12), width="stretch", hide_index=True, height=390)
