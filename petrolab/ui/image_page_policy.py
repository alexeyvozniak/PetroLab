from __future__ import annotations

import streamlit as st


def install() -> None:
    from petrolab.ui.pages import images as page

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

    page._render_field_controls = render_field_controls
