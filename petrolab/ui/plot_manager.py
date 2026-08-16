from __future__ import annotations

import pandas as pd
import streamlit as st

from petrolab.group_styles import display_group_series
from petrolab.ui.plot_spec import MULTI_PANEL_VISIBLE_SERIES_KEY
from petrolab.ui.selection_context import set_selection


def _series_table(
    dataframe: pd.DataFrame,
    group_column: str,
    *,
    visible_series: tuple[str, ...] | list[str] | None = None,
) -> pd.DataFrame:
    labels = display_group_series(dataframe[group_column])
    order = labels.drop_duplicates().astype(str).tolist()
    counts = labels.value_counts(dropna=False).to_dict()
    initial = None if visible_series is None else {str(value) for value in visible_series}
    return pd.DataFrame(
        {
            "Показывать": [True if initial is None else name in initial for name in order],
            "В отбор": [False] * len(order),
            "Серия": order,
            "Точек": [int(counts.get(name, 0)) for name in order],
            "Порядок": list(range(1, len(order) + 1)),
        }
    )


def _selected_series_ids(
    dataframe: pd.DataFrame,
    group_column: str,
    edited: pd.DataFrame,
) -> tuple[list[str], list[str]]:
    if "_analysis_id" not in dataframe.columns or "В отбор" not in edited.columns:
        return [], []
    names = edited.loc[edited["В отбор"].fillna(False).astype(bool), "Серия"].astype(str).tolist()
    if not names:
        return [], []
    labels = display_group_series(dataframe[group_column]).astype(str)
    ids = dataframe.loc[labels.isin(set(names)), "_analysis_id"].astype(str).tolist()
    return ids, names


def _incoming_visible_series(key_prefix: str) -> tuple[str, ...] | None:
    if key_prefix != "multi_panel":
        return None
    raw = st.session_state.pop(MULTI_PANEL_VISIBLE_SERIES_KEY, None)
    if not isinstance(raw, (list, tuple)):
        return None
    # A new PlotSpec must win over stale data_editor widget state from an older
    # multi-panel visit. This happens before the widget is instantiated.
    st.session_state.pop(f"{key_prefix}_series_manager", None)
    return tuple(str(value) for value in raw if str(value))


def render_series_manager(
    dataframe: pd.DataFrame,
    group_column: str | None,
    *,
    key_prefix: str,
    expanded: bool = False,
    initial_visible_series: tuple[str, ...] | list[str] | None = None,
    widget_token: str = "",
) -> tuple[pd.DataFrame, tuple[str, ...]]:
    """Origin-like series visibility/order manager with JMP-linked selection.

    Show/Hide here is presentation-only and does not mutate SelectionContext or
    row Hide/Exclude state. The explicit `В отбор` column is a separate action:
    selected series can replace/add/subtract their analysis IDs in the canonical
    SelectionContext without changing Work Group or Generation.

    ``initial_visible_series`` and ``widget_token`` let a canonical PlotSpec resume
    a compact workspace without mutating global row state. A new token deliberately
    starts a fresh editor state from the supplied PlotSpec; ordinary reruns keep the
    same token and therefore preserve the user's local series edits.
    """
    if dataframe.empty or not group_column or group_column not in dataframe.columns:
        return dataframe, ()

    incoming = _incoming_visible_series(key_prefix)
    if initial_visible_series is not None:
        incoming = tuple(str(value) for value in initial_visible_series if str(value))
    source = _series_table(dataframe, group_column, visible_series=incoming)
    if source.empty:
        return dataframe, ()

    token = str(widget_token or "").strip()
    editor_key = f"{key_prefix}_series_manager" + (f"_{token}" if token else "")

    with st.expander("Серии", expanded=expanded):
        st.caption(
            "Как Object Manager в Origin: «Видно» и «Порядок» меняют только текущий график. "
            "«В отбор» связывает серию с общим JMP-подобным Selection."
        )
        edited = st.data_editor(
            source,
            width="stretch",
            hide_index=True,
            disabled=["Серия", "Точек"],
            column_config={
                "Показывать": st.column_config.CheckboxColumn("Видно", width="small"),
                "В отбор": st.column_config.CheckboxColumn("В отбор", width="small"),
                "Серия": st.column_config.TextColumn("Серия", width="large"),
                "Точек": st.column_config.NumberColumn("Точек", width="small"),
                "Порядок": st.column_config.NumberColumn(
                    "Порядок", min_value=1, max_value=max(1, len(source)), step=1, width="small"
                ),
            },
            key=editor_key,
        )

        selected_ids, selected_names = _selected_series_ids(dataframe, group_column, edited)
        if selected_names:
            st.caption(f"Для отбора: {len(selected_names)} сер. · {len(selected_ids)} анализов")
            s1, s2, s3 = st.columns(3)
            label = ", ".join(selected_names[:3]) + ("…" if len(selected_names) > 3 else "")
            if s1.button("Заменить отбор", width="stretch", key=f"{key_prefix}_series_select_replace"):
                set_selection(selected_ids, origin=f"Серии · {group_column}", mode="replace", label=label)
                st.rerun()
            if s2.button("Добавить", width="stretch", key=f"{key_prefix}_series_select_add"):
                set_selection(selected_ids, origin=f"Серии · {group_column}", mode="add", label=label)
                st.rerun()
            if s3.button("Вычесть", width="stretch", key=f"{key_prefix}_series_select_subtract"):
                set_selection(selected_ids, origin=f"Серии · {group_column}", mode="subtract", label=label)
                st.rerun()

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
