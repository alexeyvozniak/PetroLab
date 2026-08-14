from __future__ import annotations

from datetime import datetime

import streamlit as st

from petrolab.analysis_drafts import (
    apply_analysis_draft,
    clear_analysis_draft,
    load_analysis_draft,
    remove_analysis_draft_changes,
    replace_visible_analysis_draft,
)
from petrolab.analysis_groups import WORK_GROUP_COLUMN, attach_work_groups
from petrolab.dataframe_utils import apply_quick_filter, compute_changes, dataset_label
from petrolab.db import META_COLUMNS, list_accessible_datasets
from petrolab.derived import active_derived_columns, load_unified_with_derived
from petrolab.services.analysis_service import save_changes_and_sync, save_changes_to_database
from petrolab.ui.analysis_components import PROTECTED_ANALYSIS_COLUMNS, render_point_card
from petrolab.ui.destructive_actions import confirm_then, render_pending
from petrolab.ui.editability import common_editable_source_columns
from petrolab.ui.layout import render_badges, render_page_header
from petrolab.ui.project_context import active_project_id

_BASIC = ["Sample", "Grain", "Point", "Generation", "QC уровень", "QC решение", WORK_GROUP_COLUMN, "Проект", "Набор", "Минерал", "Источник", "Лист", "Строка Excel"]
_SAVE_FLASH_KEY = "analysis_save_flash"
_DRAFT_EDITOR_KEY = "unified_editor_dashboard"


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
    st.session_state.pop(_DRAFT_EDITOR_KEY, None)
    st.rerun()


def _draft_time(value: str) -> str:
    if not value:
        return ""
    try:
        return datetime.fromisoformat(value).astimezone().strftime("%H:%M:%S")
    except ValueError:
        return ""


def _clear_draft_and_editor(project_id: int) -> None:
    clear_analysis_draft(project_id)
    st.session_state.pop(_DRAFT_EDITOR_KEY, None)


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
    datasets = list_accessible_datasets(project_id)
    if not datasets:
        st.info("В активном проекте нет данных.")
        return

    labels = {dataset_label(item): int(item["id"]) for item in datasets}
    requested_dataset_ids = [
        int(value) for value in st.session_state.pop("workflow_edit_dataset_ids", [])
    ]
    requested_analysis_ids = {
        str(value) for value in st.session_state.pop("workflow_edit_analysis_ids", [])
    }
    requested_context = st.session_state.pop("workflow_edit_context", {})
    requested_labels = [label for label, dataset_id in labels.items() if dataset_id in requested_dataset_ids]
    if requested_labels:
        st.session_state["db_datasets_dashboard"] = requested_labels
        st.info(
            "Открыт отбор из «Вся база». Отредактируйте поля и нажмите «Сохранить и синхронизировать Excel»; "
            "перед записью PetroLab проверит исходный файл и создаст резервную копию."
        )
        if requested_context:
            st.caption("Изменения будут применены только к строкам исходного отбора.")
    with st.container(border=True):
        c1, c2 = st.columns([2.2, 1])
        selected_labels = c1.multiselect(
            "Наборы", list(labels), default=requested_labels or list(labels), key="db_datasets_dashboard"
        )
        mode = c2.selectbox("Колонки", ["Основное", "Химия", "Расчёты", "QC", "Все"], key="db_column_view")
        query = st.text_input("Поиск", placeholder="Образец, зерно, поколение или значение", key="db_search_dashboard")
    selected_ids = [labels[label] for label in selected_labels]
    if not selected_ids:
        st.info("Выберите хотя бы один набор.")
        return

    dataframe = attach_work_groups(load_unified_with_derived(project_id, selected_ids))
    shown = apply_quick_filter(dataframe, query).copy()
    if requested_analysis_ids:
        shown = shown[shown["_analysis_id"].astype(str).isin(requested_analysis_ids)].copy()
    derived = active_derived_columns(selected_ids)
    render_badges([(f"{len(shown):,} строк".replace(",", " "), "neutral"), (f"{len(selected_ids)} наборов", "accent")])

    table_tab, point_tab = st.tabs(["Таблица", "Карточка точки"])
    with table_tab:
        wanted = _view_columns(shown, derived, mode)
        internals = [column for column in shown.columns if str(column).startswith("_")]
        base_editor = shown[internals + [column for column in wanted if column not in internals]].copy()
        editable = common_editable_source_columns(datasets, selected_ids) | {"QC решение"}
        protected = (set(shown.columns) - set(editable)) | PROTECTED_ANALYSIS_COLUMNS | set(derived) | META_COLUMNS
        disabled = [column for column in base_editor.columns if column in protected or str(column).startswith("_")]

        draft = load_analysis_draft(project_id)
        overlay = apply_analysis_draft(base_editor, draft.changes, protected_columns=protected)
        if overlay.resolved:
            draft = remove_analysis_draft_changes(project_id, overlay.resolved)
        working_editor = overlay.dataframe

        if draft.changes:
            stamp = _draft_time(draft.updated_at)
            label = f"Черновик автосохранён · {len(draft.changes)} правок"
            if stamp:
                label += f" · {stamp}"
            render_badges([(label, "success")])
            st.caption(
                "Черновик хранится локально и переживает перезапуск компьютера. "
                "В научную базу и исходный Excel он попадёт только после явного сохранения."
            )
        if overlay.applied:
            st.info(f"Восстановлено из локального черновика: {len(overlay.applied)} правок.")
        if overlay.conflicts:
            st.warning(
                f"Не применено конфликтующих правок: {len(overlay.conflicts)}. "
                "Исходные значения изменились после создания черновика; PetroLab не перезаписывает их автоматически."
            )

        render_pending(
            "analysis_draft",
            "Черновик содержит несохранённую работу. Нажмите «Удалить черновик» ещё раз, чтобы окончательно её отбросить.",
        )
        if draft.changes and st.button("Удалить черновик", key="discard_analysis_draft"):
            if confirm_then(
                "analysis_draft",
                int(project_id),
                lambda: _clear_draft_and_editor(int(project_id)),
            ):
                st.rerun()

        edited = st.data_editor(
            working_editor,
            width="stretch",
            hide_index=True,
            height=650,
            disabled=disabled,
            num_rows="fixed",
            key=_DRAFT_EDITOR_KEY,
        )
        changes = compute_changes(base_editor, edited, protected_columns=protected)
        replace_visible_analysis_draft(
            project_id,
            base_editor["_analysis_id"].astype(str).tolist() if "_analysis_id" in base_editor.columns else [],
            [column for column in base_editor.columns if not str(column).startswith("_")],
            [*overlay.conflicts, *changes],
        )
        if changes:
            render_badges([
                (f"{len(changes)} несохранённых изменений", "warning"),
                ("автосохранение черновика включено", "success"),
            ])

        save, sync = st.columns([1, 1.35])
        if save.button("Сохранить", type="primary", disabled=not changes, width="stretch"):
            result = save_changes_to_database(changes)
            if result.ok:
                remove_analysis_draft_changes(project_id, changes)
                _rerun_with_result(
                    f"Сохранено изменений: {result.saved_changes}.",
                    result.warnings,
                )
            for error in result.errors:
                st.error(error)
        if sync.button("Сохранить и синхронизировать Excel", disabled=not changes, width="stretch"):
            result = save_changes_and_sync(changes)
            if result.ok:
                remove_analysis_draft_changes(project_id, changes)
                _rerun_with_result(
                    f"Сохранено: {result.saved_changes}; обновлено файлов: {result.synced_files}.",
                    result.warnings,
                )
            for error in result.errors:
                st.error(error)
        st.caption("Синхронизация изменяет связанный XLSX/XLSM; перед записью проверяются внешние изменения и создаётся резервная копия.")
        st.caption("«QC уровень» и причины рассчитываются из данных и не скрывают анализы. В «QC решение» можно вручную оставить Авто, Включить или Исключить для графиков; это поле хранится только в PetroLab.")
    with point_tab:
        if len(shown) > 3000:
            st.caption("Для списка точек показаны первые 3000 совпадений. Используйте поиск в toolbar, чтобы сузить выборку.")
        render_point_card(shown, project_id)
