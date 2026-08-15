from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from petrolab.auto_pipeline import auto_process_imported_datasets
from petrolab.column_schema import CANONICAL_ROLES
from petrolab.db import get_or_create_library_project, link_dataset_to_project
from petrolab.services.import_service import (
    ImportSchemaPreview,
    import_uploaded_sheets,
    inspect_uploaded_sheet,
    list_uploaded_sheets,
    preview_uploaded_source,
)
from petrolab.ui.layout import render_badges, render_hint, render_page_header, render_section_header
from petrolab.ui.navigation import navigate
from petrolab.ui.project_context import active_project


IRON_CHOICES = {
    "FeO": {
        "Всё железо, выраженное как FeO total": "FeOt",
        "Отдельно измеренное Fe²⁺ как FeO": "FeO",
    },
    "Fe2O3": {
        "Всё железо, выраженное как Fe₂O₃ total": "Fe2O3t",
        "Отдельно измеренное Fe³⁺ как Fe₂O₃": "Fe2O3",
    },
}


def _safe_automatic_mapping(preview: ImportSchemaPreview) -> tuple[dict[str, str], list[str]]:
    """Return only high-confidence semantic mappings; iron meaning is confirmed inline."""
    blockers: list[str] = []
    if preview.duplicate_canonical_columns:
        blockers.append(
            "конфликтующие научные колонки после нормализации: "
            + ", ".join(preview.duplicate_canonical_columns)
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

    # Only chemically high-confidence, non-outlier probe rows are materialized into
    # phases. Ambiguous/trace-only rows remain unresolved; APFU stays a derived layer.
    report = auto_process_imported_datasets(int(project_id), dataset_ids)
    working = list(report.working_dataset_ids) or [int(value) for value in dataset_ids]
    warnings = [warning for item in report.datasets for warning in item.warnings]
    invalid_formula_rows = sum(item.formula_invalid_rows for item in report.datasets)
    st.session_state["workflow_recent_dataset_ids"] = working
    st.session_state["workflow_recent_import_target"] = int(project_id)
    st.session_state["quick_import_done_ids"] = working
    st.session_state["quick_import_report"] = {
        "auto_assigned": int(report.auto_assigned_rows),
        "unresolved": int(report.unresolved_rows),
        "formula_datasets": int(report.formula_datasets),
        "formula_invalid_rows": int(invalid_formula_rows),
        "warnings": warnings,
    }
    st.rerun()


def _iron_semantics(previews: dict[str, ImportSchemaPreview]) -> tuple[dict[str, dict[str, str]], bool]:
    measurement_maps: dict[str, dict[str, str]] = {}
    needed = [
        (sheet, iron)
        for sheet, preview in previews.items()
        for iron in IRON_CHOICES
        if iron in {str(column) for column in preview.schema.columns}
    ]
    if not needed:
        return {sheet: {} for sheet in previews}, True

    render_section_header("Один научный вопрос", "PetroLab не угадывает смысл FeO / Fe₂O₃")
    st.caption(
        "Это единственное обязательное уточнение для типичного зондового файла, если заголовок не говорит, total это Fe или отдельная валентность. После ответа импорт продолжится здесь же."
    )
    ready = True
    for sheet, preview in previews.items():
        columns = {str(column) for column in preview.schema.columns}
        mapping: dict[str, str] = {}
        for iron in IRON_CHOICES:
            if iron not in columns:
                continue
            choice = st.radio(
                f"{sheet or 'CSV'} · что означает {iron}?",
                list(IRON_CHOICES[iron]),
                index=None,
                key=f"quick_iron_{sheet}_{iron}",
            )
            if choice is None:
                ready = False
            else:
                mapping[iron] = IRON_CHOICES[iron][choice]
        measurement_maps[sheet] = mapping
    return measurement_maps, ready


def render_quick_import_page() -> None:
    project = active_project()
    render_page_header(
        "Быстрый импорт",
        "Зондовый файл проходит от нормализации до фаз и APFU автоматически; PetroLab спрашивает только там, где научно нельзя угадывать.",
        eyebrow="Добавить данные",
        context=str(project["name"]) if project else "Проект не выбран",
    )
    if project is None:
        st.info("Сначала создайте или выберите проект.")
        return
    project_id = int(project["id"])

    completed = [int(value) for value in st.session_state.get("quick_import_done_ids", [])]
    if completed:
        report = dict(st.session_state.get("quick_import_report", {}) or {})
        st.success(f"Данные сохранены в базе. Рабочих наборов после разбора: {len(completed)}.")
        render_badges([
            (f"авторазобрано строк · {int(report.get('auto_assigned', 0))}", "success"),
            (f"требуют решения · {int(report.get('unresolved', 0))}", "warning" if int(report.get("unresolved", 0)) else "neutral"),
            (f"APFU наборов · {int(report.get('formula_datasets', 0))}", "accent"),
        ])
        invalid_formula_rows = int(report.get("formula_invalid_rows", 0))
        if invalid_formula_rows:
            st.warning(
                f"У {invalid_formula_rows} строк формула не прошла входные условия. Исходная химия сохранена; такие строки отмечены как нерассчитанные."
            )
        for warning in list(report.get("warnings", []))[:12]:
            st.caption("• " + str(warning))
        c1, c2, c3 = st.columns(3)
        if c1.button("Открыть рабочий стол", type="primary", width="stretch", key="quick_done_workspace"):
            st.session_state["workspace_mode"] = "Массив данных"
            navigate("workspace")
            st.rerun()
        phase_label = "Разобрать оставшиеся" if int(report.get("unresolved", 0)) else "Проверить фазы"
        if c2.button(phase_label, width="stretch", key="quick_done_phases"):
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
            st.session_state.pop("quick_import_report", None)
            st.rerun()
        return

    render_badges([
        ("Preview до записи", "neutral"),
        ("Fe — один вопрос при необходимости", "warning"),
        ("High-confidence фазы → автоматически", "success"),
    ])

    uploaded = st.file_uploader(
        "Excel или CSV",
        type=["xlsx", "xlsm", "xls", "csv"],
        key="quick_import_file",
    )
    if uploaded is None:
        render_hint(
            "После записи PetroLab автоматически разберёт только уверенные mineral phases и сразу сохранит рекомендуемый APFU-пересчёт. "
            "Спорные точки останутся в mixed. Для двусторонней синхронизации с XLSX/XLSM используйте расширенный импорт."
        )
        if st.button("Расширенный импорт", width="stretch", key="quick_to_advanced_empty", help="Связать исходный файл на компьютере и пройти полный контроль схемы."):
            navigate("sources")
            st.rerun()
        return

    data = uploaded.getvalue()
    with st.expander("Заголовки не в первой строке", expanded=False):
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

    render_section_header("Проверка", "Автоматическое продолжение разрешено только для однозначной схемы")
    if preview_rows:
        st.dataframe(pd.DataFrame(preview_rows), width="stretch", hide_index=True)

    if blockers:
        st.warning("В файле есть неоднозначность, которую короткий импорт не может безопасно решить. Данные ещё не записывались.")
        for sheet, reasons in blockers.items():
            with st.expander(f"{sheet or 'CSV'} · уточнить", expanded=True):
                for reason in reasons:
                    st.write("• " + reason)
        if st.button("Открыть расширенный импорт", type="primary", width="stretch", key="quick_to_advanced"):
            st.session_state["add_data_mode"] = "own"
            navigate("sources")
            st.rerun()
        return

    measurement_maps, iron_ready = _iron_semantics(previews)
    if not iron_ready:
        st.info("Ответьте на вопрос о представлении железа — после этого можно сразу импортировать файл.")

    if iron_ready:
        for sheet in selected:
            try:
                normalized[sheet] = preview_uploaded_source(
                    data,
                    uploaded.name,
                    sheet,
                    header_row,
                    "generic",
                    semantic_maps.get(sheet, {}),
                    measurement_maps.get(sheet, {}),
                )
            except Exception as exc:
                st.error(f"{sheet or 'CSV'}: preflight не пройден — {exc}")
                return

        st.success("Схема однозначна и готова к записи.")
        for index, sheet in enumerate(selected):
            frame = normalized[sheet]
            with st.expander(
                f"{sheet or 'CSV'} · {len(frame)} строк · preview",
                expanded=index == 0,
            ):
                st.dataframe(frame.head(40), width="stretch", hide_index=True)
                if len(frame) > 40:
                    render_hint(f"В preview показаны первые 40 из {len(frame)} строк.")

    render_hint(
        "Сначала файл сохраняется как mixed без догадки по имени. Затем химически high-confidence точки автоматически переходят в фазовые наборы и получают рекомендуемый APFU; всё неоднозначное остаётся mixed."
    )
    if st.button(
        "Импортировать и подготовить к работе",
        type="primary",
        width="stretch",
        key="quick_import_commit",
        disabled=not iron_ready,
    ):
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
                measurement_maps=measurement_maps,
                header_rows={sheet: header_row for sheet in selected},
                mineral_keys={sheet: "generic" for sheet in selected},
            )
            _finish_import(project_id, list(result.dataset_ids))
        except Exception as exc:
            st.error(f"Импорт остановлен без частичной записи: {exc}")
