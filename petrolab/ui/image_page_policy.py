from __future__ import annotations

import streamlit as st

from petrolab.dataframe_utils import apply_quick_filter


def install() -> None:
    from petrolab.ui.pages import images as page

    if getattr(page, "_petrolab_image_policy_installed", False):
        return

    def render_multi_point_controls(prefix: str, dataframe) -> None:
        query = st.text_input(
            "Поиск по образцу / зерну / точке",
            key=f"{prefix}_point_query",
            placeholder="Например: N-7, зерно 14 или N-X1",
        )
        full_labels = page._analysis_id_labels(dataframe)
        filtered = apply_quick_filter(dataframe, query)
        limit = 5000
        if len(filtered) > limit:
            st.caption(
                f"Найдено {len(filtered):,} точек; в список выбора показаны первые {limit:,}. "
                "Уточните поиск, чтобы нужная точка точно попала в список."
                .replace(",", " ")
            )
        filtered_ids = [
            str(value) for value in filtered["_analysis_id"].head(limit).tolist()
        ]
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

    def render_field_controls(prefix: str, dataframe) -> None:
        candidates = [
            column for column in ("Sample", "Grain", "Generation", "Point")
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

    page._render_multi_point_controls = render_multi_point_controls
    page._render_field_controls = render_field_controls
    page._petrolab_image_policy_installed = True
