from __future__ import annotations

import pandas as pd
import streamlit as st

from petrolab.dataframe_utils import apply_quick_filter, row_identity
from petrolab.services.image_service import SCOPE_ANALYSIS, SCOPE_DATASET, SCOPE_FIELD


IMAGE_KINDS = [
    "BSE",
    "EDS",
    "Оптическая микрофотография",
    "Карта элементов",
    "Фото обнажения",
    "Фото образца",
    "Фото шлифа / препарата",
    "Другое",
]
SCOPE_LABELS = {
    "К нескольким точкам анализа": SCOPE_ANALYSIS,
    "К образцу, шлифу, зерну или поколению": SCOPE_FIELD,
    "Ко всему набору": SCOPE_DATASET,
    "Не импортировать": "skip",
}


def assignment_error(prefix: str, scope_type: str) -> str | None:
    if scope_type == SCOPE_ANALYSIS and not st.session_state.get(f"{prefix}_analysis_ids"):
        return "Выберите хотя бы одну аналитическую точку или другой тип привязки."
    if scope_type == SCOPE_FIELD:
        if not st.session_state.get(f"{prefix}_field_column") or not st.session_state.get(f"{prefix}_field_value"):
            return "Выберите поле и значение."
    return None


def analysis_id_labels(dataframe: pd.DataFrame) -> dict[str, str]:
    result: dict[str, str] = {}
    used_labels: set[str] = set()
    for _, row in dataframe.iterrows():
        analysis_id = str(row["_analysis_id"])
        base = f"{row_identity(row)} · Excel {row.get('_source_row', '—')} · {analysis_id[:8]}"
        label = base
        if label in used_labels:
            label = f"{base} · {analysis_id[8:12]}"
        used_labels.add(label)
        result[analysis_id] = label
    return result


def render_multi_point_controls(prefix: str, dataframe: pd.DataFrame) -> None:
    query = st.text_input(
        "Поиск по образцу / зерну / точке",
        key=f"{prefix}_point_query",
        placeholder="Например: N-7, зерно 14 или N-X1",
    )
    full_labels = analysis_id_labels(dataframe)
    filtered = apply_quick_filter(dataframe, query)
    limit = 5000
    if len(filtered) > limit:
        st.caption(
            f"Найдено {len(filtered):,} точек; в список выбора показаны первые {limit:,}. "
            "Уточните поиск, чтобы нужная точка точно попала в список."
            .replace(",", " ")
        )
    filtered_ids = [str(value) for value in filtered["_analysis_id"].head(limit).tolist()]
    selected_key = f"{prefix}_analysis_ids"
    previous = [str(value) for value in st.session_state.get(selected_key, [])]
    valid_previous = [value for value in previous if value in full_labels]
    option_ids = list(dict.fromkeys(valid_previous + filtered_ids))
    if selected_key not in st.session_state or valid_previous != previous:
        st.session_state[selected_key] = valid_previous
    st.multiselect(
        "Точки, видимые на этой фотографии",
        option_ids,
        format_func=lambda analysis_id: full_labels.get(analysis_id, analysis_id[:8]),
        key=selected_key,
    )
    st.caption(f"Выбрано точек: {len(st.session_state.get(selected_key, []))}.")


def render_field_controls(prefix: str, dataframe: pd.DataFrame) -> None:
    candidates = [
        column
        for column in ("Sample", "ThinSection", "Thin section", "Шлиф", "Препарат", "Grain", "Generation", "Point")
        if column in dataframe.columns and dataframe[column].notna().any()
    ]
    if not candidates:
        st.warning(
            "Для semantic field-link нужны Sample, Grain, Generation или Point. "
            "Используйте связь с аналитическими точками или со всем набором."
        )
        return
    column = st.selectbox("Поле", candidates, key=f"{prefix}_field_column")
    values = sorted(dataframe[column].dropna().astype(str).unique().tolist())
    value_key = f"{prefix}_field_value"
    if not values:
        st.session_state.pop(value_key, None)
        st.warning("В выбранном поле нет непустых значений.")
        return
    if st.session_state.get(value_key) not in values:
        st.session_state[value_key] = values[0]
    st.selectbox("Значение", values, key=value_key)


def clear_wizard_state(dataset_id: int) -> None:
    wizard_prefix = f"imgwiz_{dataset_id}_"
    for key in list(st.session_state):
        if str(key).startswith(wizard_prefix) or key in {
            f"image_wizard_index_{dataset_id}",
            f"image_wizard_review_{dataset_id}",
        }:
            del st.session_state[key]
    epoch_key = f"image_upload_epoch_{dataset_id}"
    st.session_state[epoch_key] = int(st.session_state.get(epoch_key, 0)) + 1
