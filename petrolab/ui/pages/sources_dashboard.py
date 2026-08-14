from __future__ import annotations

from pathlib import Path

import streamlit as st

from petrolab.db import list_datasets
from petrolab.io_utils import sha256_file
from petrolab.services.import_service import refresh_dataset_from_source
from petrolab.sources import source_status
from petrolab.ui.layout import render_badges, render_hint, render_page_header
from petrolab.ui.pages import sources as legacy
from petrolab.ui.project_context import active_project


def _managed_copy_status(dataset: dict) -> tuple[str, str]:
    path_text = str(dataset.get("source_path") or "")
    if not path_text:
        return "рабочая копия PetroLab", "Внутренняя копия без внешнего пути. Обратная запись в пользовательский оригинал недоступна."
    path = Path(path_text)
    if not path.exists():
        return "рабочая копия не найдена", str(path)
    stored_hash = str(dataset.get("source_sha256") or "")
    current_hash = sha256_file(path)
    if stored_hash and current_hash != stored_hash:
        return "рабочая копия изменена", str(path)
    return "рабочая копия PetroLab", str(path)


def _render_source_statuses(project_id: int) -> None:
    datasets = list_datasets(project_id)
    if not datasets:
        st.caption("Источников пока нет.")
        return
    for dataset in datasets:
        managed = str(dataset.get("source_kind") or "") == "managed_copy"
        status, detail = _managed_copy_status(dataset) if managed else source_status(dataset)
        with st.container(border=True):
            left, right = st.columns([4, 1])
            with left:
                st.markdown(f"**{dataset['name']}**")
                render_badges([
                    (status, "neutral" if managed else ("success" if status == "актуален" else "warning")),
                    ("внутренняя копия" if managed else "linked source", "neutral"),
                ])
                st.caption(detail)
                if managed:
                    st.caption("Это внутренняя рабочая копия PetroLab. Изменения базы не записываются в пользовательский оригинал.")
            with right:
                if not managed and status == "изменён вне ПетроЛаба":
                    if st.button("Обновить из файла", key=f"refresh_source_{dataset['id']}", width="stretch"):
                        try:
                            result = refresh_dataset_from_source(int(dataset["id"]))
                            st.success(
                                f"Обновлено строк: {result.row_count}; сохранено ID: {result.reused_count}; "
                                f"новых: {result.new_count}; удалённых: {result.removed_count}."
                            )
                            st.rerun()
                        except Exception as exc:
                            st.error(f"Обновление источника остановлено: {exc}")


def render_sources_dashboard_page() -> None:
    project = active_project()
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
        "Источники и рабочие копии",
    ])
    with linked:
        render_hint("PetroLab запомнит путь. Для XLSX/XLSM возможна безопасная обратная синхронизация.")
        legacy._render_linked_import(int(project["id"]))
    with uploaded:
        render_hint("PetroLab сохранит внутреннюю рабочую копию файла. Она не является sync-target пользовательского оригинала.")
        legacy._render_uploaded_import(int(project["id"]))
    with sources:
        _render_source_statuses(int(project["id"]))
