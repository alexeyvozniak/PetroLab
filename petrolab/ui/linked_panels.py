"""Связанные интерактивные XY-панели с единым отбором по устойчивому идентификатору."""
from __future__ import annotations

import math
from collections.abc import Iterable

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.colors import qualitative
from plotly.subplots import make_subplots


LINKED_SELECTION_SUFFIX = "_linked_selection_ids"


def _clean_id(value: object) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def _event_points(event) -> list[object] | None:
    if event is None:
        return None
    selection = getattr(event, "selection", None)
    if selection is None and isinstance(event, dict):
        selection = event.get("selection")
    if selection is None:
        return None
    points = getattr(selection, "points", None)
    if points is None and isinstance(selection, dict):
        points = selection.get("points")
    return list(points or [])


def selection_ids_from_event(event) -> list[str] | None:
    """Извлечь устойчивые ID из click/box/lasso события Plotly.

    `None` означает, что нового selection-события не было. Пустой список означает
    явное снятие выбора и поэтому должен очищать общую подсветку.
    """
    points = _event_points(event)
    if points is None:
        return None
    result: list[str] = []
    for point in points:
        custom = getattr(point, "customdata", None)
        if custom is None and isinstance(point, dict):
            custom = point.get("customdata")
        if isinstance(custom, (list, tuple)):
            custom = custom[0] if custom else ""
        value = _clean_id(custom)
        if value and value not in result:
            result.append(value)
    return result


def _panel_frame(dataframe: pd.DataFrame, x: str, y: str, log_x: bool, log_y: bool) -> pd.DataFrame:
    work = dataframe.copy()
    work[x] = pd.to_numeric(work[x], errors="coerce")
    work[y] = pd.to_numeric(work[y], errors="coerce")
    work = work.dropna(subset=[x, y])
    if log_x:
        work = work[work[x] > 0]
    if log_y:
        work = work[work[y] > 0]
    return work


def _hover_text(frame: pd.DataFrame, id_column: str) -> list[str]:
    fields = [
        column for column in (
            "Sample", "Rock", "Минерал", "Textural zone", "PetroLab Generation",
            "Generation", "Рабочая группа", "Рабочий класс породы", "Источник", "Источник / статья",
            "Источник данных", "Lithology", "Massif",
        )
        if column in frame.columns
    ]
    result: list[str] = []
    for _, row in frame.iterrows():
        parts = [f"ID: {_clean_id(row.get(id_column))}"]
        for field in fields:
            value = _clean_id(row.get(field))
            if value:
                parts.append(f"{field}: {value}")
        result.append("<br>".join(parts))
    return result


def _group_colors(dataframe: pd.DataFrame, group_column: str | None) -> dict[str, str]:
    if not group_column or group_column not in dataframe.columns:
        return {"Данные": qualitative.Plotly[0]}
    labels = dataframe[group_column].astype("string").fillna("Без группы").replace("", "Без группы")
    names = [str(value) for value in labels.unique().tolist()]
    return {name: qualitative.Plotly[index % len(qualitative.Plotly)] for index, name in enumerate(names)}


def _available_ids(dataframe: pd.DataFrame, id_column: str) -> set[str]:
    if id_column not in dataframe.columns:
        return set()
    return {_clean_id(value) for value in dataframe[id_column].tolist() if _clean_id(value)}


def build_linked_panel_figure(
    dataframe: pd.DataFrame,
    panels: list[dict],
    *,
    id_column: str,
    selected_ids: Iterable[str] = (),
    group_column: str | None = None,
    columns: int = 2,
    height_per_row: int = 330,
) -> go.Figure:
    """Построить до десяти связанных панелей; один ID подсвечивается везде, где он видим."""
    if id_column not in dataframe.columns:
        raise ValueError(f"Нет устойчивого идентификатора {id_column}")
    valid = [
        dict(panel) for panel in panels
        if panel.get("x") in dataframe.columns and panel.get("y") in dataframe.columns
    ]
    if not valid:
        raise ValueError("Нет валидных панелей")
    valid = valid[:10]
    ncols = max(1, min(int(columns), 4, len(valid)))
    nrows = int(math.ceil(len(valid) / ncols))
    titles = [str(panel.get("title") or f"{panel['y']} vs {panel['x']}") for panel in valid]
    figure = make_subplots(rows=nrows, cols=ncols, subplot_titles=titles)

    selected = {_clean_id(value) for value in selected_ids if _clean_id(value)} & _available_ids(dataframe, id_column)
    colors = _group_colors(dataframe, group_column)
    legend_seen: set[str] = set()

    for panel_index, panel in enumerate(valid):
        row = panel_index // ncols + 1
        col = panel_index % ncols + 1
        x = str(panel["x"])
        y = str(panel["y"])
        log_x = bool(panel.get("log_x", False))
        log_y = bool(panel.get("log_y", False))
        work = _panel_frame(dataframe, x, y, log_x, log_y)
        if work.empty:
            continue

        if group_column and group_column in work.columns:
            labels = work[group_column].astype("string").fillna("Без группы").replace("", "Без группы")
            groups = [(str(name), work.loc[labels == name]) for name in labels.unique().tolist()]
        else:
            groups = [("Данные", work)]

        for group_name, part in groups:
            ids = [_clean_id(value) for value in part[id_column].tolist()]
            selectedpoints = [index for index, value in enumerate(ids) if value in selected] if selected else None
            trace = go.Scattergl(
                x=part[x],
                y=part[y],
                mode="markers",
                name=group_name,
                legendgroup=group_name,
                showlegend=group_name not in legend_seen,
                customdata=[[value] for value in ids],
                text=_hover_text(part, id_column),
                hovertemplate="%{text}<br>X: %{x}<br>Y: %{y}<extra></extra>",
                selectedpoints=selectedpoints,
                marker={"size": 8, "opacity": 0.88, "color": colors.get(group_name)},
                # Scattergl позволяет для выбранных точек менять размер, цвет и прозрачность,
                # но не поддерживает отдельную обводку внутри selected.marker.
                selected={"marker": {"size": 13, "opacity": 1.0, "color": colors.get(group_name)}},
                unselected={"marker": {"opacity": 0.18}} if selected else None,
            )
            figure.add_trace(trace, row=row, col=col)
            legend_seen.add(group_name)

        figure.update_xaxes(
            title_text=str(panel.get("x_label") or x),
            type="log" if log_x else "linear",
            row=row,
            col=col,
        )
        figure.update_yaxes(
            title_text=str(panel.get("y_label") or y),
            type="log" if log_y else "linear",
            row=row,
            col=col,
        )

    figure.update_layout(
        height=max(360, int(height_per_row) * nrows),
        dragmode="lasso",
        clickmode="event+select",
        selectdirection="any",
        uirevision="petrolab-linked-panels",
        margin={"l": 30, "r": 20, "t": 70, "b": 35},
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "left", "x": 0},
    )
    return figure


def render_linked_panel_selection(
    dataframe: pd.DataFrame,
    panels: list[dict],
    *,
    id_column: str,
    key: str,
    group_column: str | None = None,
    columns: int = 2,
) -> list[str]:
    """Показать связанные панели и вернуть видимую часть текущего click/box/lasso отбора.

    Любое новое выделение заменяет предыдущее. Если фильтр временно скрывает часть
    выбранных ID, они могут снова появиться после снятия фильтра, но действия над
    классом/Generation получают только точки, которые видимы сейчас.
    """
    state_key = f"{key}{LINKED_SELECTION_SUFFIX}"
    ignore_key = f"{key}_ignore_selection_once"
    stored = [
        _clean_id(value) for value in st.session_state.get(state_key, []) or []
        if _clean_id(value)
    ]
    available = _available_ids(dataframe, id_column)
    visible_selected = [value for value in stored if value in available]

    figure = build_linked_panel_figure(
        dataframe,
        panels,
        id_column=id_column,
        selected_ids=visible_selected,
        group_column=group_column,
        columns=columns,
    )
    event = st.plotly_chart(
        figure,
        width="stretch",
        key=f"{key}_plotly",
        on_select="rerun",
        selection_mode=("points", "box", "lasso"),
        config={"scrollZoom": True, "displaylogo": False},
    )
    if st.session_state.pop(ignore_key, False):
        incoming = None
    else:
        incoming = selection_ids_from_event(event)
    if incoming is not None and incoming != stored:
        st.session_state[state_key] = incoming
        st.rerun()

    stored = [
        _clean_id(value) for value in st.session_state.get(state_key, []) or []
        if _clean_id(value)
    ]
    visible_selected = [value for value in stored if value in available]
    hidden_count = len(stored) - len(visible_selected)
    if visible_selected:
        c1, c2 = st.columns([4, 1])
        message = (
            f"Текущий связанный отбор: {len(visible_selected)} видимых точек. Клик, рамка или лассо на любой панели заменят его; "
            "те же ID подсвечиваются на всех остальных панелях."
        )
        if hidden_count:
            message += f" Ещё {hidden_count} выбранных ID сейчас скрыты фильтрами и не будут изменены действиями ниже."
        c1.info(message)
        if c2.button("Снять выделение", key=f"{key}_clear", width="stretch"):
            st.session_state[state_key] = []
            st.session_state[ignore_key] = True
            st.session_state.pop(f"{key}_plotly", None)
            st.rerun()
    elif stored and hidden_count:
        st.info(
            f"Все {hidden_count} выбранных точек сейчас скрыты фильтрами. Они не участвуют в действиях; "
            "снимите фильтр, чтобы снова увидеть их, или очистите selection."
        )
        if st.button("Очистить скрытый selection", key=f"{key}_clear_hidden", width="stretch"):
            st.session_state[state_key] = []
            st.session_state[ignore_key] = True
            st.session_state.pop(f"{key}_plotly", None)
            st.rerun()
    else:
        st.caption("Кликните точку или выделите точки рамкой/лассо на любой панели — выбор появится на всех панелях.")
    return visible_selected
