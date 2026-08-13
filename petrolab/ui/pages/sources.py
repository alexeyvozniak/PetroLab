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

FE2O3_OPTIONS = {
    "Fe₂O₃ = отдельно заданное Fe³⁺": "Fe2O3",
    "Fe₂O₃ = всё Fe, выраженное как Fe₂O₃ total": "Fe2O3t",
}


def render_sources_page() -> None:
    st.title("Источники и импорт")
    project = render_project_selector("import_project")
    if project is None:
        return

    st.caption(
        "Порядок колонок может быть любым. ПетроЛаб нормализует известные оксиды и "
        "рассеянные элементы с явными единицами, а смысловые поля и неоднозначные формы "
        "представления железа подтверждаются отдельно для каждого листа."
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
        "Рекомендуемый режим для постоянной работы: ПетроЛаб запоминает исходный файл, "
        "лист, строку, исходную колонку, единицы и подтверждённый смысл неоднозначных полей."
    )
    path_text = st.text_input("Полный путь к Excel/CSV", key="local_source_path")
    header_row = int(st.number_input(
        "Строка заголовков", min_value=1, max_value=200, value=1, step=1, key="local_header_row"
    ))
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
        "Минерал", list(MINERALS), format_func=lambda key: MINERALS[key].name_ru, key="linked_mineral"
    )
    dataset_name = st.text_input("Название набора", value=source_path.stem, key="linked_dataset_name")

    semantic_maps, measurement_maps = _render_schema_mapping(
        selected_sheets,
        inspector=lambda sheet: inspect_linked_sheet(source_path, sheet, header_row),
        key_prefix="linked",
    )

    if selected_sheets:
        try:
            first_sheet = selected_sheets[0]
            preview = preview_linked_source(
                source_path, first_sheet, header_row, mineral_key,
                semantic_maps.get(first_sheet, {}), measurement_maps.get(first_sheet, {}),
            )
            st.subheader("Предпросмотр после нормализации")
            st.dataframe(preview.head(50), width="stretch", hide_index=True)
        except Exception as exc:
            st.error(f"Не удалось построить предпросмотр: {exc}")

    if st.button(
        "Связать и импортировать выбранные листы", type="primary", key="link_local",
        disabled=not selected_sheets,
    ):
        try:
            result = import_linked_sheets(
                project_id=project_id, path=source_path, sheet_names=selected_sheets,
                mineral_key=mineral_key, dataset_name=dataset_name, header_row=header_row,
                semantic_maps=semantic_maps, measurement_maps=measurement_maps,
            )
            st.success(f"Импортировано наборов: {result.count}.")
            st.rerun()
        except Exception as exc:
            st.error(f"Не удалось импортировать источник: {exc}")


def _render_uploaded_import(project_id: int) -> None:
    st.subheader("Импорт через браузер")
    st.caption(
        "Если исходный Excel должен оставаться двусторонне связанным, лучше использовать первый режим. "
        "Здесь ПетроЛаб создаёт собственную управляемую копию файла."
    )
    uploaded = st.file_uploader(
        "Excel или CSV", type=["xlsx", "xlsm", "xls", "csv"], key="upload_source"
    )
    if uploaded is None:
        return

    file_bytes = uploaded.getvalue()
    header_row = int(st.number_input(
        "Строка заголовков", min_value=1, max_value=200, value=1, step=1, key="upload_header_row"
    ))
    try:
        sheets = list_uploaded_sheets(file_bytes, uploaded.name)
    except Exception as exc:
        st.error(f"Не удалось открыть загруженный файл: {exc}")
        return

    selected_sheets = st.multiselect(
        "Листы для импорта", sheets, default=sheets[:1], key="upload_sheets"
    )
    mineral_key = st.selectbox(
        "Минерал", list(MINERALS), format_func=lambda key: MINERALS[key].name_ru, key="upload_mineral"
    )
    dataset_name = st.text_input(
        "Название набора", value=Path(uploaded.name).stem, key="upload_dataset_name"
    )

    semantic_maps, measurement_maps = _render_schema_mapping(
        selected_sheets,
        inspector=lambda sheet: inspect_uploaded_sheet(file_bytes, uploaded.name, sheet, header_row),
        key_prefix="upload",
    )

    if selected_sheets:
        try:
            first_sheet = selected_sheets[0]
            preview = preview_uploaded_source(
                file_bytes, uploaded.name, first_sheet, header_row, mineral_key,
                semantic_maps.get(first_sheet, {}), measurement_maps.get(first_sheet, {}),
            )
            st.subheader("Предпросмотр после нормализации")
            st.dataframe(preview.head(50), width="stretch", hide_index=True)
        except Exception as exc:
            st.error(f"Не удалось построить предпросмотр: {exc}")

    if st.button(
        "Импортировать рабочую копию", type="primary", key="upload_import",
        disabled=not selected_sheets,
    ):
        try:
            result = import_uploaded_sheets(
                project_id=project_id, file_bytes=file_bytes, filename=uploaded.name,
                sheet_names=selected_sheets, mineral_key=mineral_key, dataset_name=dataset_name,
                header_row=header_row, semantic_maps=semantic_maps,
                measurement_maps=measurement_maps,
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
) -> tuple[dict[str, dict[str, str]], dict[str, dict[str, str]]]:
    semantic_maps: dict[str, dict[str, str]] = {}
    measurement_maps: dict[str, dict[str, str]] = {}
    if not selected_sheets:
        return semantic_maps, measurement_maps

    st.subheader("Сопоставление колонок")
    st.caption(
        "Оксиды и элементы с явными единицами нормализуются автоматически. Поля ниже объединяют "
        "разные названия служебных колонок. Неоднозначные Group/Type/Zone и смысл Fe₂O₃ не угадываются."
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
                for original, normalized in preview.source_headers if original != normalized
            ]
            if changed_headers:
                st.write("**Автоматически распознанные названия:**")
                st.dataframe(pd.DataFrame(changed_headers), width="stretch", hide_index=True)
            else:
                st.caption("Названия уже совместимы с внутренней схемой.")

            if preview.measurement_notes:
                st.write("**Единицы и научные примечания:**")
                for note in preview.measurement_notes:
                    st.caption("• " + note)

            if preview.duplicate_canonical_columns:
                st.warning(
                    "После нормализации обнаружены дубли: "
                    + ", ".join(preview.duplicate_canonical_columns)
                    + ". Они не объединены автоматически. Проверьте исходный лист."
                )

            if "Fe2O3" in preview.schema.columns:
                fe_choice = st.radio(
                    "Что означает колонка Fe₂O₃ на этом листе?",
                    list(FE2O3_OPTIONS),
                    index=None,
                    key=f"{key_prefix}_fe2o3_semantics_{sheet_index}",
                )
                if fe_choice is None:
                    measurement_maps[sheet_name] = {}
                    st.warning(
                        "Нужно явно выбрать смысл Fe₂O₃. До этого предпросмотр и импорт "
                        "не могут научно однозначно интерпретировать железо."
                    )
                else:
                    measurement_maps[sheet_name] = {"Fe2O3": FE2O3_OPTIONS[fe_choice]}
                st.caption(
                    "Выбор сохраняется вместе с набором. Если это ΣFe как Fe₂O₃, ПетроЛаб не будет "
                    "считать величину измеренным Fe³⁺ и при пересчёте сначала восстановит количество total Fe."
                )
            else:
                measurement_maps[sheet_name] = {}

            options = ["—"] + [
                column for column in preview.schema.columns
                if column not in {"Σ оксидов", "QC суммы", "QC железа"}
            ]
            sheet_map: dict[str, str] = {}
            columns = st.columns(2)
            for role_index, role in enumerate(CANONICAL_ROLES):
                suggestion = preview.schema.suggested.get(role)
                default_index = options.index(suggestion) if suggestion in options else 0
                source = columns[role_index % 2].selectbox(
                    ROLE_LABELS[role], options, index=default_index,
                    key=f"{key_prefix}_schema_{sheet_index}_{role}",
                )
                if source != "—":
                    sheet_map[role] = source
                weak = preview.schema.weak_candidates.get(role, ())
                if weak and not suggestion:
                    columns[role_index % 2].caption(
                        "Возможный кандидат: " + ", ".join(weak)
                        + ". Подтвердите вручную, если это действительно нужное поле."
                    )
            semantic_maps[sheet_name] = sheet_map
    return semantic_maps, measurement_maps


def _render_source_statuses(project_id: int) -> None:
    datasets = list_datasets(project_id)
    if not datasets:
        st.info("В проекте пока нет источников.")
        return

    icons = {"актуален": "✓", "изменён вне ПетроЛаба": "↻", "не найден": "!", "несвязанный": "·"}
    for dataset in datasets:
        status, detail = source_status(dataset)
        icon = icons.get(status, "·")
        sheet_label = dataset["source_sheet"] or "CSV/активный лист"
        with st.expander(f"{icon} {dataset['name']} · {dataset['source_filename']} · {sheet_label}"):
            st.write(f"**Статус:** {status}")
            st.code(detail)
            if status == "изменён вне ПетроЛаба":
                st.caption(
                    "При обновлении ПетроЛаб заново найдёт физические колонки, применит сохранённые роли "
                    "и смысл измерений и сопоставит точки по устойчивым идентификаторам."
                )
                if st.button("Обновить базу из этого Excel", key=f"reload_{dataset['id']}"):
                    try:
                        result = refresh_dataset_from_source(int(dataset["id"]))
                        st.success(
                            f"Обновлено строк: {result.row_count}. Сохранено ID: {result.reused_count}; "
                            f"новых точек: {result.new_count}; исчезнувших: {result.removed_count}."
                        )
                        if result.moved_rows_detected:
                            st.info("Обнаружена перестановка/вставка строк: позиционный fallback был отключён для безопасности.")
                        if result.positional_fallback_disabled:
                            st.info(
                                "Позиционное сопоставление по номеру строки отключено: у конкретных точек уже есть "
                                "изображения или история правок. ID сохраняются только при более надёжном совпадении."
                            )
                        if result.positional_reused_count:
                            st.warning(
                                f"ID, сохранённых только по прежней строке Excel: {result.positional_reused_count}. "
                                "Это низкоуверенное сопоставление; для устойчивой истории лучше назначить Sample/Grain/Point."
                            )
                        if result.recovered_roles:
                            st.info("После переименования колонок восстановлены роли: " + ", ".join(result.recovered_roles))
                        if result.detached_image_count:
                            st.warning(
                                f"Из-за исчезнувших или ненадёжно сопоставленных точек затронуто изображений: "
                                f"{result.detached_image_count}. Сами файлы сохранены; проверьте их связи в галерее."
                            )
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Не удалось обновить источник: {exc}")
