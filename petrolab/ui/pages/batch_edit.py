from __future__ import annotations

import streamlit as st

from petrolab.analysis_groups import attach_work_groups
from petrolab.dataframe_utils import apply_quick_filter, dataset_label
from petrolab.db import list_accessible_datasets
from petrolab.derived import load_unified_with_derived
from petrolab.generations import attach_generations
from petrolab.ui.batch_actions import render_batch_actions
from petrolab.ui.layout import render_badges, render_page_header
from petrolab.ui.project_context import active_project_id


def render_batch_edit_page() -> None:
    project_id = active_project_id()
    render_page_header(
        "Массовые действия",
        "Изменить фазу, Generation или морфологию сразу для группы точек — с журналом интерпретационных операций.",
        eyebrow="Интерпретация",
    )
    if project_id is None:
        st.info("Сначала создайте или выберите проект.")
        return
    datasets = list_accessible_datasets(int(project_id))
    if not datasets:
        st.info("В проекте пока нет анализов. Сначала добавьте данные.")
        return
    labels = {dataset_label(item): int(item["id"]) for item in datasets}
    requested = [int(value) for value in st.session_state.pop("batch_dataset_ids", [])]
    defaults = [label for label, dataset_id in labels.items() if dataset_id in requested] or list(labels)
    c1, c2 = st.columns([2.2, 1])
    selected = c1.multiselect("Наборы", list(labels), default=defaults, key="batch_edit_datasets")
    query = c2.text_input("Фильтр", key="batch_edit_query", placeholder="Sample, Grain, Point, Generation…")
    dataset_ids = [labels[label] for label in selected]
    if not dataset_ids:
        st.info("Выберите хотя бы один набор.")
        return
    frame = attach_generations(attach_work_groups(load_unified_with_derived(int(project_id), dataset_ids)))
    frame = apply_quick_filter(frame, query)
    requested_ids = {str(value) for value in st.session_state.pop("batch_analysis_ids", [])}
    if requested_ids:
        frame = frame[frame["_analysis_id"].astype(str).isin(requested_ids)].copy()
    render_badges([
        (f"{len(frame):,} точек".replace(",", " "), "accent"),
        (f"{len(dataset_ids)} наборов", "neutral"),
    ])
    if frame.empty:
        st.info("В текущем отборе нет точек.")
        return
    render_batch_actions(frame, int(project_id))
