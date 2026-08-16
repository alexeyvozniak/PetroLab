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


def _open_dataset(dataset: dict) -> None:
    st.session_state["workspace_mode"] = "Массив данных"
    st.session_state["workspace_query_pending"] = str(dataset.get("name") or "")
    _go("workspace")


def _quick_actions() -> None:
    render_section_header("Быстрые действия", "Основные задачи без перехода через технические разделы")
    actions = [
        ("Данные", "workspace", True),
        ("Добавить", "add_data", False),
        ("Графики", "plots", False),
        ("Шлифы", "thin_section", False),
        ("Расчёты", "calculate", False),
        ("Публикация", "publish", False),
        ("Поиск", "search", False),
    ]
    cols = st.columns(len(actions))
    for col, (label, route, primary) in zip(cols, actions):
        if col.button(
            label,
            key=f"home_{route}",
            type="primary" if primary else "secondary",
            width="stretch",
        ):
            _go(route)


def _recent_work(project_id: int) -> None:
    recent = list_recent_work_contexts(project_id, limit=8)
    if not recent:
        return
    render_section_header("Продолжить", "Последние объекты работы сохраняются между запусками")
    kind_labels = {"sample": "Sample", "dataset": "Массив", "thin_section": "Шлиф"}
    view = pd.DataFrame([
        {
            "Тип": kind_labels.get(str(item.get("kind")), "Объект"),
            "Объект": str(item.get("label") or ""),
        }
        for item in recent
    ])
    event = st.dataframe(
        view,
        width="stretch",
        hide_index=True,
        height=min(330, 42 + 35 * len(view)),
        key="home_recent_work_table",
        on_select="rerun",
        selection_mode="single-row",
    )
    try:
        rows = list(event.selection.rows)
    except (AttributeError, TypeError):
        rows = []
    if rows:
        index = int(rows[0])
        if 0 <= index < len(recent):
            _open_recent(recent[index])


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
    context = f"{len(datasets)} наборов · {analyses:,} анализов".replace(",", " ")
    render_page_header(
        str(project["name"]),
        "Данные, связанные представления и научные расчёты в одном рабочем контексте.",
        eyebrow="ПетроЛаб",
        context=context,
    )

    _recent_work(project_id)
    _quick_actions()

    render_section_header("Проект")
    render_badges([
        (f"{len(datasets)} наборов", "neutral"),
        (f"{analyses:,} анализов".replace(",", " "), "neutral"),
        ("Формулы актуальны" if stale == 0 else f"Пересчитать · {stale}", "success" if stale == 0 else "warning"),
        ("Нет обязательных хвостов" if not health["required_count"] else f"Требует внимания · {health['required_count']}", "success" if not health["required_count"] else "warning"),
    ])
    if health["required_count"] and st.button("Разобрать", key="home_attention_now"):
        _go("attention")

    render_section_header("Недавние данные", "Щёлкните строку, чтобы открыть набор на рабочем столе")
    if not datasets:
        st.info("В проекте пока нет аналитических наборов.")
        if st.button("Добавить первые данные", type="primary", key="home_first_data"):
            _go("add_data")
        return
    recent_datasets = list(datasets[:12])
    view = pd.DataFrame(recent_datasets)[["name", "mineral_key", "row_count", "source_filename", "source_sheet", "source_kind"]].copy()
    view["mineral_key"] = view["mineral_key"].map(mineral_labels()).fillna(view["mineral_key"])
    view.columns = ["Набор", "Минерал", "Строк", "Источник", "Лист", "Связь"]
    event = st.dataframe(
        view,
        width="stretch",
        hide_index=True,
        height=390,
        key="home_recent_datasets_table",
        on_select="rerun",
        selection_mode="single-row",
    )
    try:
        rows = list(event.selection.rows)
    except (AttributeError, TypeError):
        rows = []
    if rows:
        index = int(rows[0])
        if 0 <= index < len(recent_datasets):
            _open_dataset(recent_datasets[index])
