from __future__ import annotations

from pathlib import Path

import streamlit as st

from petrolab.db import list_datasets
from petrolab.minerals.registry import MINERALS
from petrolab.services.import_service import (
    import_linked_sheets,
    import_uploaded_sheets,
    list_linked_sheets,
    list_uploaded_sheets,
    preview_linked_source,
    preview_uploaded_source,
    refresh_dataset_from_source,
)
from petrolab.sources import source_status
from petrolab.ui.components import render_project_selector


def render_sources_page() -> None:
    """Render source linking, browser upload, and external-change refresh workflows."""
    st.title("Источники и импорт")
    project = render_project_selector("import_project")
    if project is None:
        return

    linked_tab, upload_tab, sources_tab = st.tabs(
        ["Связать локальный файл", "Загрузить копию", "Связанные источники"]
    )
    with linked_tab:
        _render_linked_import(int(project["id"]))
    with upload_tab:
        _render_uploaded_import(int(project["id"]))
    with sources_tab:
        _render_source_statuses(int(project["id"]))


def _render_linked_import(project_id: int) -> None:
    st.subheader("Локальный Excel с двусторонней синхронизацией")
    st.info(
        "Укажите полный путь к XLSX/XLSM/CSV. Тогда изменения из «Единой базы» "
        "можно записывать обратно в этот файл с резервной копией."
    )
    path_text = st.text_input("Полный путь к Excel/CSV", key="local_source_path")
    header_row = int(
        st.number_input(
            "Строка заголовков",
            min_value=1,
            max_value=200,
            value=1,
            step=1,
            key="local_header_row",
        )
    )
    if not path_text.strip():
        return

    try:
        source_path = Path(path_text).expanduser()
        sheets = list_linked_sheets(source_path)
    except Exception as exc:
        st.error(f"Не удалось открыть источник: {exc}")
        return

    selected_sheets = st.multiselect("Листы для импорта", sheets, default=sheets[:1])
    mineral_key = st.selectbox(
        "Минерал",
        list(MINERALS),
        format_func=lambda key: MINERALS[key].name_ru,
        key="linked_mineral",
    )
    dataset_name = st.text_input("Название набора", value=source_path.stem, key="linked_dataset_name")

    if selected_sheets:
        try:
            preview = preview_linked_source(
                source_path,
                selected_sheets[0],
                header_row,
                mineral_key,
            )
            st.dataframe(preview.head(50), width="stretch", hide_index=True)
        except Exception as exc:
            st.error(f"Не удалось построить предпросмотр: {exc}")

    if st.button(
        "Связать и импортировать выбранные листы",
        type="primary",
        key="link_local",
        disabled=not selected_sheets,
    ):
        try:
            result = import_linked_sheets(
                project_id=project_id,
                path=source_path,
                sheet_names=selected_sheets,
                mineral_key=mineral_key,
                dataset_name=dataset_name,
                header_row=header_row,
            )
            st.success(f"Импортировано наборов: {result.count}.")
            st.rerun()
        except Exception as exc:
            st.error(f"Не удалось импортировать источник: {exc}")


def _render_uploaded_import(project_id: int) -> None:
    st.subheader("Импорт через браузер")
    uploaded = st.file_uploader(
        "Excel или CSV",
        type=["xlsx", "xlsm", "xls", "csv"],
        key="upload_source",
    )
    if uploaded is None:
        return

    file_bytes = uploaded.getvalue()
    header_row = int(
        st.number_input(
            "Строка заголовков",
            min_value=1,
            max_value=200,
            value=1,
            step=1,
            key="upload_header_row",
        )
    )
    try:
        sheets = list_uploaded_sheets(file_bytes, uploaded.name)
    except Exception as exc:
        st.error(f"Не удалось открыть загруженный файл: {exc}")
        return

    selected_sheets = st.multiselect(
        "Листы для импорта",
        sheets,
        default=sheets[:1],
        key="upload_sheets",
    )
    mineral_key = st.selectbox(
        "Минерал",
        list(MINERALS),
        format_func=lambda key: MINERALS[key].name_ru,
        key="upload_mineral",
    )
    dataset_name = st.text_input(
        "Название набора",
        value=Path(uploaded.name).stem,
        key="upload_dataset_name",
    )

    if selected_sheets:
        try:
            preview = preview_uploaded_source(
                file_bytes,
                uploaded.name,
                selected_sheets[0],
                header_row,
                mineral_key,
            )
            st.dataframe(preview.head(50), width="stretch", hide_index=True)
        except Exception as exc:
            st.error(f"Не удалось построить предпросмотр: {exc}")

    if st.button(
        "Импортировать рабочую копию",
        type="primary",
        key="upload_import",
        disabled=not selected_sheets,
    ):
        try:
            result = import_uploaded_sheets(
                project_id=project_id,
                file_bytes=file_bytes,
                filename=uploaded.name,
                sheet_names=selected_sheets,
                mineral_key=mineral_key,
                dataset_name=dataset_name,
                header_row=header_row,
            )
            st.success(f"Импортировано наборов: {result.count}.")
            st.rerun()
        except Exception as exc:
            st.error(f"Не удалось импортировать рабочую копию: {exc}")


def _render_source_statuses(project_id: int) -> None:
    datasets = list_datasets(project_id)
    if not datasets:
        st.info("В проекте пока нет источников.")
        return

    icons = {
        "актуален": "✓",
        "изменён вне ПетроЛаба": "↻",
        "не найден": "!",
        "несвязанный": "·",
    }
    for dataset in datasets:
        status, detail = source_status(dataset)
        icon = icons.get(status, "·")
        sheet_label = dataset["source_sheet"] or "CSV/активный лист"
        with st.expander(
            f"{icon} {dataset['name']} · {dataset['source_filename']} · {sheet_label}"
        ):
            st.write(f"**Статус:** {status}")
            st.code(detail)
            if status == "изменён вне ПетроЛаба":
                if st.button(
                    "Обновить базу из этого Excel",
                    key=f"reload_{dataset['id']}",
                ):
                    try:
                        row_count = refresh_dataset_from_source(int(dataset["id"]))
                        st.success(f"База обновлена из источника. Строк: {row_count}.")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Не удалось обновить источник: {exc}")
