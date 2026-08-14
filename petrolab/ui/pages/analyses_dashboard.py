from __future__ import annotations

import streamlit as st

from petrolab.analysis_groups import WORK_GROUP_COLUMN, attach_work_groups
from petrolab.dataframe_utils import apply_quick_filter, compute_changes, dataset_label
from petrolab.db import META_COLUMNS, list_datasets
from petrolab.derived import active_derived_columns, load_unified_with_derived
from petrolab.services.analysis_service import save_changes_and_sync, save_changes_to_database
from petrolab.ui.analysis_components import PROTECTED_ANALYSIS_COLUMNS, render_point_card
from petrolab.ui.editability import common_editable_source_columns
from petrolab.ui.layout import render_badges, render_page_header
from petrolab.ui.project_context import active_project_id

_BASIC = ["Sample", "Grain", "Point", "Generation", WORK_GROUP_COLUMN, "Проект", "Набор", "Минерал", "Источник", "Лист", "Строка Excel"]
_SAVE_FLASH_KEY = "analysis_save_flash"


def _view_columns(dataframe, derived: set[str], mode: str):
    visible = [column for column in dataframe.columns if not str(column).startswith("_")]
    basic = [column for column in _BASIC if column in visible]
    qc = [column for column in visible if str(column).startswith("QC ") or str(column).startswith("Σ ") or column == "Поправка O=F,Cl"]
    calculated = [column for column in visible if column in derived or str(column).startswith(("apfu_", "site_"))]
    chemistry = [column for column in visible if column not in set(basic + qc + calculated)]
    return {
        "Основное": basic,
        "Химия": basic[:4] + chemistry,
        "Расчёты": basic[:4] + calculated,
        "QC": basic[:4] + qc,
        "Все": visible,
    }[mode]


def _show_save_flash() -> None:
    flash = st.session_state.pop(_SAVE_FLASH_KEY, None)
    if not isinstance(flash, dict):
        return
    message = str(flash.get("success") or "").strip()
    if message:
        st.success(message)
    for warning in flash.get("warnings", []):
        st.warning(str(warning))


def _rerun_with_result(message: str, warnings: list[str]) -> None:
    st.session_state[_SAVE_FLASH_KEY] = {
        "success": message,
        "warnings": [str(warning) for warning in warnings],
    }
    st.rerun()


def render_analyses_dashboard_page() -> None:
    project_id = active_project_id()
    render_page_header(
        "База анализов",
        "Исходная химия, локальная интерпретация и актуальные расчётные поля в одной рабочей таблице.",
        eyebrow="Данные",
    )
    _show_save_flash()
    if project_id is None:
        st.info("Сначала создайте проект.")
        return
    datasets = list_datasets(project_id)
    if not datasets:
        st.info("В активном проекте нет данных.")
        return

    labels = {dataset_label(item): int(item["id"]) for item in datasets}
    with st.container(border=True):
        c1, c2 = st.columns([2.2, 1])
        selected_labels = c1.multiselect("Наборы", list(labels), default=list(labels), key="db_datasets_dashboard")
        mode = c2.selectbox("Колонки", ["Основное", "Химия", "Расчёты", "QC", "Все"], key="db_column_view")
        query = st.text_input("Поиск", placeholder="Образец, зерно, поколение или значение", key="db_search_dashboard")
    selected_ids = [labels[label] for label in selected_labels]
    if not selected_ids:
        st.info("Выберите хотя бы один набор.")
        return

    dataframe = attach_work_groups(load_unified_with_derived(project_id, selected_ids))
    shown = apply_quick_filter(dataframe, query).copy()
    derived = active_derived_columns(selected_ids)
    render_badges([(f"{len(shown):,} строк".replace(",", " "), "neutral"), (f"{len(selected_ids)} наборов", "accent")])

    table_tab, point_tab = st.tabs(["Таблица", "Карточка точки"])
    with table_tab:
        wanted = _view_columns(shown, derived, mode)
        internals = [column for column in shown.columns if str(column).startswith("_")]
        editor = shown[internals + [column for column in wanted if column not in internals]].copy()
        editable = common_editable_source_columns(datasets, selected_ids)
        protected = (set(shown.columns) - set(editable)) | PROTECTED_ANALYSIS_COLUMNS | set(derived) | META_COLUMNS
        disabled = [column for column in editor.columns if column in protected or str(column).startswith("_")]
        edited = st.data_editor(
            editor,
            width="stretch",
            hide_index=True,
            height=650,
            disabled=disabled,
            num_rows="fixed",
            key="unified_editor_dashboard",
        )
        changes = compute_changes(editor, edited, protected_columns=protected)
        if changes:
            render_badges([(f"{len(changes)} несохранённых изменений", "warning")])
        save, sync = st.columns([1, 1.35])
        if save.button("Сохранить", type="primary", disabled=not changes, width="stretch"):
            result = save_changes_to_database(changes)
            if result.ok:
                _rerun_with_result(
                    f"Сохранено изменений: {result.saved_changes}.",
                    result.warnings,
                )
            for error in result.errors:
                st.error(error)
        if sync.button("Сохранить и синхронизировать Excel", disabled=not changes, width="stretch"):
            result = save_changes_and_sync(changes)
            if result.ok:
                _rerun_with_result(
                    f"Сохранено: {result.saved_changes}; обновлено файлов: {result.synced_files}.",
                    result.warnings,
                )
            for error in result.errors:
                st.error(error)
        st.caption("Синхронизация изменяет связанный XLSX/XLSM; перед записью проверяются внешние изменения и создаётся резервная копия.")
    with point_tab:
        if len(shown) > 3000:
            st.caption("Для списка точек показаны первые 3000 совпадений. Используйте поиск в toolbar, чтобы сузить выборку.")
        render_point_card(shown, project_id)
