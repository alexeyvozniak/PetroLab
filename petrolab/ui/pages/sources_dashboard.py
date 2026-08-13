from __future__ import annotations

import streamlit as st

from petrolab.db import list_projects
from petrolab.ui.layout import render_badges, render_page_header
from petrolab.ui.pages import sources as legacy


def _active_project() -> dict | None:
    projects = list_projects()
    if not projects:
        return None
    by_id = {int(project["id"]): project for project in projects}
    ids = list(by_id)
    try:
        project_id = int(st.session_state.get("active_project_id", ids[0]))
    except (TypeError, ValueError):
        project_id = ids[0]
    if project_id not in by_id:
        project_id = ids[0]
    st.session_state["active_project_id"] = project_id
    return by_id[project_id]


def render_sources_dashboard_page() -> None:
    project = _active_project()
    context = str(project["name"]) if project else "Проект не выбран"
    render_page_header(
        "Импорт и источники",
        "Добавляйте Excel/CSV, настраивайте каждый лист отдельно и сохраняйте происхождение каждой аналитической колонки.",
        eyebrow="Данные",
        context=context,
    )
    if project is None:
        st.info("Сначала создайте проект.")
        return
    render_badges([
        ("1 · Файл", "accent"), ("2 · Листы", "neutral"),
        ("3 · Сопоставление", "neutral"), ("4 · Проверка", "neutral"),
        ("5 · Импорт", "neutral"),
    ])
    linked, uploaded, sources = st.tabs([
        "Связать файл на компьютере",
        "Загрузить рабочую копию",
        "Связанные источники",
    ])
    with linked:
        st.caption("PetroLab запомнит путь. Для XLSX/XLSM возможна безопасная обратная синхронизация.")
        legacy._render_linked_import(int(project["id"]))
    with uploaded:
        st.caption("PetroLab сохранит управляемую локальную копию файла внутри проекта.")
        legacy._render_uploaded_import(int(project["id"]))
    with sources:
        legacy._render_source_statuses(int(project["id"]))
