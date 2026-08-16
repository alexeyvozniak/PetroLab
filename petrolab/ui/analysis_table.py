from __future__ import annotations

import pandas as pd
import streamlit as st

from petrolab.analysis_groups import WORK_GROUP_COLUMN
from petrolab.dataframe_utils import apply_quick_filter, human_point_label
from petrolab.generations import PETROLAB_GENERATION_COLUMN, SOURCE_GENERATION_COLUMN
from petrolab.source_registry import SOURCE_LABEL_COLUMN
from petrolab.table_views import delete_table_view, list_table_views, save_table_view
from petrolab.ui.field_presets import FIELD_MODES, columns_for_mode, normalize_field_mode
from petrolab.ui.record_detail import render_record_detail
from petrolab.ui.selection_components import render_selection_panel
from petrolab.ui.selection_context import clear_selection, read_selection, set_selection
from petrolab.ui.table_filters import FILTER_MODES, apply_categorical_filter, normalize_filter_mode
from petrolab.ui.table_view_state import TableViewState, apply_table_view, capture_table_view, clear_table_view
from petrolab.ui.view_presets import builtin_table_view_presets


_IDENTITY_COLUMNS = (
    "Sample", "Grain", "Point", PETROLAB_GENERATION_COLUMN, SOURCE_GENERATION_COLUMN,
    "Generation", WORK_GROUP_COLUMN, "Textural zone", "Минерал", "Mineral", SOURCE_LABEL_COLUMN,
    "Набор", "Источник", "Method", "Метод", "QC уровень", "QC решение",
)
_GROUPING_COLUMNS = (
    PETROLAB_GENERATION_COLUMN, SOURCE_GENERATION_COLUMN, "Generation", WORK_GROUP_COLUMN,
    "Sample", "Grain", "Textural zone", SOURCE_LABEL_COLUMN, "Источник", "Набор", "Минерал", "Mineral",
)
_FIELD_MODES = FIELD_MODES


def _columns_for_mode(dataframe: pd.DataFrame, mode: str) -> list[str]:
    return columns_for_mode(dataframe, mode, identity_columns=_IDENTITY_COLUMNS)


def _field_candidates(dataframe: pd.DataFrame) -> list[str]:
    return [column for column in dataframe.columns if not str(column).startswith("_")]


def _field_control(dataframe: pd.DataFrame, *, key_prefix: str) -> list[str]:
    mode_key = f"{key_prefix}_column_mode"
    raw_mode = str(st.session_state.get(mode_key, "Основное"))
    current_mode = normalize_field_mode(raw_mode)
    if raw_mode != current_mode:
        st.session_state[mode_key] = current_mode
    with st.popover("Поля", width="stretch"):
        mode = st.radio(
            "Набор полей",
            _FIELD_MODES,
            index=_FIELD_MODES.index(current_mode),
            key=mode_key,
            horizontal=False,
            help="Микрозонд = оксиды/wt.%; Trace = элементы ppm/µg/g; APFU = структурная формула; QC = контроль качества.",
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
        column = st.selectbox("Поле", options, index=options.index(current), key=filter_key)
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
            minimum = c1.number_input("От", value=lower, key=f"{key_prefix}_filter_min_{column}")
            maximum = c2.number_input("До", value=upper, key=f"{key_prefix}_filter_max_{column}")
            if float(minimum) > float(maximum):
                st.warning("Нижняя граница больше верхней.")
                return dataframe.iloc[0:0].copy()
            values = pd.to_numeric(dataframe[column], errors="coerce")
            return dataframe.loc[values.between(float(minimum), float(maximum), inclusive="both")].copy()

        values = sorted(
            {str(value) for value in series.dropna().tolist() if str(value).strip()},
            key=str.casefold,
        )
        mode_key = f"{key_prefix}_filter_mode_{column}"
        current_mode = normalize_filter_mode(st.session_state.get(mode_key, "Оставить"))
        filter_mode = st.segmented_control(
            "Что сделать с выбранными значениями",
            list(FILTER_MODES),
            default=current_mode,
            key=mode_key,
            help="«Оставить» показывает только выбранные значения; «Скрыть» временно убирает их из текущего вида. Данные и Selection не меняются.",
        ) or current_mode
        chosen = st.multiselect(
            "Значения",
            values,
            key=f"{key_prefix}_filter_values_{column}",
            placeholder="Все значения",
        )
        if not chosen:
            return dataframe
        return apply_categorical_filter(dataframe, column, chosen, mode=str(filter_mode))


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
        group_col = st.selectbox("Группировать по", options, index=options.index(current), key=group_key)
        if group_col == "Другой столбец…":
            group_col = (
                st.selectbox("Другой столбец", advanced, key=f"{key_prefix}_advanced_group_col")
                if advanced else "Не группировать"
            )
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
        column = st.selectbox("Сортировать по", options, index=options.index(current), key=sort_key)
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
        sort_helper = (
            dataframe[column]
            if pd.api.types.is_numeric_dtype(dataframe[column])
            else dataframe[column].astype("string").fillna("")
        )
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


def _table_view_scope(dataframe: pd.DataFrame) -> str:
    if "_dataset_id" not in dataframe.columns:
        return "project"
    ids = sorted({str(value) for value in dataframe["_dataset_id"].dropna().tolist()})
    if len(ids) == 1:
        return f"dataset:{ids[0]}"
    return "project"


def _sanitize_saved_view(state: TableViewState, dataframe: pd.DataFrame) -> TableViewState:
    available = {str(column) for column in dataframe.columns if not str(column).startswith("_")}
    state.custom_fields = [column for column in state.custom_fields if column in available]
    if state.filter_column not in available:
        state.filter_column = "Без фильтра"
        state.filter_values = []
        state.filter_min = None
        state.filter_max = None
    state.filter_mode = normalize_filter_mode(state.filter_mode)
    if state.group_column not in {*available, "Не группировать", "Другой столбец…"}:
        state.group_column = "Не группировать"
    if state.advanced_group_column not in available:
        state.advanced_group_column = ""
    if state.sort_column not in available:
        state.sort_column = "Без сортировки"
    state.column_mode = normalize_field_mode(state.column_mode)
    return state


def _view_control(dataframe: pd.DataFrame, *, project_id: int | None, key_prefix: str) -> None:
    active_key = f"{key_prefix}_active_saved_view"
    preset_key = f"{key_prefix}_active_view_preset"
    active_name = str(st.session_state.get(active_key, "") or "")
    active_preset = str(st.session_state.get(preset_key, "") or "")
    current_label = active_name or active_preset
    label = f"Вид · {current_label}" if current_label else "Вид"

    with st.popover(label, width="stretch"):
        st.caption(
            "Вид хранит поля, поиск, фильтр, группировку и сортировку. "
            "Selection, Hide и Exclude не сохраняются."
        )

        presets = builtin_table_view_presets(dataframe)
        if presets:
            st.markdown("**Быстрые виды**")
            for start in range(0, len(presets), 2):
                columns = st.columns(2)
                for slot, preset in zip(columns, presets[start:start + 2]):
                    if slot.button(
                        preset.name,
                        width="stretch",
                        type="primary" if preset.name == active_preset and not active_name else "secondary",
                        key=f"{key_prefix}_preset_{start}_{preset.name}",
                        help=preset.description,
                    ):
                        state = _sanitize_saved_view(
                            TableViewState.from_dict(preset.state.to_dict()),
                            dataframe,
                        )
                        apply_table_view(st.session_state, key_prefix, state)
                        st.session_state[active_key] = ""
                        st.session_state[preset_key] = preset.name
                        st.rerun()

        if project_id is None:
            st.info("Сохранённые виды доступны внутри проекта. Быстрые виды выше работают и без сохранения.")
            if st.button("Сбросить текущий вид", width="stretch", key=f"{key_prefix}_view_reset_no_project"):
                clear_table_view(st.session_state, key_prefix)
                st.session_state[active_key] = ""
                st.session_state[preset_key] = ""
                st.rerun()
            return

        scope_key = _table_view_scope(dataframe)
        views = list_table_views(int(project_id), scope_key)
        by_name = {str(item["name"]): item for item in views}
        if by_name:
            st.markdown("**Сохранённые виды**")
            for name, item in by_name.items():
                c1, c2 = st.columns([4, 1])
                if c1.button(
                    name,
                    width="stretch",
                    type="primary" if name == active_name else "secondary",
                    key=f"{key_prefix}_view_open_{item['id']}",
                ):
                    state = _sanitize_saved_view(TableViewState.from_dict(item.get("config")), dataframe)
                    apply_table_view(st.session_state, key_prefix, state)
                    st.session_state[active_key] = name
                    st.session_state[preset_key] = ""
                    st.rerun()
                if c2.button("×", key=f"{key_prefix}_view_delete_{item['id']}", help=f"Удалить вид «{name}»"):
                    delete_table_view(int(project_id), scope_key, name)
                    if active_name == name:
                        st.session_state[active_key] = ""
                    st.rerun()
        else:
            st.caption("Сохранённых видов для этого рабочего контекста пока нет.")

        st.divider()
        new_name = st.text_input(
            "Название вида",
            key=f"{key_prefix}_view_name",
            placeholder="Например: Для статьи",
        )
        current_state = capture_table_view(st.session_state, key_prefix)
        save_label = (
            "Обновить вид"
            if active_name and (not new_name.strip() or new_name.strip() == active_name)
            else "Сохранить текущий вид"
        )
        if st.button(save_label, type="primary", width="stretch", key=f"{key_prefix}_view_save"):
            target_name = new_name.strip() or active_name
            if not target_name:
                st.warning("Введите название вида.")
            else:
                save_table_view(int(project_id), scope_key, target_name, current_state.to_dict())
                st.session_state[active_key] = target_name
                st.session_state[preset_key] = ""
                st.rerun()

        if st.button("Сбросить настройки вида", width="stretch", key=f"{key_prefix}_view_reset"):
            clear_table_view(st.session_state, key_prefix)
            st.session_state[active_key] = ""
            st.session_state[preset_key] = ""
            st.rerun()


def _render_expanded_record(dataframe: pd.DataFrame, *, project_id: int | None) -> None:
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
        render_record_detail(row, dataframe, project_id=project_id)


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

    toolbar = st.columns([3.8, 1.05, 1.05, 1.05, 1.05, 1.15], gap="small")
    with toolbar[5]:
        _view_control(dataframe, project_id=project_id, key_prefix=key_prefix)
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

    active_view: list[str] = []
    saved_view_name = str(st.session_state.get(f"{key_prefix}_active_saved_view", "") or "")
    preset_name = str(st.session_state.get(f"{key_prefix}_active_view_preset", "") or "")
    view_name = saved_view_name or preset_name
    if view_name:
        active_view.append(f"вид: {view_name}")
    filter_name = str(st.session_state.get(f"{key_prefix}_filter_column", "Без фильтра"))
    if filter_name != "Без фильтра":
        filter_mode = normalize_filter_mode(st.session_state.get(f"{key_prefix}_filter_mode_{filter_name}", "Оставить"))
        active_view.append(f"{'скрыть' if filter_mode == 'Скрыть' else 'фильтр'}: {filter_name}")
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
            "Выбрать": st.column_config.CheckboxColumn(
                "✓",
                help="Добавить строку в общий научный отбор",
                width="small",
            ),
            "Точка": st.column_config.TextColumn("Точка", width="large"),
        },
        key=f"{key_prefix}_editor",
    )

    checked_indices = edited.index[edited["Выбрать"].fillna(False).astype(bool)].tolist()
    checked_ids = working.loc[working.index.isin(checked_indices), "_analysis_id"].astype(str).tolist()
    c1, c2, c3, c4, c5, note = st.columns([1.2, 1, 1, 1.05, .8, 2.3], gap="small")
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
    if c3.button(
        "+ Видимые",
        width="stretch",
        key=f"{key_prefix}_add_visible",
        help="Добавить все строки текущего фильтра к уже существующему Selection.",
    ):
        set_selection(visible_ids, origin="Таблица · добавить видимые", mode="add")
        st.rerun()
    if c4.button("Инвертировать", width="stretch", key=f"{key_prefix}_invert_visible"):
        inverted = [analysis_id for analysis_id in visible_ids if analysis_id not in current]
        set_selection(inverted, origin="Таблица · инверсия", mode="replace", label="Инверсия видимых")
        st.rerun()
    if c5.button("Очистить", width="stretch", key=f"{key_prefix}_clear_visible_selection"):
        clear_selection()
        st.rerun()
    note.caption(
        "«Все видимые» заменяет Selection; «+ Видимые» добавляет текущий фильтр к нему. "
        "Фильтр, скрытие значений, группировка, сортировка и сохранённые виды сами Selection не меняют."
    )

    _render_expanded_record(dataframe, project_id=project_id)
    render_selection_panel(dataframe, project_id=project_id, key_prefix=f"{key_prefix}_selection")
    return working
