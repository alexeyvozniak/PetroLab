from __future__ import annotations

from pathlib import Path
from typing import Callable

import pandas as pd
import streamlit as st

from petrolab.column_schema import CANONICAL_ROLES
from petrolab.db import list_datasets
from petrolab.minerals.registry import MINERALS
from petrolab.services.import_service import (
    ImportSchemaPreview,
    import_linked_sheets,
    import_uploaded_sheets,
    inspect_linked_sheet,
    inspect_uploaded_sheet,
    list_linked_sheets,
    list_uploaded_sheets,
    preview_linked_source,
    preview_uploaded_source,
    refresh_dataset_from_source,
)
from petrolab.sources import source_status
from petrolab.ui.components import render_project_selector

ROLE_LABELS = {
    "Sample": "Образец",
    "Grain": "Зерно",
    "Point": "Точка анализа",
    "Generation": "Генерация / группа кристаллизации",
}


def render_sources_page() -> None:
    """Render source linking, schema mapping, upload, and source-refresh workflows."""
    st.title("Источники и импорт")
    project = render_project_selector("import_project")
    if project is None:
        return

    st.caption(
        "Порядок колонок в разных листах может быть любым. ПетроЛаб нормализует известные "
        "оксиды автоматически, а смысловые поля образца/зерна/точки/генерации можно подтвердить "
        "отдельно для каждого листа."
    )

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
        "Это рекомендуемый режим для постоянной работы: ПетроЛаб запоминает исходный файл, "
        "лист, строку и исходную колонку каждой величины."
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
    dataset_name = st.text_input(
        "Название набора",
        value=source_path.stem,
        key="linked_dataset_name",
    )

    semantic_maps = _render_schema_mapping(
        selected_sheets,
        inspector=lambda sheet: inspect_linked_sheet(source_path, sheet, header_row),
        key_prefix="linked",
    )

    if selected_sheets:
        try:
            preview = preview_linked_source(
                source_path,
                selected_sheets[0],
                header_row,
                mineral_key,
                semantic_maps.get(selected_sheets[0], {}),
            )
            st.subheader("Предпросмотр после нормализации")
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
                semantic_maps=semantic_maps,
            )
            st.success(f"Импортировано наборов: {result.count}.")
            st.rerun()
        except Exception as exc:
            st.error(f"Не удалось импортировать источник: {exc}")


def _render_uploaded_import(project_id: int) -> None:
    st.subheader("Импорт через браузер")
    st.caption(
        "Если исходный Excel должен оставаться двусторонне связанным, лучше использовать первый "
        "режим. Здесь ПетроЛаб создаёт собственную управляемую копию файла."
    )
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

    semantic_maps = _render_schema_mapping(
        selected_sheets,
        inspector=lambda sheet: inspect_uploaded_sheet(
            file_bytes,
            uploaded.name,
            sheet,
            header_row,
        ),
        key_prefix="upload",
    )

    if selected_sheets:
        try:
            preview = preview_uploaded_source(
                file_bytes,
                uploaded.name,
                selected_sheets[0],
                header_row,
                mineral_key,
                semantic_maps.get(selected_sheets[0], {}),
            )
            st.subheader("Предпросмотр после нормализации")
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
                semantic_maps=semantic_maps,
            )
            st.success(f"Импортировано наборов: {result.count}.")
            st.rerun()
        except Exception as exc:
            st.error(f"Не удалось импортировать рабочую копию: {exc}")


def _render_schema_mapping(
    selected_sheets: list[str],
    *,
    inspector: Callable[[str], ImportSchemaPreview],
    key_prefix: str,
) -> dict[str, dict[str, str]]:
    """Render explicit semantic role mapping for each selected sheet."""
    semantic_maps: dict[str, dict[str, str]] = {}
    if not selected_sheets:
        return semantic_maps

    st.subheader("Сопоставление колонок")
    st.caption(
        "Оксиды нормализуются автоматически. Поля ниже нужны для объединения разных названий "
        "служебных колонок в единой базе. «Group» и «Type» не назначаются генерацией автоматически."
    )

    for sheet_index, sheet_name in enumerate(selected_sheets):
        label = sheet_name or "CSV"
        try:
            preview = inspector(sheet_name)
        except Exception as exc:
            st.error(f"{label}: не удалось прочитать заголовки — {exc}")
            continue

        with st.expander(f"Лист: {label}", expanded=sheet_index == 0):
            changed_headers = [
                {"В Excel": original, "В ПетроЛабе": normalized}
                for original, normalized in preview.source_headers
                if original != normalized
            ]
            if changed_headers:
                st.write("**Автоматически распознанные названия:**")
                st.dataframe(pd.DataFrame(changed_headers), width="stretch", hide_index=True)
            else:
                st.caption("Названия оксидов уже совместимы с внутренней схемой.")

            if preview.duplicate_canonical_columns:
                st.warning(
                    "После нормализации обнаружены дублирующиеся имена: "
                    + ", ".join(preview.duplicate_canonical_columns)
                    + ". Они не объединены автоматически. Проверьте исходный лист."
                )

            options = ["—"] + [
                column
                for column in preview.schema.columns
                if column not in {"Σ оксидов", "QC суммы"}
            ]
            sheet_map: dict[str, str] = {}
            columns = st.columns(2)
            for role_index, role in enumerate(CANONICAL_ROLES):
                suggestion = preview.schema.suggested.get(role)
                default_index = options.index(suggestion) if suggestion in options else 0
                source = columns[role_index % 2].selectbox(
                    ROLE_LABELS[role],
                    options,
                    index=default_index,
                    key=f"{key_prefix}_schema_{sheet_index}_{role}",
                )
                if source != "—":
                    sheet_map[role] = source

                weak = preview.schema.weak_candidates.get(role, ())
                if weak and not suggestion:
                    columns[role_index % 2].caption(
                        "Возможный кандидат: " + ", ".join(weak) + ". Подтвердите вручную, если это действительно нужное поле."
                    )
            semantic_maps[sheet_name] = sheet_map
    return semantic_maps


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
                st.caption(
                    "При обновлении будет повторно использована сохранённая схема соответствий колонок."
                )
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
