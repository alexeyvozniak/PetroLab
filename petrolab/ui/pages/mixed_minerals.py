from __future__ import annotations

import pandas as pd
import streamlit as st

from petrolab.db import list_datasets, load_dataset_dataframe
from petrolab.minerals.registry import MINERALS
from petrolab.phase_suggestions import (
    SUGGESTED_MINERAL_COLUMN,
    SUGGESTION_CONFIDENCE_COLUMN,
    SUGGESTION_REASON_COLUMN,
    attach_phase_suggestions,
    materialize_confirmed_phases,
)
from petrolab.ui.layout import render_badges, render_page_header
from petrolab.ui.project_context import active_project_id


def render_mixed_minerals_page() -> None:
    render_page_header(
        "Разбор смешанного файла",
        "Быстро разделите один сырой зондовский dataset на минералы. PetroLab предлагает только уверенные фазы; неоднозначные точки оставляет на проверку.",
        eyebrow="Данные",
    )
    project_id = active_project_id()
    if project_id is None:
        st.info("Сначала выберите проект.")
        return
    datasets = list_datasets(int(project_id))
    if not datasets:
        st.info("Сначала импортируйте сырой файл.")
        return
    by_id = {int(row["id"]): row for row in datasets}
    dataset_id = st.selectbox(
        "Сырой dataset",
        list(by_id),
        format_func=lambda value: f"{by_id[int(value)]['name']} · {by_id[int(value)]['mineral_key']} · {by_id[int(value)]['row_count']} точек",
        key="mixed_dataset",
    )
    dataset = by_id[int(dataset_id)]
    if str(dataset.get("mineral_key")) != "generic":
        st.warning("Для безопасного разбиения лучше выбирать dataset, импортированный как «Другой минерал / generic». Уже классифицированный набор тоже можно просмотреть, но материализация изменит его структуру.")
    frame = load_dataset_dataframe(int(dataset_id), include_meta=True)
    if frame.empty:
        st.info("В наборе нет точек.")
        return
    suggested = attach_phase_suggestions(frame)
    high = int((suggested[SUGGESTION_CONFIDENCE_COLUMN] == "high").sum())
    medium = int((suggested[SUGGESTION_CONFIDENCE_COLUMN] == "medium").sum())
    unresolved = len(suggested) - high - medium
    render_badges([(f"{len(suggested)} точек", "accent"), (f"{high} уверенно", "success"), (f"{medium} вероятно", "neutral"), (f"{unresolved} проверить", "warning")])
    st.caption("Это предварительное распознавание широких фаз по химическому составу, а не IMA-классификация. Подтверждение пользователя обязательно перед изменением структуры dataset.")

    display_cols = [column for column in ["_analysis_id", "Sample", "Grain", "Point", "SiO2", "TiO2", "Al2O3", "FeO", "FeOt", "MgO", "CaO", "Na2O", "K2O", "P2O5", "ZrO2", SUGGESTED_MINERAL_COLUMN, SUGGESTION_CONFIDENCE_COLUMN, SUGGESTION_REASON_COLUMN] if column in suggested.columns]
    review = suggested[display_cols].copy()
    review["Confirmed Mineral"] = review[SUGGESTED_MINERAL_COLUMN].where(review[SUGGESTION_CONFIDENCE_COLUMN].isin(["high", "medium"]), "")
    options = [""] + list(MINERALS)
    edited = st.data_editor(
        review,
        width="stretch",
        hide_index=True,
        disabled=[column for column in review.columns if column != "Confirmed Mineral"],
        column_config={
            "Confirmed Mineral": st.column_config.SelectboxColumn("Подтверждённый минерал", options=options),
            SUGGESTED_MINERAL_COLUMN: st.column_config.TextColumn("Предложение"),
            SUGGESTION_CONFIDENCE_COLUMN: st.column_config.TextColumn("Уверенность"),
            SUGGESTION_REASON_COLUMN: st.column_config.TextColumn("Почему"),
        },
        key=f"mixed_review_{dataset_id}",
    )
    assignments = {
        str(row["_analysis_id"]): str(row["Confirmed Mineral"])
        for _, row in edited.iterrows()
        if str(row.get("Confirmed Mineral", "")).strip()
    }
    st.caption(f"Подтверждено к разбиению: {len(assignments)} из {len(review)}. Неподтверждённые точки останутся в исходном mixed dataset.")
    confirm = st.checkbox("Я проверил назначение фаз и хочу переместить подтверждённые точки в mineral datasets", key=f"mixed_confirm_{dataset_id}")
    if st.button("Разделить подтверждённые точки", type="primary", disabled=not assignments or not confirm, key=f"mixed_materialize_{dataset_id}"):
        try:
            created = materialize_confirmed_phases(int(dataset_id), assignments)
            summary = ", ".join(f"{MINERALS.get(key, MINERALS['generic']).name_ru}: dataset {value}" for key, value in created.items())
            st.success("Разбиение завершено без дублирования analysis_id. " + summary)
            st.rerun()
        except Exception as exc:
            st.error(f"Разбиение остановлено: {exc}")
