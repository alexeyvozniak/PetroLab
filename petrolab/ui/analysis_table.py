from __future__ import annotations

import pandas as pd
import streamlit as st

from petrolab.analysis_groups import WORK_GROUP_COLUMN
from petrolab.dataframe_utils import apply_quick_filter, human_point_label
from petrolab.generations import PETROLAB_GENERATION_COLUMN, SOURCE_GENERATION_COLUMN
from petrolab.source_registry import SOURCE_LABEL_COLUMN
from petrolab.ui.selection_components import render_selection_panel
from petrolab.ui.selection_context import read_selection, set_selection


_IDENTITY_COLUMNS = (
    "Sample", "Grain", "Point", PETROLAB_GENERATION_COLUMN, SOURCE_GENERATION_COLUMN,
    "Generation", WORK_GROUP_COLUMN, "Textural zone", "Минерал", "Mineral", SOURCE_LABEL_COLUMN,
    "Набор", "Источник", "Method", "Метод", "QC уровень", "QC решение",
)
_CHEMISTRY_PRIORITY = (
    "SiO2", "TiO2", "Al2O3", "Cr2O3", "FeOt", "FeO", "Fe2O3t", "MnO", "MgO",
    "CaO", "Na2O", "K2O", "P2O5", "F", "Cl", "Mg#", "Ni", "Cr", "Co", "Sc", "V",
    "Rb", "Sr", "Ba", "Nb", "Ta", "Zr", "Hf", "La", "Ce", "Nd", "Sm", "Eu", "Y", "Yb",
)
_GROUPING_COLUMNS = (
    PETROLAB_GENERATION_COLUMN, SOURCE_GENERATION_COLUMN, "Generation", WORK_GROUP_COLUMN,
    "Sample", "Grain", "Textural zone", SOURCE_LABEL_COLUMN, "Источник", "Набор", "Минерал", "Mineral",
)


def _chemical_columns(dataframe: pd.DataFrame) -> list[str]:
    preferred = [column for column in _CHEMISTRY_PRIORITY if column in dataframe.columns]
    numeric = [
        column for column in dataframe.columns
        if column not in preferred
        and not str(column).startswith("_")
        and pd.api.types.is_numeric_dtype(dataframe[column])
    ]
    return [*preferred, *numeric]


def _calculated_columns(dataframe: pd.DataFrame) -> list[str]:
    tokens = ("apfu", "mg#", "fe#", "cation", "site", "formula", "calc", "ratio", "/")
    return [
        column for column in dataframe.columns
        if not str(column).startswith("_")
        and any(token in str(column).casefold() for token in tokens)
    ]


def _columns_for_mode(dataframe: pd.DataFrame, mode: str) -> list[str]:
    identity = [column for column in _IDENTITY_COLUMNS if column in dataframe.columns]
    if mode == "Химия":
        body = _chemical_columns(dataframe)[:28]
    elif mode == "Расчёты":
        body = _calculated_columns(dataframe)
    elif mode == "Все":
        body = [column for column in dataframe.columns if not str(column).startswith("_")]
    else:
        body = _chemical_columns(dataframe)[:8]
    return list(dict.fromkeys([*identity, *body]))


def _apply_group_filter(dataframe: pd.DataFrame, *, key_prefix: str) -> pd.DataFrame:
    candidates = [
        column for column in _GROUPING_COLUMNS
        if column in dataframe.columns and dataframe[column].nunique(dropna=True) > 1
    ]
    if not candidates:
        return dataframe
    group_col = st.selectbox(
        "Группировать / отфильтровать по",
        ["Не группировать", *candidates, "Другой столбец…"],
        key=f"{key_prefix}_group_col",
    )
    if group_col == "Другой столбец…":
        advanced = [
            column for column in dataframe.columns
            if not str(column).startswith("_") and dataframe[column].nunique(dropna=True) <= 100
        ]
        group_col = st.selectbox("Другой столбец", advanced, key=f"{key_prefix}_advanced_group_col") if advanced else "Не группировать"
    if group_col == "Не группировать" or group_col not in dataframe.columns:
        return dataframe
    values = sorted(dataframe[group_col].dropna().astype(str).unique(), key=str.casefold)
    chosen = st.multiselect(
        f"{group_col}: оставить значения",
        values,
        key=f"{key_prefix}_group_values",
        placeholder="Все значения",
    )
    if not chosen:
        return dataframe
    return dataframe[dataframe[group_col].astype(str).isin(chosen)].copy()


def render_analysis_table(
    dataframe: pd.DataFrame,
    *,
    project_id: int | None,
    key_prefix: str,
    height: int = 560,
) -> pd.DataFrame:
    """Render the canonical row-selection workspace and return the displayed rows."""
    if dataframe.empty or "_analysis_id" not in dataframe.columns:
        st.info("В текущем контексте нет аналитических строк.")
        return dataframe.iloc[0:0].copy()

    top1, top2 = st.columns([2.2, 1.4])
    with top1:
        query = st.text_input(
            "Поиск в анализах",
            key=f"{key_prefix}_query",
            placeholder="Sample, Grain, Point, Generation, элемент…",
            label_visibility="collapsed",
        )
    with top2:
        mode = st.segmented_control(
            "Колонки",
            ["Основное", "Химия", "Расчёты", "Все"],
            default="Основное",
            key=f"{key_prefix}_column_mode",
        ) or "Основное"

    working = apply_quick_filter(dataframe, str(query or ""))
    working = _apply_group_filter(working, key_prefix=key_prefix)
    if working.empty:
        st.info("По текущему поиску/фильтру ничего не найдено.")
        return working

    current = set(read_selection().analysis_ids)
    editor = working.copy()
    editor.insert(0, "Выбрать", editor["_analysis_id"].astype(str).isin(current))
    editor.insert(1, "Точка", [human_point_label(row) for _, row in editor.iterrows()])
    visible = ["Выбрать", "Точка", *_columns_for_mode(editor, str(mode))]
    visible = list(dict.fromkeys(column for column in visible if column in editor.columns))

    edited = st.data_editor(
        editor[visible],
        width="stretch",
        height=height,
        hide_index=True,
        disabled=[column for column in visible if column != "Выбрать"],
        column_config={
            "Выбрать": st.column_config.CheckboxColumn("✓", help="Добавить строку в общий научный отбор", width="small"),
            "Точка": st.column_config.TextColumn("Точка", width="large"),
        },
        key=f"{key_prefix}_editor",
    )

    checked_indices = edited.index[edited["Выбрать"].fillna(False).astype(bool)].tolist()
    checked_ids = working.loc[working.index.isin(checked_indices), "_analysis_id"].astype(str).tolist()
    c1, c2 = st.columns([1, 3])
    if c1.button(
        f"Применить отбор · {len(checked_ids)}",
        type="primary",
        width="stretch",
        key=f"{key_prefix}_apply_selection",
    ):
        set_selection(checked_ids, origin="Таблица", mode="replace")
        st.rerun()
    c2.caption("Чекбоксы задают тот же SelectionContext, который подсвечивается на XY/PCA/multi-panel. Фильтр таблицы сам по себе Selection не меняет.")

    render_selection_panel(dataframe, project_id=project_id, key_prefix=f"{key_prefix}_selection")
    return working
