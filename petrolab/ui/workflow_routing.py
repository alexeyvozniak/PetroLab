from __future__ import annotations

import streamlit as st

from petrolab.db import get_dataset
from petrolab.derived import load_unified_with_derived
from petrolab.smart_start import recommendations
from petrolab.source_registry import link_dataset_to_study


def _link_pending_study(datasets: list[dict]) -> None:
    """Finish the external-data intake without a redundant manual linking step."""
    pending = st.session_state.get("pending_study_id")
    if pending is None or not datasets:
        return
    linked = 0
    warnings: list[str] = []
    for dataset in datasets:
        try:
            link_dataset_to_study(
                int(dataset["id"]), int(pending),
                source_table=str(dataset.get("source_sheet") or ""),
            )
            linked += 1
        except ValueError as exc:
            warnings.append(str(exc))
    if linked:
        st.session_state["workflow_study_linked_count"] = linked
        st.session_state.pop("pending_study_id", None)
    if warnings:
        st.session_state["workflow_study_link_warnings"] = warnings


def route_fresh_import_to_workflow() -> None:
    """Open the most useful next screen once for each newly imported batch."""
    recent = tuple(
        int(value)
        for value in st.session_state.get("workflow_recent_dataset_ids", [])
        if value is not None
    )
    if not recent:
        return
    token = ",".join(str(value) for value in recent)
    if str(st.session_state.get("_workflow_import_redirect_token", "")) == token:
        return
    if str(st.session_state.get("nav_route", "home")) != "sources":
        return

    st.session_state["_workflow_import_redirect_token"] = token
    datasets = []
    for dataset_id in recent:
        try:
            datasets.append(get_dataset(int(dataset_id)))
        except (KeyError, ValueError):
            continue

    _link_pending_study(datasets)

    mixed = next(
        (item for item in datasets if str(item.get("mineral_key") or "generic") == "generic"),
        None,
    )
    if mixed is not None:
        st.session_state["workflow_mixed_dataset_id"] = int(mixed["id"])
        st.session_state["workflow_focus_dataset_id"] = int(mixed["id"])
        st.session_state["nav_route"] = "mixed_minerals"
        return

    focus_id = int(datasets[0]["id"]) if datasets else int(recent[0])
    st.session_state["workflow_focus_dataset_id"] = focus_id
    st.session_state["nav_route"] = "workflow"


def apply_smart_plot_defaults() -> None:
    """Prefill the ordinary XY editor with a mineral-aware starting pair.

    The user remains in the normal plot editor and can change every axis/style immediately.
    """
    if str(st.session_state.get("nav_route", "")) != "plots":
        return
    ids = [int(value) for value in st.session_state.get("workflow_plot_dataset_ids", []) if value is not None]
    if not ids:
        return
    token = ",".join(str(value) for value in ids)
    if str(st.session_state.get("_smart_plot_defaults_token", "")) == token:
        return
    st.session_state["_smart_plot_defaults_token"] = token
    try:
        dataset = get_dataset(ids[0])
        frame = load_unified_with_derived(None, ids)
    except (KeyError, ValueError):
        return
    choices = [item for item in recommendations(str(dataset.get("mineral_key") or "generic"), frame.columns) if item.route == "plots" and item.x and item.y]
    if not choices:
        return
    first = choices[0]
    st.session_state["quick_x"] = first.x
    st.session_state["quick_y"] = first.y
    st.session_state["workflow_plot_notice"] = f"PetroLab предложил старт: {first.title}. Оси и оформление можно сразу изменить."
