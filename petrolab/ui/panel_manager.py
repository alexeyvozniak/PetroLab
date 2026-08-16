from __future__ import annotations

import hashlib

import pandas as pd
import streamlit as st

from petrolab.ui.plot_spec import PlotSpec


def _context_token(numeric: list[str], panel_count: int) -> str:
    return hashlib.sha1("\x1f".join([*numeric, str(panel_count)]).encode("utf-8")).hexdigest()[:10]


def _inbox_token(inbox: PlotSpec | None) -> str:
    if inbox is None:
        return ""
    parts = [
        *[str(value) for value in inbox.dataset_ids],
        *inbox.analysis_ids,
        inbox.x,
        inbox.y,
        inbox.group_column,
        inbox.title,
        str(inbox.log_x),
        str(inbox.log_y),
    ]
    return hashlib.sha1("\x1f".join(parts).encode("utf-8")).hexdigest()[:12]


def _default_rows(
    numeric: list[str],
    defaults: list[tuple[str, str]],
    panel_count: int,
    inbox: PlotSpec | None,
) -> pd.DataFrame:
    rows: list[dict] = []
    for index in range(panel_count):
        default_x, default_y = defaults[index % len(defaults)] if defaults else (numeric[0], numeric[1])
        if index == 0 and inbox is not None and inbox.x in numeric and inbox.y in numeric and inbox.x != inbox.y:
            default_x, default_y = inbox.x, inbox.y
        rows.append(
            {
                "Панель": index + 1,
                "X": default_x,
                "Y": default_y,
                "Название": (
                    inbox.title
                    if index == 0 and inbox is not None and inbox.title
                    else f"{default_y} vs {default_x}"
                ),
                "log X": bool(inbox.log_x) if index == 0 and inbox is not None else False,
                "log Y": bool(inbox.log_y) if index == 0 and inbox is not None else False,
                "Порядок": index + 1,
            }
        )
    return pd.DataFrame(rows)


def _saved_source(
    numeric: list[str],
    defaults: list[tuple[str, str]],
    panel_count: int,
    inbox: PlotSpec | None,
    *,
    key_prefix: str,
) -> pd.DataFrame:
    seed_key = f"_{key_prefix}_panel_seed"
    context_key = f"_{key_prefix}_panel_context"
    inbox_key = f"_{key_prefix}_panel_inbox_token"
    widget_key = f"{key_prefix}_panel_manager"
    context = _context_token(numeric, panel_count)
    incoming = _inbox_token(inbox)

    saved = st.session_state.get(seed_key)
    saved_frame = pd.DataFrame(saved) if isinstance(saved, list) and saved else pd.DataFrame()
    saved_valid = (
        len(saved_frame) == panel_count
        and {"X", "Y", "Название", "log X", "log Y", "Порядок"}.issubset(saved_frame.columns)
        and set(saved_frame["X"].astype(str)).issubset(set(numeric))
        and set(saved_frame["Y"].astype(str)).issubset(set(numeric))
    )
    context_changed = st.session_state.get(context_key) != context
    new_inbox = bool(incoming and st.session_state.get(inbox_key) != incoming)

    if context_changed or new_inbox or not saved_valid:
        source = _default_rows(numeric, defaults, panel_count, inbox if new_inbox else None)
        st.session_state[seed_key] = source.to_dict("records")
        st.session_state[context_key] = context
        if incoming:
            st.session_state[inbox_key] = incoming
        st.session_state.pop(widget_key, None)
        return source
    return saved_frame


def render_panel_manager(
    numeric: list[str],
    defaults: list[tuple[str, str]],
    panel_count: int,
    *,
    inbox: PlotSpec | None,
    key_prefix: str,
) -> list[dict]:
    """Render one compact Origin-like layer/panel specification table."""
    if len(numeric) < 2 or panel_count < 1:
        return []

    source = _saved_source(
        numeric,
        defaults,
        panel_count,
        inbox,
        key_prefix=key_prefix,
    )
    widget_key = f"{key_prefix}_panel_manager"
    seed_key = f"_{key_prefix}_panel_seed"
    st.caption(
        "Одна строка = одна панель. Меняйте оси, название, логарифмический масштаб и порядок здесь; "
        "исходные данные и linked Selection остаются общими."
    )
    edited = st.data_editor(
        source,
        width="stretch",
        hide_index=True,
        disabled=["Панель"],
        column_config={
            "Панель": st.column_config.NumberColumn("Панель", width="small"),
            "X": st.column_config.SelectboxColumn("X", options=numeric, required=True),
            "Y": st.column_config.SelectboxColumn("Y", options=numeric, required=True),
            "Название": st.column_config.TextColumn("Название", width="large"),
            "log X": st.column_config.CheckboxColumn("log X", width="small"),
            "log Y": st.column_config.CheckboxColumn("log Y", width="small"),
            "Порядок": st.column_config.NumberColumn(
                "Порядок", min_value=1, max_value=panel_count, step=1, required=True, width="small"
            ),
        },
        key=widget_key,
    )
    st.session_state[seed_key] = edited.to_dict("records")

    problems: list[str] = []
    for index, row in edited.iterrows():
        if str(row.get("X")) == str(row.get("Y")):
            problems.append(f"панель {int(row.get('Панель') or index + 1)}: X и Y совпадают")
    positions = pd.to_numeric(edited["Порядок"], errors="coerce")
    if positions.isna().any() or positions.duplicated().any():
        problems.append("порядок панелей должен состоять из уникальных чисел")
    if problems:
        st.warning("Проверьте менеджер панелей: " + "; ".join(problems) + ".")
        return []

    prepared = edited.assign(_position=positions).sort_values("_position", kind="stable")
    panels: list[dict] = []
    for _, row in prepared.iterrows():
        x = str(row["X"])
        y = str(row["Y"])
        panels.append(
            {
                "x": x,
                "y": y,
                "x_label": x,
                "y_label": y,
                "title": str(row.get("Название") or "").strip(),
                "log_x": bool(row.get("log X")),
                "log_y": bool(row.get("log Y")),
            }
        )
    return panels
