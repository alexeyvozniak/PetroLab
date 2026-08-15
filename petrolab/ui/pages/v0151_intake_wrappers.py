"""Универсальный intake: project-scoping, provenance-lock и staging для сложных таблиц."""
from __future__ import annotations

import streamlit as st

from petrolab.db import list_accessible_datasets
from petrolab.ui import staged_intake as _staged
from petrolab.ui import universal_intake as _universal
from petrolab.ui import universal_intake_extensions as _extensions
from petrolab.ui.navigation import navigate
from petrolab.ui.project_context import active_project

from . import add_data as _add_data
from . import quick_import as _quick_import


def _project_session_token(project_id: int, token: str) -> str:
    """Разделять transient-state импорта между проектами, не меняя identity сохранённых данных."""
    return f"p{int(project_id)}_{str(token)}"


def _render_table_with_locked_provenance(original_table, project_id: int, name: str, data: bytes, token: str):
    """Не позволять уже записанному внешнему provenance тихо смениться в той же intake-сессии."""
    source_widget_key = f"universal_source_kind_{token}"
    study_key = f"universal_study_id_{token}"
    lock_key = f"universal_locked_source_kind_{token}"
    locked_kind = st.session_state.get(lock_key)
    if locked_kind:
        st.session_state[source_widget_key] = str(locked_kind)

    result = _extensions.render_table_import_with_provenance(
        original_table, project_id, name, data, token
    )

    if st.session_state.get(study_key) is not None:
        current_kind = str(st.session_state.get(source_widget_key) or "")
        if current_kind:
            st.session_state[lock_key] = current_kind
            st.caption(
                "Provenance внешнего источника уже записан и зафиксирован для этой импортированной пачки. "
                "Если источник указан неверно, исправьте его явно в «Источники и литература», а не переключателем импорта."
            )
    return result


def render_add_data_page() -> None:
    _add_data.render_add_data_page()
    project = active_project()
    if project is None:
        return
    project_id = int(project["id"])

    original_table = _universal._render_table_import
    original_images = _universal._render_image_wizard
    original_file_token = _universal._file_token
    original_batch_token = _extensions._batch_token

    def scoped_file_token(name: str, data: bytes) -> str:
        return _project_session_token(project_id, original_file_token(name, data))

    def scoped_batch_token(image_files: list[tuple[str, bytes]]) -> str:
        return _project_session_token(project_id, original_batch_token(image_files))

    def table_with_staging(target_project_id: int, name: str, data: bytes, token: str):
        if int(target_project_id) != project_id:
            raise ValueError("Контекст универсального импорта сменился между рендерами")

        # В обычном режиме staging должен сохранить тот же provenance-lock,
        # который действует у безопасного импорта без структурных преобразований.
        original_staged_provenance = _staged.render_table_import_with_provenance

        def locked_provenance(base_original, pid: int, filename: str, raw: bytes, intake_token: str):
            return _render_table_with_locked_provenance(
                base_original, int(pid), filename, raw, intake_token
            )

        _staged.render_table_import_with_provenance = locked_provenance
        try:
            return _staged.render_table_import_v0154(
                original_table, target_project_id, name, data, token
            )
        finally:
            _staged.render_table_import_with_provenance = original_staged_provenance

    _universal._file_token = scoped_file_token
    _extensions._batch_token = scoped_batch_token
    _universal._render_table_import = table_with_staging
    _universal._render_image_wizard = _extensions.render_image_wizard_multi_dataset
    try:
        _universal.render_universal_intake(project_id)
    finally:
        _universal._file_token = original_file_token
        _extensions._batch_token = original_batch_token
        _universal._render_table_import = original_table
        _universal._render_image_wizard = original_images


def render_quick_import_page() -> None:
    _quick_import.render_quick_import_page()
    completed = [int(value) for value in st.session_state.get("quick_import_done_ids", [])]
    project = active_project()
    if not completed or project is None:
        return
    project_id = int(project["id"])
    recent_target = st.session_state.get("workflow_recent_import_target")
    if recent_target is not None:
        try:
            if int(recent_target) != project_id:
                return
        except (TypeError, ValueError):
            return
    accessible = {int(item["id"]): item for item in list_accessible_datasets(project_id)}
    choices = [value for value in completed if value in accessible]
    if not choices:
        return
    st.divider()
    st.markdown("### Следующий естественный шаг")
    st.caption(
        "Если к этим анализам есть BSE, EDS-карты или фотографии, их можно привязать сейчас. "
        "Если фотографии относятся к нескольким автоматически разобранным фазовым наборам, откройте «Добавить данные → Универсальный +»: там dataset выбирается отдельно для каждого изображения."
    )
    dataset_id = st.selectbox(
        "К какому рабочему набору относятся фотографии",
        choices,
        format_func=lambda value: str(accessible[int(value)]["name"]),
        key=f"v0154_post_import_image_dataset_{project_id}",
    )
    if st.button(
        "Добавить фотографии к этим анализам",
        type="primary",
        width="stretch",
        key=f"v0154_post_import_images_{project_id}",
    ):
        st.session_state["workflow_image_dataset_id"] = int(dataset_id)
        navigate("images")
        st.rerun()
