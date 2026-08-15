"""Cross-page UI safety guards found by the full v0.15.5 audit.

The established page implementations stay intact.  These wrappers enforce three
contracts that are easy to violate in a rerun-driven UI:

1. a routed exact analysis selection survives Streamlit reruns until the user
   explicitly resets it;
2. a routed object/dataset id wins over stale selectbox state from an earlier
   visit;
3. irreversible mapping/formula deletes require the same target to be requested
   twice.
"""
from __future__ import annotations

from collections.abc import MutableMapping
from typing import Any

import streamlit as st

from petrolab.dataframe_utils import dataset_label
from petrolab.db import list_accessible_datasets
from petrolab.measurement_registry import list_entities
from petrolab.sample_registry import list_samples
from petrolab.slides import list_slide_images
from petrolab.ui.destructive_actions import confirm_then, pending_key, render_pending
from petrolab.ui.layout import render_section_header
from petrolab.ui.navigation import navigate
from petrolab.ui.project_context import active_project, active_project_id
from petrolab.ui.work_context import get_work_context

from . import analyses_dashboard as _analyses
from . import article_tables as _tables
from . import batch_edit as _batch
from . import formulae as _formulae
from . import global_search as _search_base
from . import guided_workflow as _guided
from . import home_dashboard as _home
from . import images_dashboard as _images
from . import mixed_minerals as _mixed
from . import object_workspace as _workspace
from . import slides as _slides
from . import thin_section_workspace as _thin_base
from . import v0151_wrappers as _thin_chain
from . import v0152_publication_wrappers as _multi_chain
from . import v0153_grain_profile_wrappers as _search_chain


_EDIT_A = "_audit_edit_exact_analysis_ids"
_EDIT_D = "_audit_edit_exact_dataset_ids"
_EDIT_C = "_audit_edit_exact_context"
_TABLE_A = "_audit_table_exact_analysis_ids"
_TABLE_D = "_audit_table_exact_dataset_ids"
_TABLE_C = "_audit_table_exact_context"
_BATCH_A = "_audit_batch_exact_analysis_ids"
_BATCH_D = "_audit_batch_exact_dataset_ids"


def _unique_strings(values) -> list[str]:
    return list(dict.fromkeys(str(value) for value in values or [] if str(value)))


def _unique_ints(values) -> list[int]:
    result: list[int] = []
    for value in values or []:
        try:
            number = int(value)
        except (TypeError, ValueError):
            continue
        if number not in result:
            result.append(number)
    return result


def _clear_persisted_exact(
    state: MutableMapping,
    analysis_key: str,
    dataset_key: str,
    context_key: str | None,
) -> None:
    state.pop(analysis_key, None)
    state.pop(dataset_key, None)
    if context_key:
        state.pop(context_key, None)


def _persist_exact_route(
    state: MutableMapping,
    *,
    incoming_analysis_key: str,
    incoming_dataset_key: str,
    incoming_context_key: str | None,
    persistent_analysis_key: str,
    persistent_dataset_key: str,
    persistent_context_key: str | None,
) -> tuple[list[str], list[int], dict[str, Any]]:
    """Keep an exact route alive across reruns, but let a new dataset-only route reset it."""
    has_analysis = incoming_analysis_key in state
    has_datasets = incoming_dataset_key in state

    # A deliberate new dataset-only route means "open this dataset", not
    # "keep the exact analysis ids from a previous visit".
    if has_datasets and not has_analysis:
        _clear_persisted_exact(
            state, persistent_analysis_key, persistent_dataset_key, persistent_context_key
        )

    if has_analysis:
        analysis_ids = _unique_strings(state.get(incoming_analysis_key, []))
        dataset_ids = _unique_ints(state.get(incoming_dataset_key, []))
        if analysis_ids:
            state[persistent_analysis_key] = analysis_ids
            state[persistent_dataset_key] = dataset_ids
            if persistent_context_key and incoming_context_key:
                context = state.get(incoming_context_key, {})
                state[persistent_context_key] = dict(context) if isinstance(context, dict) else {}
        else:
            _clear_persisted_exact(
                state, persistent_analysis_key, persistent_dataset_key, persistent_context_key
            )

    analysis_ids = _unique_strings(state.get(persistent_analysis_key, []))
    dataset_ids = _unique_ints(state.get(persistent_dataset_key, []))
    context: dict[str, Any] = {}
    if persistent_context_key:
        value = state.get(persistent_context_key, {})
        context = dict(value) if isinstance(value, dict) else {}

    if analysis_ids:
        state[incoming_analysis_key] = analysis_ids
        state[incoming_dataset_key] = dataset_ids
        if incoming_context_key:
            state[incoming_context_key] = context
    return analysis_ids, dataset_ids, context


def _render_exact_reset(
    *,
    count: int,
    label: str,
    reset_key: str,
    persistent_keys: tuple[str, ...],
    incoming_keys: tuple[str, ...],
    extra_clear: tuple[str, ...] = (),
) -> None:
    if count <= 0:
        return
    st.info(f"Точный отбор активен: {count} analysis_id. Он не расширяется после изменения виджетов или rerun.")
    if st.button(label, key=reset_key, width="stretch"):
        for key in (*persistent_keys, *incoming_keys, *extra_clear):
            st.session_state.pop(key, None)
        st.rerun()


def render_analyses_page() -> None:
    exact, _, _ = _persist_exact_route(
        st.session_state,
        incoming_analysis_key="workflow_edit_analysis_ids",
        incoming_dataset_key="workflow_edit_dataset_ids",
        incoming_context_key="workflow_edit_context",
        persistent_analysis_key=_EDIT_A,
        persistent_dataset_key=_EDIT_D,
        persistent_context_key=_EDIT_C,
    )
    _analyses.render_analyses_dashboard_page()
    _render_exact_reset(
        count=len(exact),
        label="Снять точный отбор и открыть наборы целиком",
        reset_key="audit_reset_edit_exact",
        persistent_keys=(_EDIT_A, _EDIT_D, _EDIT_C),
        incoming_keys=("workflow_edit_analysis_ids", "workflow_edit_dataset_ids", "workflow_edit_context"),
        extra_clear=("unified_editor_dashboard",),
    )


def render_article_tables_page() -> None:
    exact, _, _ = _persist_exact_route(
        st.session_state,
        incoming_analysis_key="workflow_table_analysis_ids",
        incoming_dataset_key="workflow_table_dataset_ids",
        incoming_context_key="workflow_table_context",
        persistent_analysis_key=_TABLE_A,
        persistent_dataset_key=_TABLE_D,
        persistent_context_key=_TABLE_C,
    )
    _tables.render_article_tables_page()
    _render_exact_reset(
        count=len(exact),
        label="Вернуться к обычному конструктору таблицы",
        reset_key="audit_reset_table_exact",
        persistent_keys=(_TABLE_A, _TABLE_D, _TABLE_C),
        incoming_keys=("workflow_table_analysis_ids", "workflow_table_dataset_ids", "workflow_table_context"),
    )


def render_batch_edit_page() -> None:
    exact, dataset_ids, _ = _persist_exact_route(
        st.session_state,
        incoming_analysis_key="batch_analysis_ids",
        incoming_dataset_key="batch_dataset_ids",
        incoming_context_key=None,
        persistent_analysis_key=_BATCH_A,
        persistent_dataset_key=_BATCH_D,
        persistent_context_key=None,
    )
    if dataset_ids:
        project_id = active_project_id()
        if project_id is not None:
            labels = {
                dataset_label(item): int(item["id"])
                for item in list_accessible_datasets(int(project_id))
            }
            selected = [label for label, dataset_id in labels.items() if dataset_id in dataset_ids]
            if selected:
                st.session_state["batch_edit_datasets"] = selected
    _batch.render_batch_edit_page()
    _render_exact_reset(
        count=len(exact),
        label="Снять точный отбор массового действия",
        reset_key="audit_reset_batch_exact",
        persistent_keys=(_BATCH_A, _BATCH_D),
        incoming_keys=("batch_analysis_ids", "batch_dataset_ids"),
    )


def _sync_id_widget(options: list[int], routed_value, widget_key: str) -> None:
    if not options:
        st.session_state.pop(widget_key, None)
        return
    try:
        routed = None if routed_value is None else int(routed_value)
    except (TypeError, ValueError):
        routed = None
    if routed in options:
        st.session_state[widget_key] = routed
        return
    try:
        current = int(st.session_state.get(widget_key))
    except (TypeError, ValueError):
        current = None
    if current not in options:
        st.session_state[widget_key] = options[0]


def render_guided_workflow_page() -> None:
    project_id = active_project_id()
    if project_id is not None:
        ids = [int(item["id"]) for item in list_accessible_datasets(int(project_id))]
        _sync_id_widget(ids, st.session_state.get("workflow_focus_dataset_id"), "workflow_dataset")
    _guided.render_guided_workflow_page()


def render_mixed_minerals_page() -> None:
    project_id = active_project_id()
    if project_id is not None:
        ids = [int(item["id"]) for item in list_accessible_datasets(int(project_id))]
        _sync_id_widget(ids, st.session_state.get("workflow_mixed_dataset_id"), "mixed_dataset")
    _mixed.render_mixed_minerals_page()


def render_images_page() -> None:
    project_id = active_project_id()
    if project_id is not None:
        datasets = list_accessible_datasets(int(project_id))
        mapping = {dataset_label(item): int(item["id"]) for item in datasets}
        requested = st.session_state.get("workflow_image_dataset_id")
        requested_label = next(
            (label for label, dataset_id in mapping.items() if requested is not None and int(dataset_id) == int(requested)),
            None,
        )
        if requested_label is not None:
            st.session_state["img_dataset"] = requested_label
        elif st.session_state.get("img_dataset") not in mapping:
            if mapping:
                st.session_state["img_dataset"] = next(iter(mapping))
            else:
                st.session_state.pop("img_dataset", None)
    _images.render_images_dashboard_page()


def _sample_widget_label(sample: dict) -> str:
    return f"{sample['name']} · {sample.get('locality') or 'местность не указана'} · id {int(sample['id'])}"


def _dataset_widget_label(dataset: dict) -> str:
    return f"{dataset['name']} · {dataset.get('mineral_key') or 'mineral ?'} · {int(dataset.get('row_count') or 0)} строк · id {int(dataset['id'])}"


def _sync_workspace_pending() -> None:
    project_id = active_project_id()
    if project_id is None:
        return
    sample_pending = st.session_state.pop("workspace_sample_id_pending", None)
    if sample_pending is not None:
        samples = {int(item["id"]): item for item in list_samples(int(project_id))}
        try:
            sample_id = int(sample_pending)
        except (TypeError, ValueError):
            sample_id = -1
        sample = samples.get(sample_id)
        if sample is not None:
            st.session_state["workspace_mode"] = "Sample"
            st.session_state["workspace_query_pending"] = str(sample["name"])
            st.session_state["workspace_sample"] = _sample_widget_label(sample)

    dataset_pending = st.session_state.pop("workspace_dataset_id_pending", None)
    if dataset_pending is not None:
        datasets = {int(item["id"]): item for item in list_accessible_datasets(int(project_id))}
        try:
            dataset_id = int(dataset_pending)
        except (TypeError, ValueError):
            dataset_id = -1
        dataset = datasets.get(dataset_id)
        if dataset is not None:
            st.session_state["workspace_mode"] = "Массив данных"
            st.session_state["workspace_query_pending"] = str(dataset["name"])
            st.session_state["workspace_dataset"] = _dataset_widget_label(dataset)


def render_object_workspace_page() -> None:
    _sync_workspace_pending()
    original_navigate = _workspace.navigate

    def navigate_with_physical_context(route: str) -> None:
        if route == "thin_section":
            project_id = active_project_id()
            context = get_work_context(project_id) if project_id is not None else None
            if context and context.get("sample_id") is not None:
                st.session_state["thin_section_sample_id_pending"] = int(context["sample_id"])
        original_navigate(route)

    _workspace.navigate = navigate_with_physical_context
    try:
        _workspace.render_object_workspace_page()
    finally:
        _workspace.navigate = original_navigate


def _open_recent_exact(item: dict) -> None:
    kind = str(item.get("kind") or "")
    selector = item.get("selector") or {}
    if kind == "sample":
        sample_id = selector.get("sample_id")
        if sample_id is not None:
            st.session_state["workspace_sample_id_pending"] = int(sample_id)
        st.session_state["workspace_mode"] = "Sample"
        st.session_state["workspace_query_pending"] = str(selector.get("sample") or item.get("label") or "")
        _home._go("workspace")
        return
    if kind == "dataset":
        dataset_ids = _unique_ints(selector.get("dataset_ids", []))
        if dataset_ids:
            st.session_state["workspace_dataset_id_pending"] = dataset_ids[0]
        st.session_state["workspace_mode"] = "Массив данных"
        st.session_state["workspace_query_pending"] = str(item.get("label") or "")
        _home._go("workspace")
        return
    if kind == "thin_section":
        thin_section_id = selector.get("thin_section_id")
        if thin_section_id is not None:
            st.session_state["thin_section_focus_id_pending"] = int(thin_section_id)
        _home._go("thin_section")
        return
    _home._go("workspace")


def render_home_page() -> None:
    original = _home._open_recent
    _home._open_recent = _open_recent_exact
    try:
        _home.render_home_dashboard_page()
    finally:
        _home._open_recent = original


def _open_exact_matches(samples: list[dict], datasets: list[dict], slide_images: list[dict]) -> None:
    groups = []
    if samples:
        groups.append("sample")
    if datasets:
        groups.append("dataset")
    if slide_images:
        groups.append("slide")
    if not groups:
        return

    render_section_header("Открыть найденное", "Выберите точный объект, а не первое текстовое совпадение")
    columns = st.columns(len(groups))
    for column, kind in zip(columns, groups):
        with column:
            if kind == "sample":
                by_id = {int(item["id"]): item for item in samples}
                selected = st.selectbox(
                    "Sample",
                    list(by_id),
                    format_func=lambda value: str(by_id[int(value)].get("name") or value),
                    key="audit_search_open_sample",
                )
                if st.button("Открыть Sample", key="audit_search_go_sample", width="stretch"):
                    item = by_id[int(selected)]
                    st.session_state["workspace_sample_id_pending"] = int(selected)
                    st.session_state["workspace_mode"] = "Sample"
                    st.session_state["workspace_query_pending"] = str(item.get("name") or "")
                    navigate("workspace")
                    st.rerun()
            elif kind == "dataset":
                by_id = {int(item["id"]): item for item in datasets}
                selected = st.selectbox(
                    "Массив",
                    list(by_id),
                    format_func=lambda value: str(by_id[int(value)].get("name") or value),
                    key="audit_search_open_dataset",
                )
                if st.button("Открыть массив", key="audit_search_go_dataset", width="stretch"):
                    item = by_id[int(selected)]
                    st.session_state["workspace_dataset_id_pending"] = int(selected)
                    st.session_state["workspace_mode"] = "Массив данных"
                    st.session_state["workspace_query_pending"] = str(item.get("name") or "")
                    navigate("workspace")
                    st.rerun()
            else:
                by_id = {int(item["id"]): item for item in slide_images}
                selected = st.selectbox(
                    "Снимок шлифа",
                    list(by_id),
                    format_func=lambda value: f"{by_id[int(value)].get('title') or value} · {by_id[int(value)].get('image_type') or ''}",
                    key="audit_search_open_slide",
                )
                if st.button("Открыть снимок", key="audit_search_go_slide", width="stretch"):
                    item = by_id[int(selected)]
                    section_id = item.get("thin_section_id")
                    if section_id is None:
                        navigate("slides")
                    else:
                        st.session_state["thin_section_focus_id_pending"] = int(section_id)
                        st.session_state["thin_image_focus_id_pending"] = int(selected)
                        navigate("thin_section")
                    st.rerun()


def render_global_search_page() -> None:
    original = _search_base._open_matches
    _search_base._open_matches = _open_exact_matches
    try:
        _search_chain.render_global_search_page()
    finally:
        _search_base._open_matches = original


def _sync_thin_section_target() -> None:
    project_id = active_project_id()
    if project_id is None:
        return
    sections = [item for item in list_entities(int(project_id)) if item.get("kind") == "thin_section"]
    by_id = {int(item["id"]): item for item in sections}
    ids = list(by_id)
    if not ids:
        st.session_state.pop("thin_section_selected", None)
        return

    pending_focus = st.session_state.get("thin_section_focus_id_pending")
    try:
        pending_id = None if pending_focus is None else int(pending_focus)
    except (TypeError, ValueError):
        pending_id = None

    sample_pending = st.session_state.pop("thin_section_sample_id_pending", None)
    if pending_id not in by_id and sample_pending is not None:
        try:
            sample_id = int(sample_pending)
        except (TypeError, ValueError):
            sample_id = -1
        candidates = [
            int(item["id"]) for item in sections
            if item.get("sample_id") is not None and int(item["sample_id"]) == sample_id
        ]
        if candidates:
            pending_id = candidates[0]
            st.session_state["thin_section_focus_id_pending"] = pending_id

    _sync_id_widget(ids, pending_id, "thin_section_selected")
    selected_section = int(st.session_state.get("thin_section_selected", ids[0]))
    images = [
        image for image in list_slide_images(int(project_id))
        if image.thin_section_id == selected_section
    ]
    image_ids = [int(image.id) for image in images]
    image_pending = st.session_state.pop("thin_image_focus_id_pending", None)
    _sync_id_widget(image_ids, image_pending, "thin_image_selected")


def _sync_multi_panel_section() -> None:
    project_id = active_project_id()
    if project_id is None:
        return
    ids = [
        int(item["id"]) for item in list_entities(int(project_id))
        if item.get("kind") == "thin_section"
    ]
    _sync_id_widget(ids, st.session_state.get("multi_panel_thin_section_id"), "multi_panel_section")


def render_multi_panel_page() -> None:
    _sync_multi_panel_section()
    _multi_chain.render_multi_panel_page()


def _render_pending_prefix(action_prefix: str, message: str) -> None:
    marker = pending_key(action_prefix)
    prefix = marker
    for key in list(st.session_state):
        text = str(key)
        if not text.startswith(prefix):
            continue
        action_name = text.removeprefix("_pending_destructive_")
        render_pending(action_name, message)


def _guard_delete(action_name: str, target, action) -> None:
    confirm_then(action_name, target, action)


def render_thin_section_workspace_page() -> None:
    _sync_thin_section_target()
    _render_pending_prefix(
        "audit_thin_marker_",
        "Удаление точки разметки изменит физические связи. Нажмите ту же кнопку удаления ещё раз для подтверждения.",
    )
    _render_pending_prefix(
        "audit_thin_field_",
        "Удаление области/контура нельзя считать безобидным UI-действием. Нажмите ту же кнопку ещё раз для подтверждения.",
    )
    original_marker = _thin_base.delete_slide_marker
    original_field = _thin_base._delete_field

    def guarded_marker(marker_id: int) -> None:
        _guard_delete(
            f"audit_thin_marker_{int(marker_id)}",
            int(marker_id),
            lambda: original_marker(int(marker_id)),
        )

    def guarded_field(field_id: int) -> None:
        _guard_delete(
            f"audit_thin_field_{int(field_id)}",
            int(field_id),
            lambda: original_field(int(field_id)),
        )

    _thin_base.delete_slide_marker = guarded_marker
    _thin_base._delete_field = guarded_field
    try:
        _thin_chain.render_thin_section_workspace_page()
    finally:
        _thin_base.delete_slide_marker = original_marker
        _thin_base._delete_field = original_field


def render_slides_page() -> None:
    _render_pending_prefix(
        "audit_slide_marker_",
        "Удаление метки разрывает её UI/аналитические связи. Нажмите удаление ещё раз для подтверждения.",
    )
    _render_pending_prefix(
        "audit_slide_image_",
        "Будут удалены превью/копия и связанные метки. Нажмите удаление снимка ещё раз для подтверждения.",
    )
    original_marker = _slides.delete_slide_marker
    original_image = _slides.delete_slide_image

    def guarded_marker(marker_id: int) -> None:
        _guard_delete(
            f"audit_slide_marker_{int(marker_id)}",
            int(marker_id),
            lambda: original_marker(int(marker_id)),
        )

    def guarded_image(image_id: int) -> None:
        _guard_delete(
            f"audit_slide_image_{int(image_id)}",
            int(image_id),
            lambda: original_image(int(image_id)),
        )

    _slides.delete_slide_marker = guarded_marker
    _slides.delete_slide_image = guarded_image
    try:
        _slides.render_slides_page()
    finally:
        _slides.delete_slide_marker = original_marker
        _slides.delete_slide_image = original_image


def render_formulae_page() -> None:
    _render_pending_prefix(
        "audit_formula_field_",
        "Сохранённая пользовательская формула будет удалена. Нажмите «Удалить» ещё раз для подтверждения.",
    )
    original = _formulae.delete_field

    def guarded(field_id: int) -> None:
        _guard_delete(
            f"audit_formula_field_{int(field_id)}",
            int(field_id),
            lambda: original(int(field_id)),
        )

    _formulae.delete_field = guarded
    try:
        _formulae.render_formulae_page()
    finally:
        _formulae.delete_field = original
