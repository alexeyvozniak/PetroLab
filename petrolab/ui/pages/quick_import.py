from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from petrolab.column_schema import CANONICAL_ROLES
from petrolab.db import get_or_create_library_project, link_dataset_to_project
from petrolab.services.import_service import (
    ImportSchemaPreview,
    import_uploaded_sheets,
    inspect_uploaded_sheet,
    list_uploaded_sheets,
    preview_uploaded_source,
)
from petrolab.ui.layout import render_badges, render_page_header, render_section_header
from petrolab.ui.navigation import navigate
from petrolab.ui.project_context import active_project


def _safe_automatic_mapping(preview: ImportSchemaPreview) -> tuple[dict[str, str], list[str]]:
    """Return only high-confidence semantic mappings; never infer ambiguous iron semantics."""
    blockers: list[str] = []
    if preview.duplicate_canonical_columns:
        blockers.append(
            "конфликтующие научные колонки после нормализации: "
            + ", ".join(preview.duplicate_canonical_columns)
        )
    columns = {str(column) for column in preview.schema.columns}
    for iron in ("FeO", "Fe2O3"):
        if iron in columns:
            blockers.append(
                f"{iron} требует явного подтверждения: это отдельная валентность или total Fe"
            )
    if not preview.recognized_oxides and not preview.recognized_traces:
        blockers.append("не распознано ни одной химической колонки с однозначной семантикой")

    suggestions = dict(preview.schema.suggested or {})
    semantic: dict[str, str] = {}
    for role in CANONICAL_ROLES:
        suggested = suggestions.get(role)
        if suggested:
            semantic[str(role)] = str(suggested)
            continue
        weak = tuple((preview.schema.weak_candidates or {}).get(role, ()))
        if weak:
            blockers.append(
                f"роль «{role}» неоднозначна: " + ", ".join(str(value) for value in weak)
            )
    return semantic, blockers


def _preview_table(preview: ImportSchemaPreview, sheet: str) -> dict:
    return {
        "Лист": sheet or "CSV",
        "Строк": int(preview.row_count),
        "Оксидов": len(preview.recognized_oxides),
        "Trace": len(preview.recognized_traces),
        "Пустых ячеек": int(preview.empty_cells),
        "<DL / <LOD": int(preview.detection_limit_cells),
        "Формат": preview.adapter_name or "обычная таблица",
    }


def _finish_import(project_id: int, dataset_ids: list[int]) -> None:
    for dataset_id in dataset_ids:
        link_dataset_to_project(
            int(project_id),
            int(dataset_id),
            "Добавлено через безопасный быстрый импорт",
            purpose="working",
        )
    st.session_state["workflow_recent_dataset_ids"] = [int(value) for value in dataset_ids]
    st.session_state["workflow_recent_import_target"] = int(project_id)
    st.session_state["quick_import_done_ids"] = [int(value) for value in dataset_ids]
    st.rerun()


def render_quick_import_page() -> None:
    project = active_project()
    render_page_header(
        "Быстрый импорт",
        "Если структура файла однозначна, PetroLab импортирует его без длинного мастера. Любая научная неоднозначность автоматически переводит сценарий в экспертный режим.",
        eyebrow="Добавить данные",
        context=str(project["name"]) if project else "Проект не выбран",
    )
    if project is None:
        st.info("Сначала создайте или выберите проект.")
        return
    project_id = int(project["id"])

    completed = [int(value) for value in st.session_state.get("quick_import_done_ids", [])]
    if completed:
        st.success(f"Импортировано наборов: {len(completed)}.")
        c1, c2, c3 = st.columns(3)
        if c1.button("Открыть рабочий стол", type="primary", width="stretch", key="quick_done_workspace"):
            st.session_state["workspace_mode"] = "Массив данных"
            navigate("workspace")
            st.rerun()
        if c2.button("Разобрать фазы", width="stretch", key="quick_done_phases"):
            if len(completed) == 1:
                st.session_state["workflow_mixed_dataset_id"] = completed[0]
            navigate("mixed_minerals")
            st.rerun()
        if c3.button("Построить график", width="stretch", key="quick_done_plot"):
            st.session_state["workflow_plot_dataset_ids"] = completed
            navigate("plots")
            st.rerun()
        if st.button("Импортировать ещё файл", width="stretch", key="quick_done_again"):
            st.session_state.pop("quick_import_done_ids", None)
            st.rerun()
        return

    render_badges([
        ("Без догадок о минерале", "success"),
        ("Неоднозначное Fe → экспертный режим", "warning"),
        ("Preview до записи", "neutral"),
        ("Исходный файл сохраняется", "neutral"),
    ])

    uploaded = st.file_uploader(
        "Excel или CSV",
        type=["xlsx", "xlsm", "xls", "csv"],
        key="quick_import_file",
    )
    if uploaded is None:
        st.caption(
            "Быстрый импорт создаёт внутреннюю рабочую копию. Если нужна двусторонняя синхронизация с вашим XLSX/XLSM, используйте «Расширенный импорт»."
        )
        if st.button("Расширенный импорт / связать файл на компьютере", width="stretch", key="quick_to_advanced_empty"):
            navigate("sources")
            st.rerun()
        return

    data = uploaded.getvalue()
    with st.expander("Если заголовки не в первой строке", expanded=False):
        header_row = int(st.number_input(
            "Строка заголовков",
            min_value=1,
            max_value=200,
            value=1,
            step=1,
            key="quick_import_header",
        ))
    try:
        sheets = list_uploaded_sheets(data, uploaded.name)
    except Exception as exc:
        st.error(f"Файл не удалось открыть: {exc}")
        return
    selected = st.multiselect(
        "Листы",
        sheets,
        default=sheets[:1],
        key="quick_import_sheets",
    )
    if not selected:
        st.info("Выберите хотя бы один лист.")
        return

    dataset_name = st.text_input(
        "Название набора",
        value=Path(uploaded.name).stem,
        key="quick_import_name",
    )

    previews: dict[str, ImportSchemaPreview] = {}
    semantic_maps: dict[str, dict[str, str]] = {}
    blockers: dict[str, list[str]] = {}
    preview_rows: list[dict] = []
    normalized: dict[str, pd.DataFrame] = {}

    for sheet in selected:
        try:
            preview = inspect_uploaded_sheet(data, uploaded.name, sheet, header_row)
        except Exception as exc:
            blockers[sheet] = [f"не удалось прочитать заголовки: {exc}"]
            continue
        previews[sheet] = preview
        semantic, reasons = _safe_automatic_mapping(preview)
        semantic_maps[sheet] = semantic
        if reasons:
            blockers[sheet] = reasons
        preview_rows.append(_preview_table(preview, sheet))

    render_section_header("Проверка", "PetroLab автоматически продолжит только при однозначной схеме")
    if preview_rows:
        st.dataframe(pd.DataFrame(preview_rows), width="stretch", hide_index=True)

    if blockers:
        st.warning(
            "Быстрый импорт остановлен: есть поля, которые нельзя интерпретировать без вашего решения. "
            "Данные ещё не записывались."
        )
        for sheet, reasons in blockers.items():
            with st.expander(f"{sheet or 'CSV'} · что нужно уточнить", expanded=True):
                for reason in reasons:
                    st.write("• " + reason)
        if st.button("Открыть расширенный импорт", type="primary", width="stretch", key="quick_to_advanced"):
            st.session_state["add_data_mode"] = "own"
            navigate("sources")
            st.rerun()
        return

    for sheet in selected:
        try:
            normalized[sheet] = preview_uploaded_source(
                data,
                uploaded.name,
                sheet,
                header_row,
                "generic",
                semantic_maps.get(sheet, {}),
                {},
            )
        except Exception as exc:
            st.error(f"{sheet or 'CSV'}: preflight не пройден — {exc}")
            return

    st.success("Схема однозначна. Научных вопросов, требующих ручного подтверждения, не найдено.")
    for index, sheet in enumerate(selected):
        frame = normalized[sheet]
        with st.expander(
            f"{sheet or 'CSV'} · {len(frame)} строк · preview",
            expanded=index == 0,
        ):
            st.dataframe(frame.head(40), width="stretch", hide_index=True)
            if len(frame) > 40:
                st.caption(f"Показаны первые 40 из {len(frame)} строк.")

    st.caption(
        "Минерал намеренно сохраняется как «Смешанный / определить автоматически»: быстрый режим не делает минералогическое предположение по одному имени файла или листа."
    )
    if st.button("Импортировать", type="primary", width="stretch", key="quick_import_commit"):
        try:
            result = import_uploaded_sheets(
                project_id=get_or_create_library_project(),
                file_bytes=data,
                filename=uploaded.name,
                sheet_names=selected,
                mineral_key="generic",
                dataset_name=dataset_name,
                header_row=header_row,
                semantic_maps=semantic_maps,
                measurement_maps={},
                header_rows={sheet: header_row for sheet in selected},
                mineral_keys={sheet: "generic" for sheet in selected},
            )
            _finish_import(project_id, list(result.dataset_ids))
        except Exception as exc:
            st.error(f"Импорт остановлен без частичной записи: {exc}")
