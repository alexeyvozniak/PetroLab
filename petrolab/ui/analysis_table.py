from __future__ import annotations

import pandas as pd
import streamlit as st

from petrolab.analysis_groups import WORK_GROUP_COLUMN
from petrolab.dataframe_utils import apply_quick_filter, display_value, human_point_label
from petrolab.generations import PETROLAB_GENERATION_COLUMN, SOURCE_GENERATION_COLUMN
from petrolab.source_registry import SOURCE_LABEL_COLUMN
from petrolab.ui.selection_components import render_selection_panel
from petrolab.ui.selection_context import clear_selection, read_selection, set_selection


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
_FIELD_MODES = ("Основное", "Химия", "Расчёты", "Все", "Свои")


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


def _field_candidates(dataframe: pd.DataFrame) -> list[str]:
    return [column for column in dataframe.columns if not str(column).startswith("_")]


def _field_control(dataframe: pd.DataFrame, *, key_prefix: str) -> list[str]:
    mode_key = f"{key_prefix}_column_mode"
    current_mode = str(st.session_state.get(mode_key, "Основное"))
    if current_mode not in _FIELD_MODES:
        current_mode = "Основное"
    with st.popover("Поля", width="stretch"):
        mode = st.radio(
            "Набор полей",
            _FIELD_MODES,
            index=_FIELD_MODES.index(current_mode),
            key=mode_key,
            horizontal=False,
        )
        if mode == "Свои":
            available = _field_candidates(dataframe)
            defaults = [column for column in _columns_for_mode(dataframe, "Основное") if column in available]
            chosen = st.multiselect(
                "Показывать поля",
                available,
                default=defaults,
                key=f"{key_prefix}_custom_fields",
                placeholder="Выберите поля",
            )
            identity = [column for column in _IDENTITY_COLUMNS if column in dataframe.columns]
            return list(dict.fromkeys([*identity, *chosen]))
    return _columns_for_mode(dataframe, str(mode))


def _filter_candidates(dataframe: pd.DataFrame) -> list[str]:
    curated = [column for column in _IDENTITY_COLUMNS if column in dataframe.columns]
    others = [
        column for column in dataframe.columns
        if not str(column).startswith("_")
        and column not in curated
        and (
            pd.api.types.is_numeric_dtype(dataframe[column])
            or dataframe[column].nunique(dropna=True) <= 120
        )
    ]
    return list(dict.fromkeys([*curated, *others]))


def _filter_control(dataframe: pd.DataFrame, *, key_prefix: str) -> pd.DataFrame:
    candidates = _filter_candidates(dataframe)
    if not candidates:
        return dataframe
    filter_key = f"{key_prefix}_filter_column"
    current = str(st.session_state.get(filter_key, "Без фильтра"))
    options = ["Без фильтра", *candidates]
    if current not in options:
        current = "Без фильтра"
    with st.popover("Фильтр", width="stretch"):
        column = st.selectbox(
            "Поле",
            options,
            index=options.index(current),
            key=filter_key,
        )
        if column == "Без фильтра" or column not in dataframe.columns:
            st.caption("Фильтр меняет только текущий вид. Selection, Hide и Exclude остаются прежними.")
            return dataframe

        series = dataframe[column]
        if pd.api.types.is_numeric_dtype(series):
            numeric = pd.to_numeric(series, errors="coerce").dropna()
            if numeric.empty:
                return dataframe
            lower = float(numeric.min())
            upper = float(numeric.max())
            c1, c2 = st.columns(2)
            minimum = c1.number_input(
                "От",
                value=lower,
                key=f"{key_prefix}_filter_min_{column}",
            )
            maximum = c2.number_input(
                "До",
                value=upper,
                key=f"{key_prefix}_filter_max_{column}",
            )
            if float(minimum) > float(maximum):
                st.warning("Нижняя граница больше верхней.")
                return dataframe.iloc[0:0].copy()
            values = pd.to_numeric(dataframe[column], errors="coerce")
            return dataframe.loc[values.between(float(minimum), float(maximum), inclusive="both")].copy()

        values = sorted(
            {str(value) for value in series.dropna().tolist() if str(value).strip()},
            key=str.casefold,
        )
        chosen = st.multiselect(
            "Оставить значения",
            values,
            key=f"{key_prefix}_filter_values_{column}",
            placeholder="Все значения",
        )
        if not chosen:
            return dataframe
        return dataframe.loc[dataframe[column].astype(str).isin(chosen)].copy()


def _group_control(dataframe: pd.DataFrame, *, key_prefix: str) -> tuple[pd.DataFrame, str | None]:
    candidates = [
        column for column in _GROUPING_COLUMNS
        if column in dataframe.columns and dataframe[column].nunique(dropna=True) > 1
    ]
    advanced = [
        column for column in dataframe.columns
        if not str(column).startswith("_")
        and column not in candidates
        and 1 < dataframe[column].nunique(dropna=True) <= 100
    ]
    options = ["Не группировать", *candidates]
    if advanced:
        options.append("Другой столбец…")
    group_key = f"{key_prefix}_group_col"
    current = str(st.session_state.get(group_key, "Не группировать"))
    if current not in options:
        current = "Не группировать"
    with st.popover("Группа", width="stretch"):
        group_col = st.selectbox(
            "Группировать по",
            options,
            index=options.index(current),
            key=group_key,
        )
        if group_col == "Другой столбец…":
            group_col = st.selectbox(
                "Другой столбец",
                advanced,
                key=f"{key_prefix}_advanced_group_col",
            ) if advanced else "Не группировать"
        if group_col == "Не группировать" or group_col not in dataframe.columns:
            st.caption("Группировка меняет порядок текущего вида, но не создаёт Work Group или Generation.")
            return dataframe, None
        st.caption("Строки одной группы будут стоять рядом; сама колонка группы остаётся видимой в таблице.")

    helper = dataframe[group_col].astype("string").fillna("")
    grouped = dataframe.assign(_petrolab_group_sort=helper)
    grouped = grouped.sort_values("_petrolab_group_sort", kind="stable").drop(columns=["_petrolab_group_sort"])
    return grouped, str(group_col)


def _sort_control(
    dataframe: pd.DataFrame,
    *,
    key_prefix: str,
    group_col: str | None,
) -> tuple[pd.DataFrame, str | None]:
    candidates = [column for column in dataframe.columns if not str(column).startswith("_")]
    if not candidates:
        return dataframe, None
    sort_key = f"{key_prefix}_sort_column"
    current = str(st.session_state.get(sort_key, "Без сортировки"))
    options = ["Без сортировки", *candidates]
    if current not in options:
        current = "Без сортировки"
    with st.popover("Сортировка", width="stretch"):
        column = st.selectbox(
            "Сортировать по",
            options,
            index=options.index(current),
            key=sort_key,
        )
        direction = st.radio(
            "Направление",
            ["По возрастанию", "По убыванию"],
            horizontal=True,
            key=f"{key_prefix}_sort_direction",
        )
        if column == "Без сортировки" or column not in dataframe.columns:
            st.caption("Сортировка меняет только порядок строк текущего вида.")
            return dataframe, None

    ascending = direction == "По возрастанию"
    if group_col and group_col in dataframe.columns and group_col != column:
        group_helper = dataframe[group_col].astype("string").fillna("")
        sort_helper = dataframe[column] if pd.api.types.is_numeric_dtype(dataframe[column]) else dataframe[column].astype("string").fillna("")
        result = dataframe.assign(_petrolab_group_sort=group_helper, _petrolab_sort=sort_helper).sort_values(
            by=["_petrolab_group_sort", "_petrolab_sort"],
            ascending=[True, ascending],
            na_position="last",
            kind="stable",
        ).drop(columns=["_petrolab_group_sort", "_petrolab_sort"])
    elif pd.api.types.is_numeric_dtype(dataframe[column]):
        result = dataframe.sort_values(column, ascending=ascending, na_position="last", kind="stable")
    else:
        helper = dataframe[column].astype("string").fillna("")
        result = dataframe.assign(_petrolab_sort=helper).sort_values(
            by="_petrolab_sort",
            ascending=ascending,
            na_position="last",
            kind="stable",
        ).drop(columns=["_petrolab_sort"])
    return result, str(column)


def _render_expanded_record(dataframe: pd.DataFrame) -> None:
    context = read_selection()
    if context.count != 1 or dataframe.empty or "_analysis_id" not in dataframe.columns:
        return
    analysis_id = str(context.analysis_ids[0])
    match = dataframe.loc[dataframe["_analysis_id"].astype(str).eq(analysis_id)]
    if match.empty:
        return
    row = match.iloc[0]
    label = human_point_label(row)
    with st.expander(f"Карточка точки · {label}", expanded=False):
        st.caption("Развёрнутая запись без перехода на другую страницу. Внутренние ID остаются скрытыми.")
        columns = [column for column in dataframe.columns if not str(column).startswith("_")]
        details = pd.DataFrame(
            {
                "Поле": columns,
                "Значение": [display_value(row.get(column)) for column in columns],
            }
        )
        st.dataframe(details, width="stretch", hide_index=True, height=360)


def _render_view_selection_actions(working: pd.DataFrame, *, key_prefix: str) -> None:
    visible_ids = working["_analysis_id"].astype(str).tolist()
    current = set(read_selection().analysis_ids)
    c1, c2, c3, c4, note = st.columns([1.2, 1, 1.05, .8, 2.6], gap="small")
    if c1.button(
        f"Применить · {sum(value in current for value in visible_ids)}",
        type="primary",
        width="stretch",
        key=f"{key_prefix}_apply_selection",
        help="Применить чекбоксы таблицы как новый общий Selection.",
    ):
        return
    if c2.button("Все видимые", width="stretch", key=f"{key_prefix}_select_visible"):
        set_selection(visible_ids, origin="Таблица · видимые", mode="replace", label="Видимые строки")
        st.rerun()
    if c3.button("Инвертировать", width="stretch", key=f"{key_prefix}_invert_visible"):
        inverted = [analysis_id for analysis_id in visible_ids if analysis_id not in current]
        set_selection(inverted, origin="Таблица · инверсия", mode="replace", label="Инверсия видимых")
        st.rerun()
    if c4.button("Очистить", width="stretch", key=f"{key_prefix}_clear_visible_selection"):
        clear_selection()
        st.rerun()
    note.caption("Операции относятся к текущему виду; фильтр и сортировка сами по себе Selection не меняют.")


def render_analysis_table(
    dataframe: pd.DataFrame,
    *,
    project_id: int | None,
    key_prefix: str,
    height: int = 560,
) -> pd.DataFrame:
    """Render the canonical Airtable/JMP-inspired analysis workspace."""
    if dataframe.empty or "_analysis_id" not in dataframe.columns:
        st.info("В текущем контексте нет аналитических строк.")
        return dataframe.iloc[0:0].copy()

    toolbar = st.columns([4.0, 1.2, 1.2, 1.2, 1.2], gap="small")
    with toolbar[0]:
        query = st.text_input(
            "Поиск в анализах",
            key=f"{key_prefix}_query",
            placeholder="🔎 Sample, Grain, Point, Generation, элемент…",
            label_visibility="collapsed",
        )
    with toolbar[1]:
        visible_columns = _field_control(dataframe, key_prefix=key_prefix)
    with toolbar[2]:
        filtered = _filter_control(dataframe, key_prefix=key_prefix)
    with toolbar[3]:
        grouped, group_col = _group_control(filtered, key_prefix=key_prefix)
    with toolbar[4]:
        ordered, sort_col = _sort_control(grouped, key_prefix=key_prefix, group_col=group_col)

    working = apply_quick_filter(ordered, str(query or ""))
    if working.empty:
        st.info("По текущему поиску/фильтру ничего не найдено.")
        return working

    current = set(read_selection().analysis_ids)
    editor = working.copy()
    editor.insert(0, "Выбрать", editor["_analysis_id"].astype(str).isin(current))
    editor.insert(1, "Точка", [human_point_label(row) for _, row in editor.iterrows()])
    if group_col and group_col in editor.columns:
        visible_columns = [group_col, *[column for column in visible_columns if column != group_col]]
    visible = ["Выбрать", "Точка", *visible_columns]
    visible = list(dict.fromkeys(column for column in visible if column in editor.columns))

    active_view = []
    filter_name = str(st.session_state.get(f"{key_prefix}_filter_column", "Без фильтра"))
    if filter_name != "Без фильтра":
        active_view.append(f"фильтр: {filter_name}")
    if group_col:
        active_view.append(f"группа: {group_col}")
    if sort_col:
        active_view.append(f"сортировка: {sort_col}")
    if query:
        active_view.append("поиск")
    st.caption(
        f"{len(working):,} строк".replace(",", " ")
        + (" · " + " · ".join(active_view) if active_view else "")
        + " · настройки меняют только вид"
    )

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
    c1, c2, c3, c4, note = st.columns([1.2, 1, 1.05, .8, 2.6], gap="small")
    if c1.button(
        f"Применить · {len(checked_ids)}",
        type="primary",
        width="stretch",
        key=f"{key_prefix}_apply_selection",
    ):
        set_selection(checked_ids, origin="Таблица", mode="replace")
        st.rerun()
    visible_ids = working["_analysis_id"].astype(str).tolist()
    if c2.button("Все видимые", width="stretch", key=f"{key_prefix}_select_visible"):
        set_selection(visible_ids, origin="Таблица · видимые", mode="replace", label="Видимые строки")
        st.rerun()
    if c3.button("Инвертировать", width="stretch", key=f"{key_prefix}_invert_visible"):
        inverted = [analysis_id for analysis_id in visible_ids if analysis_id not in current]
        set_selection(inverted, origin="Таблица · инверсия", mode="replace", label="Инверсия видимых")
        st.rerun()
    if c4.button("Очистить", width="stretch", key=f"{key_prefix}_clear_visible_selection"):
        clear_selection()
        st.rerun()
    note.caption(
        "Чекбоксы, «все видимые» и инверсия меняют общий Selection. "
        "Фильтр, группировка, сортировка и скрытие полей — только текущий вид."
    )

    _render_expanded_record(dataframe)
    render_selection_panel(dataframe, project_id=project_id, key_prefix=f"{key_prefix}_selection")
    return working
