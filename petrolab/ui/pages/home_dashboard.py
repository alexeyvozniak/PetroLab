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
from petrolab.ui.work_context import list_recent_work_contexts


def _go(route: str) -> None:
    navigate(route)
    st.rerun()


def _open_recent(item: dict) -> None:
    kind = str(item.get("kind") or "")
    selector = item.get("selector") or {}
    if kind == "sample":
        st.session_state["workspace_mode"] = "Sample"
        st.session_state["workspace_query_pending"] = str(selector.get("sample") or item.get("label") or "")
        _go("workspace")
    if kind == "dataset":
        st.session_state["workspace_mode"] = "Массив данных"
        st.session_state["workspace_query_pending"] = str(item.get("label") or "")
        _go("workspace")
    if kind == "thin_section":
        thin_section_id = selector.get("thin_section_id")
        if thin_section_id is not None:
            st.session_state["thin_section_focus_id_pending"] = int(thin_section_id)
        _go("thin_section")
    _go("workspace")


def _scenario_card(title: str, note: str, route: str, *, primary: bool = False) -> None:
    with st.container(border=True):
        st.markdown(f"**{title}**")
        st.caption(note)
        if st.button(
            "Открыть",
            key=f"home_{route}",
            type="primary" if primary else "secondary",
            width="stretch",
        ):
            _go(route)


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
        "Что вы хотите сделать сегодня?",
        "Выберите задачу — PetroLab откроет короткий путь, но все инструменты останутся доступны напрямую.",
        eyebrow="ПетроЛаб",
        context=context,
    )

    first_row = st.columns(4)
    scenarios = [
        ("Исследовать объект", "Один Sample или массив: анализы, изображения, шлифы, расчёты и источники.", "workspace"),
        ("Добавить данные", "Excel/CSV, изображения, статьи или полевые объекты без лишних шагов.", "add_data"),
        ("Работать со шлифом", "PPL/XPL/BSE, точки анализов, области и контуры зерен прямо на изображении.", "thin_section"),
        ("Сравнить данные", "Собрать два или больше массивов и включать/выключать их как отдельные серии.", "compare"),
    ]
    for index, (col, (title, note, route)) in enumerate(zip(first_row, scenarios)):
        with col:
            _scenario_card(title, note, route, primary=index == 0)

    second_row = st.columns(3)
    more = [
        ("Посчитать", "Формулы/APFU, мономинеральная и минерал–расплав термодинамика, классификации.", "calculate"),
        ("Подготовить рисунок или таблицу", "XY, треугольные диаграммы, публикационные таблицы и экспорт.", "publish"),
        ("Найти", "Одна лупа для Sample, точки, зерна, минерала, массива, изображения и источника.", "search"),
    ]
    for col, (title, note, route) in zip(second_row, more):
        with col:
            _scenario_card(title, note, route)

    recent = list_recent_work_contexts(project_id, limit=4)
    if recent:
        render_section_header("Продолжить", "Последние объекты работы сохраняются между запусками")
        cols = st.columns(len(recent))
        kind_labels = {"sample": "Sample", "dataset": "Массив", "thin_section": "Шлиф"}
        for index, (col, item) in enumerate(zip(cols, recent)):
            with col:
                with st.container(border=True):
                    st.caption(kind_labels.get(str(item.get("kind")), "Объект"))
                    st.markdown(f"**{item.get('label', '')}**")
                    if st.button("Продолжить", key=f"home_recent_{index}", width="stretch"):
                        _open_recent(item)

    render_section_header("Проект")
    render_badges([
        (f"{len(datasets)} наборов", "neutral"),
        (f"{analyses:,} анализов".replace(",", " "), "neutral"),
        ("Формулы актуальны" if stale == 0 else f"Пересчитать · {stale}", "success" if stale == 0 else "warning"),
        ("Нет обязательных хвостов" if not health["required_count"] else f"Требует внимания · {health['required_count']}", "success" if not health["required_count"] else "warning"),
    ])
    if health["required_count"] and st.button("Разобрать", key="home_attention_now"):
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
