from __future__ import annotations

import streamlit as st

from petrolab.ui.components import render_project_selector
from petrolab.ui.layout import render_badges, render_page_header
from petrolab.ui.pages import sources as legacy


def render_sources_dashboard_page() -> None:
    render_page_header(
        "Импорт и источники",
        "Добавляйте Excel/CSV, настраивайте каждый лист отдельно и сохраняйте происхождение каждой аналитической колонки.",
        eyebrow="Данные",
    )
    project = render_project_selector("import_project")
    if project is None:
        return
    render_badges([
        ("1 · Файл", "accent"),
        ("2 · Листы", "neutral"),
        ("3 · Сопоставление", "neutral"),
        ("4 · Проверка", "neutral"),
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
