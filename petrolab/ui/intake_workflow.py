"""Canonical Add Data composition: safe table import -> staging -> images -> science."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from petrolab.dataframe_utils import human_point_label
from petrolab.db import list_accessible_datasets, load_dataset_dataframe, unlink_dataset_from_project
from petrolab.operation_journal import set_annotation_with_journal
from petrolab.services.image_service import SCOPE_ANALYSIS
from petrolab.term_registry import register_term, term_values
from petrolab.textural_runtime import COMMON_TEXTURAL_ZONES, TEXTURAL_ZONE_COLUMN
from petrolab.ui import staged_intake, universal_intake, universal_intake_extensions
from petrolab.ui.image_components import SCOPE_LABELS
from petrolab.ui.layout import render_badges, render_hint, render_section_header
from petrolab.ui.navigation import navigate
from petrolab.ui.selection_context import clear_selection, clear_row_states


_PROJECT_CONTEXT_KEY = "_petrolab_intake_project_id"
_TRANSIENT_PREFIXES = ("universal_", "univimg_", "staging_")


def _reset_transient_state_on_project_change(project_id: int) -> None:
    """Keep uncommitted uploader widgets from leaking into another project."""
    previous = st.session_state.get(_PROJECT_CONTEXT_KEY)
    if previous is not None:
        try:
            same_project = int(previous) == int(project_id)
        except (TypeError, ValueError):
            same_project = False
        if not same_project:
            for key in list(st.session_state):
                if any(str(key).startswith(prefix) for prefix in _TRANSIENT_PREFIXES):
                    st.session_state.pop(key, None)
    st.session_state[_PROJECT_CONTEXT_KEY] = int(project_id)


def render_recent_import_undo(project_id: int) -> None:
    """Remove the latest import only from this project, never from the global library."""
    recent_target = st.session_state.get("workflow_recent_import_target")
    try:
        if recent_target is None or int(recent_target) != int(project_id):
            return
    except (TypeError, ValueError):
        return

    recent: list[int] = []
    for value in st.session_state.get("workflow_recent_dataset_ids", []) or []:
        try:
            dataset_id = int(value)
        except (TypeError, ValueError):
            continue
        if dataset_id not in recent:
            recent.append(dataset_id)
    if not recent:
        return

    accessible = {int(item["id"]): item for item in list_accessible_datasets(int(project_id))}
    linked = [dataset_id for dataset_id in recent if dataset_id in accessible]
    if not linked:
        return
    names = [str(accessible[dataset_id].get("name") or f"Набор {dataset_id}") for dataset_id in linked]
    with st.container(border=True):
        st.markdown("**Последний импорт**")
        st.caption(" · ".join(names[:6]) + (" …" if len(names) > 6 else ""))
        st.caption(
            "«Отменить импорт» уберёт эти наборы только из текущего проекта. "
            "Исходные файлы, анализы и общая библиотека останутся на месте."
        )
        if st.button("↶ Отменить этот импорт", key=f"undo_recent_import_{project_id}", width="stretch"):
            for dataset_id in linked:
                unlink_dataset_from_project(int(project_id), int(dataset_id))
            st.session_state.pop("workflow_recent_dataset_ids", None)
            st.session_state.pop("workflow_recent_import_target", None)
            st.success(f"Убрано из проекта наборов: {len(linked)}. Данные в общей базе сохранены.")
            st.rerun()


def _render_table_with_locked_provenance(
    project_id: int,
    name: str,
    data: bytes,
    token: str,
) -> list[int]:
    """Run staging explicitly and keep already-recorded external provenance stable."""
    source_widget_key = f"universal_source_kind_{token}"
    study_key = f"universal_study_id_{token}"
    lock_key = f"universal_locked_source_kind_{token}"
    locked_kind = st.session_state.get(lock_key)
    if locked_kind:
        st.session_state[source_widget_key] = str(locked_kind)

    st.caption(
        "Для первичной петрографической разметки используйте Textural zone "
        "(ядро, кайма, реакционная зона). Generation оставляйте для химической интерпретации."
    )
    result = staged_intake.render_table_import_v0154(
        universal_intake._render_table_import,
        int(project_id),
        name,
        data,
        token,
    )

    if st.session_state.get(study_key) is not None:
        current_kind = str(st.session_state.get(source_widget_key) or "")
        if current_kind:
            st.session_state[lock_key] = current_kind
            st.caption(
                "Provenance внешнего источника уже записан для этой пачки. "
                "Если источник указан неверно, исправьте его явно в «Источники и литература»."
            )
    return [int(value) for value in result]


def _current_image_prefix(image_files: list[tuple[str, bytes]]) -> tuple[str, int] | None:
    if not image_files:
        return None
    batch = universal_intake_extensions._batch_token(image_files)
    index = min(int(st.session_state.get(f"univimg_index_{batch}", 0)), len(image_files) - 1)
    name, raw = image_files[index]
    token = universal_intake._file_token(name, raw)
    return f"univimg_{batch}_{token}", index


def _render_current_image_textural_markup(
    project_id: int,
    image_files: list[tuple[str, bytes]],
) -> None:
    """Attach observed Textural zone to the exact analysis rows chosen for this image."""
    current = _current_image_prefix(image_files)
    if current is None:
        return
    prefix, _index = current
    scope_label = st.session_state.get(f"{prefix}_scope", "К нескольким точкам анализа")
    if SCOPE_LABELS.get(scope_label) != SCOPE_ANALYSIS:
        return
    dataset_id = st.session_state.get(f"{prefix}_dataset_id")
    try:
        dataset_id = int(dataset_id)
    except (TypeError, ValueError):
        return

    accessible = {int(item["id"]) for item in list_accessible_datasets(int(project_id))}
    if dataset_id not in accessible:
        return
    linked_ids = [
        str(value).strip()
        for value in st.session_state.get(f"{prefix}_analysis_ids", []) or []
        if str(value).strip()
    ]
    if not linked_ids:
        return

    dataframe = load_dataset_dataframe(dataset_id, include_meta=True)
    if dataframe.empty or "_analysis_id" not in dataframe.columns:
        return
    dataframe = dataframe.copy()
    dataframe["_analysis_id"] = dataframe["_analysis_id"].astype(str)
    linked_ids = [value for value in linked_ids if value in set(dataframe["_analysis_id"])]
    if not linked_ids:
        return

    selected_rows = dataframe[dataframe["_analysis_id"].isin(linked_ids)].copy()
    labels = {
        str(row["_analysis_id"]): human_point_label(row)
        for _, row in selected_rows.iterrows()
    }
    st.markdown("#### Текстурная зона на текущем изображении")
    st.caption(
        "Textural zone — наблюдение на изображении. Это отдельное состояние от Work Group и Generation."
    )
    zone_ids = st.multiselect(
        "Какие связанные точки относятся к одной зоне",
        linked_ids,
        default=linked_ids,
        format_func=lambda value: labels.get(str(value), "Точка"),
        key=f"{prefix}_textural_zone_ids",
    )
    known = list(dict.fromkeys([
        *term_values(int(project_id), TEXTURAL_ZONE_COLUMN),
        *COMMON_TEXTURAL_ZONES,
    ]))
    choice = st.selectbox(
        "Textural zone",
        [*known, "Другое…"],
        key=f"{prefix}_textural_zone_choice",
    )
    zone = (
        st.text_input(
            "Своё название",
            placeholder="например, тонкая внешняя кайма",
            key=f"{prefix}_textural_zone_custom",
        ).strip()
        if choice == "Другое…" else str(choice).strip()
    )

    notice_key = f"{prefix}_textural_zone_notice"
    notice = st.session_state.pop(notice_key, "")
    if notice:
        st.success(str(notice))
    if st.button(
        "Назначить Textural zone выбранным точкам",
        type="primary",
        disabled=not zone_ids or not zone,
        width="stretch",
        key=f"{prefix}_save_textural_zone",
    ):
        count = set_annotation_with_journal(
            int(project_id),
            zone_ids,
            namespace="morphology",
            key="zone",
            value=zone,
            label=f"Текстурная зона → {zone}",
        )
        register_term(int(project_id), TEXTURAL_ZONE_COLUMN, zone, source="image_textural_zone")
        st.session_state[notice_key] = f"Текстурная зона «{zone}» сохранена для {count} точек."
        st.rerun()

    status_rows = []
    from petrolab.analytical_sessions import annotation_table
    annotations = annotation_table(linked_ids, namespace="morphology")
    for _, row in selected_rows.iterrows():
        analysis_id = str(row["_analysis_id"])
        status_rows.append({
            "Точка": labels.get(analysis_id, "Точка"),
            "Textural zone": str((annotations.get(analysis_id, {}) or {}).get("zone") or ""),
        })
    if status_rows:
        st.dataframe(
            pd.DataFrame(status_rows),
            width="stretch",
            hide_index=True,
            height=min(260, 36 * len(status_rows) + 38),
        )


def _current_import_ids(project_id: int) -> list[int]:
    accessible = {int(item["id"]) for item in list_accessible_datasets(int(project_id))}
    result: list[int] = []
    for key in list(st.session_state):
        if not str(key).startswith("universal_imported_"):
            continue
        for raw in st.session_state.get(key, []) or []:
            try:
                dataset_id = int(raw)
            except (TypeError, ValueError):
                continue
            if dataset_id in accessible and dataset_id not in result:
                result.append(dataset_id)
    return result


def _prepare_new_import_scope(dataset_ids: list[int]) -> None:
    for key in list(st.session_state):
        if str(key).startswith("multi_panel_") or str(key).startswith("_multi_panel_"):
            st.session_state.pop(key, None)
    clear_selection()
    clear_row_states()
    st.session_state["workflow_plot_dataset_ids"] = [int(value) for value in dataset_ids]


def _render_post_import_steps(project_id: int) -> None:
    dataset_ids = _current_import_ids(int(project_id))
    if not dataset_ids:
        return
    st.divider()
    render_section_header(
        "Продолжить исследование",
        "Те же только что импортированные данные переходят дальше без повторного выбора",
    )
    c1, c2, c3 = st.columns(3)
    if c1.button("Сравнить на диаграммах", type="primary", width="stretch", key="intake_continue_multi"):
        _prepare_new_import_scope(dataset_ids)
        st.session_state["workflow_plot_notice"] = (
            "Открыты только что импортированные наборы в нескольких химических проекциях."
        )
        navigate("multi_panel")
        st.rerun()
    if c2.button("Утвердить Generation", width="stretch", key="intake_continue_generation"):
        navigate("generations")
        st.rerun()
    if c3.button("Сравнить с другими данными", width="stretch", key="intake_continue_compare"):
        st.session_state["workflow_plot_dataset_ids"] = dataset_ids
        navigate("compare")
        st.rerun()


def render_intake_workflow(project_id: int) -> None:
    """Single user-facing intake path without runtime module monkey-patching."""
    _reset_transient_state_on_project_change(int(project_id))
    st.divider()
    render_section_header(
        "Универсальный +",
        "Перетащите Excel/CSV и/или фотографии. PetroLab сначала распознаёт их и ничего не пишет до проверки.",
    )
    uploads = st.file_uploader(
        "Файлы",
        type=["xlsx", "xlsm", "xls", "csv", "png", "jpg", "jpeg", "webp", "tif", "tiff", "bmp"],
        accept_multiple_files=True,
        key="universal_intake_files",
    )
    if not uploads:
        render_hint(
            "Типичный сценарий: Excel + фотографии → проверить таблицу → разнести строки по Sample → "
            "привязать изображения к тем же точкам."
        )
        render_recent_import_undo(int(project_id))
        _render_post_import_steps(int(project_id))
        return

    classified: list[tuple[str, bytes, str]] = []
    for index, upload in enumerate(uploads):
        data = upload.getvalue()
        guessed = universal_intake._guessed_kind(upload.name)
        kind = st.selectbox(
            upload.name,
            [universal_intake._KIND_TABLE, universal_intake._KIND_IMAGE, universal_intake._KIND_SKIP],
            index=[universal_intake._KIND_TABLE, universal_intake._KIND_IMAGE, universal_intake._KIND_SKIP].index(guessed),
            key=f"universal_kind_{index}_{universal_intake._file_token(upload.name, data)}",
            help="Расширение — только подсказка; тип файла подтверждается явно.",
        )
        classified.append((upload.name, data, kind))

    tables = [(name, data) for name, data, kind in classified if kind == universal_intake._KIND_TABLE]
    images = [(name, data) for name, data, kind in classified if kind == universal_intake._KIND_IMAGE]
    render_badges([
        (f"таблиц · {len(tables)}", "accent" if tables else "neutral"),
        (f"изображений · {len(images)}", "accent" if images else "neutral"),
    ])
    if len(tables) > 1:
        st.warning(
            "В одной пачке сейчас обрабатывается одна аналитическая таблица. "
            "Остальные пометьте «Не добавлять» и загрузите следующей пачкой."
        )
        return

    preferred_ids: list[int] = []
    if tables:
        name, data = tables[0]
        token = universal_intake._file_token(name, data)
        preferred_ids = _render_table_with_locked_provenance(int(project_id), name, data, token)
        if not preferred_ids:
            if images:
                st.info("Фотографии станут доступны для привязки сразу после безопасного импорта таблицы.")
            render_recent_import_undo(int(project_id))
            return

    if images:
        _render_current_image_textural_markup(int(project_id), images)
        universal_intake_extensions.render_image_wizard_multi_dataset(
            int(project_id), images, preferred_ids
        )

    render_recent_import_undo(int(project_id))
    _render_post_import_steps(int(project_id))
