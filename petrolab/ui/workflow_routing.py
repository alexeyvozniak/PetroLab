from __future__ import annotations

import streamlit as st

from petrolab.db import get_dataset


def route_fresh_import_to_workflow() -> None:
    """Open the most useful next screen once for each newly imported batch.

    Only the automatic rerun immediately after import is intercepted. A later manual visit to
    «Новые анализы» stays where the user put it.
    """
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
