from __future__ import annotations

import pandas as pd
import streamlit as st

from petrolab.dataframe_utils import dataset_label
from petrolab.db import list_accessible_datasets, load_dataset_dataframe
from petrolab.scientific_context import add_assemblage_members, create_assemblage, list_assemblages
from petrolab.ui.layout import render_hint, render_page_header
from petrolab.ui.project_context import active_project_id


def _equilibrium_dataset_map(datasets: list[dict]) -> dict[str, dict]:
    """Build a selector that cannot collapse same-name/same-mineral datasets."""
    return {dataset_label(dataset): dataset for dataset in datasets}


def render_equilibrium_page() -> None:
    render_page_header(
        "Равновесные пары",
        "Выберите конкретные анализы, а не все точки одной породы. Это основа для Kd и парной термобарометрии.",
        eyebrow="Исследование",
    )
    project_id = active_project_id()
    if project_id is None:
        st.info("Сначала выберите проект.")
        return
    datasets = list_accessible_datasets(project_id)
    if not datasets:
        st.info("В проекте пока нет анализов.")
        return

    render_hint("Сначала создайте candidate-ассоциацию. После петрографической проверки её можно считать равновесной.")
    labels = _equilibrium_dataset_map(datasets)
    selected = st.multiselect(
        "Наборы",
        list(labels),
        default=list(labels)[:1],
        key="equilibrium_datasets",
    )
    frames = [load_dataset_dataframe(int(labels[label]["id"])) for label in selected]
    data = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if data.empty:
        return

    ids = data["_analysis_id"].astype(str).tolist()
    chosen = st.multiselect("Точки", ids, key="equilibrium_points")
    name = st.text_input(
        "Название",
        placeholder="Напр.: PG-6, Cpx rim + glass",
        key="equilibrium_name",
    )
    phases = {int(dataset["id"]): str(dataset["mineral_key"]) for dataset in datasets}
    if st.button(
        "Создать ассоциацию",
        type="primary",
        disabled=not chosen or not name.strip(),
        key="equilibrium_create",
    ):
        assemblage_id = create_assemblage(project_id, name, equilibrium_status="candidate")
        members = []
        for analysis_id in chosen:
            dataset_id = int(
                data.loc[data["_analysis_id"].astype(str) == analysis_id, "_dataset_id"].iloc[0]
            )
            members.append({"analysis_id": analysis_id, "phase": phases[dataset_id]})
        add_assemblage_members(assemblage_id, members)
        st.success("Ассоциация создана. Она пока имеет статус candidate.")
        st.rerun()

    rows = list_assemblages(project_id)
    if rows:
        st.dataframe(
            pd.DataFrame(rows)[["name", "equilibrium_status", "member_count", "updated_at"]],
            hide_index=True,
            width="stretch",
        )
