from __future__ import annotations

import pandas as pd
import streamlit as st

from petrolab.group_styles import display_group_series


def _series_table(dataframe: pd.DataFrame, group_column: str) -> pd.DataFrame:
    labels = display_group_series(dataframe[group_column])
    order = labels.drop_duplicates().astype(str).tolist()
    counts = labels.value_counts(dropna=False).to_dict()
    return pd.DataFrame(
        {
            "Показывать": [True] * len(order),
            "Серия": order,
            "Точек": [int(counts.get(name, 0)) for name in order],
            "Порядок": list(range(1, len(order) + 1)),
        }
    )


def render_series_manager(
    dataframe: pd.DataFrame,
    group_column: str | None,
    *,
    key_prefix: str,
    expanded: bool = False,
) -> tuple[pd.DataFrame, tuple[str, ...]]:
    """Origin-like series visibility/order manager for grouped plots.

    This is deliberately a presentation-layer operation. Hiding a series here does
    not mutate SelectionContext, row Hide/Exclude state, Work Group or Generation.
    """
    if dataframe.empty or not group_column or group_column not in dataframe.columns:
        return dataframe, ()

    source = _series_table(dataframe, group_column)
    if source.empty:
        return dataframe, ()

    with st.expander("Серии", expanded=expanded):
        st.caption(
            "Как Object Manager в Origin: выключайте серии и меняйте порядок только для текущего графика. "
            "Исходные анализы и общий Selection при этом не меняются."
        )
        edited = st.data_editor(
            source,
            width="stretch",
            hide_index=True,
            disabled=["Серия", "Точек"],
            column_config={
                "Показывать": st.column_config.CheckboxColumn("Видно", width="small"),
                "Серия": st.column_config.TextColumn("Серия", width="large"),
                "Точек": st.column_config.NumberColumn("Точек", width="small"),
                "Порядок": st.column_config.NumberColumn(
                    "Порядок", min_value=1, max_value=max(1, len(source)), step=1, width="small"
                ),
            },
            key=f"{key_prefix}_series_manager",
        )

    visible = edited.loc[edited["Показывать"].fillna(False).astype(bool)].copy()
    if visible.empty:
        st.info("Все серии выключены. Включите хотя бы одну в «Серии».")
        return dataframe.iloc[0:0].copy(), ()

    positions = pd.to_numeric(visible["Порядок"], errors="coerce")
    if positions.isna().any() or positions.duplicated().any():
        st.warning("Порядок серий должен состоять из уникальных чисел. Пока используется исходный порядок.")
        ordered_names = visible["Серия"].astype(str).tolist()
    else:
        visible = visible.assign(_position=positions)
        ordered_names = visible.sort_values("_position", kind="stable")["Серия"].astype(str).tolist()

    labels = display_group_series(dataframe[group_column]).astype(str)
    pieces = [dataframe.loc[labels.eq(name)].copy() for name in ordered_names]
    result = pd.concat(pieces, axis=0) if pieces else dataframe.iloc[0:0].copy()
    return result, tuple(ordered_names)
