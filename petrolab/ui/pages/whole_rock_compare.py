from __future__ import annotations

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

from petrolab.extended_plotting import (
    NORMALIZATION_REFERENCES,
    REE_ORDER,
    SPIDER_ORDER,
    available_elements,
    build_pattern_figure,
    prepare_pattern,
)
from petrolab.io_utils import numeric_candidates
from petrolab.plotting import build_scatter, figure_png_bytes, figure_svg_bytes
from petrolab.rock_comparison import (
    ROCK_SOURCE_COLUMN,
    whole_rock_comparison_dataframe,
    whole_rock_isotope_comparison_dataframe,
)
from petrolab.tectonic_discrimination import TECTONIC_PRESETS, build_tectonic_figure, prepare_tectonic_dataframe
from petrolab.ui.layout import render_badges, render_page_header
from petrolab.ui.project_context import active_project
from petrolab.ui.xy_components import style_dataframe, style_map
from petrolab.visualization_presets import FIGURE_PRESETS


_PLOT_GROUP_COLUMN = "_rock_plot_group"


def _source_filter(dataframe: pd.DataFrame, key: str) -> pd.DataFrame:
    if ROCK_SOURCE_COLUMN not in dataframe.columns:
        return dataframe
    source_values = dataframe[ROCK_SOURCE_COLUMN].fillna("Свои / источник не указан").astype(str)
    sources = sorted(source_values.unique().tolist())
    chosen = st.multiselect(
        "Источники / статьи",
        sources,
        default=sources,
        key=f"{key}_sources",
        help="Отключение источника скрывает его только в текущем представлении и не удаляет данные.",
    )
    return dataframe.loc[source_values.isin(chosen)].copy()


def _series_filter(dataframe: pd.DataFrame, key: str) -> pd.DataFrame:
    filtered = dataframe.copy()
    with st.expander("Серии и образцы", expanded=False):
        for column, label in (("Massif", "Массив / комплекс"), ("Lithology", "Литология")):
            if column not in filtered.columns:
                continue
            values = sorted(
                value for value in filtered[column].fillna("").astype(str).str.strip().unique().tolist()
                if value
            )
            if not values:
                continue
            selected = st.multiselect(label, values, default=values, key=f"{key}_{column.lower()}")
            filtered = filtered[filtered[column].fillna("").astype(str).str.strip().isin(selected)].copy()
        if "Rock" in filtered.columns:
            names = sorted(filtered["Rock"].fillna("").astype(str).unique().tolist())
            hidden = st.multiselect(
                "Скрыть отдельные образцы",
                names,
                default=[],
                key=f"{key}_hidden_rocks",
                help="Образец только скрывается с текущих графиков; данные не удаляются.",
            )
            if hidden:
                filtered = filtered[~filtered["Rock"].astype(str).isin(hidden)].copy()
    return filtered


def _focus_ids(project_id: int, dataframe: pd.DataFrame) -> list[int]:
    context = st.session_state.get("whole_rock_workspace_context")
    context = context if isinstance(context, dict) else {}
    try:
        context_project = int(context.get("project_id"))
    except (TypeError, ValueError):
        return []
    if context_project != int(project_id):
        return []
    raw_ids = context.get("rock_ids", [])
    requested: list[int] = []
    for value in raw_ids if isinstance(raw_ids, (list, tuple, set)) else []:
        try:
            rock_id = int(value)
        except (TypeError, ValueError):
            continue
        if rock_id not in requested:
            requested.append(rock_id)
    available = set(
        pd.to_numeric(dataframe.get("_rock_id", pd.Series(dtype=float)), errors="coerce")
        .dropna().astype(int).tolist()
    )
    missing = [rock_id for rock_id in requested if rock_id not in available]
    if missing:
        st.warning("Фокусная порода больше не входит в текущий проект/выборку: " + ", ".join(map(str, missing)))
    return [rock_id for rock_id in requested if rock_id in available]


def _apply_plot_groups(dataframe: pd.DataFrame, focus_ids: list[int]) -> pd.DataFrame:
    result = dataframe.copy()
    if ROCK_SOURCE_COLUMN in result.columns:
        base = result[ROCK_SOURCE_COLUMN].fillna("Свои / источник не указан").astype(str)
    else:
        base = pd.Series("Породы", index=result.index, dtype=str)
    result[_PLOT_GROUP_COLUMN] = base
    if focus_ids and "_rock_id" in result.columns:
        focus_set = {int(value) for value in focus_ids}
        ids = pd.to_numeric(result["_rock_id"], errors="coerce")
        mask = ids.isin(focus_set)
        if "Rock" in result.columns:
            names = result["Rock"].fillna("").astype(str)
        else:
            names = ids.astype("Int64").astype(str)
        result.loc[mask, _PLOT_GROUP_COLUMN] = "★ " + names.loc[mask]
    return result


def _shared_styles(dataframe: pd.DataFrame, key: str, group_column: str) -> dict:
    if group_column not in dataframe.columns:
        return {}
    groups = sorted(dataframe[group_column].fillna("Без группы").astype(str).unique().tolist())
    if not groups:
        return {}
    with st.expander("Стили серий", expanded=True):
        st.caption(
            "Фокусная порода имеет отдельную plot-group, но её настоящий источник/provenance не меняется. "
            "Для литературных серий можно уменьшить Alpha или показать поле."
        )
        editor = st.data_editor(
            style_dataframe(groups),
            width="stretch",
            hide_index=True,
            column_config={
                "Alpha": st.column_config.NumberColumn("Alpha", min_value=0.05, max_value=1.0, step=0.05),
                "Alpha поля": st.column_config.NumberColumn("Alpha поля", min_value=0.0, max_value=1.0, step=0.05),
                "Показывать": st.column_config.SelectboxColumn("Показывать", options=["Точки", "Поле", "Точки + поле", "Только центр"]),
                "Поле": st.column_config.SelectboxColumn("Поле", options=["Confidence ellipse", "Convex hull", "KDE 90%"]),
            },
            key=f"{key}_styles",
        )
        return style_map(editor)


def _figure_exports(fig, stem: str, key: str) -> None:
    c1, c2 = st.columns(2)
    c1.download_button(
        "SVG", figure_svg_bytes(fig), file_name=f"{stem}.svg", mime="image/svg+xml",
        width="stretch", key=f"{key}_svg",
    )
    c2.download_button(
        "PNG 600 dpi", figure_png_bytes(fig, 600), file_name=f"{stem}.png", mime="image/png",
        width="stretch", key=f"{key}_png",
    )


def _xy_tab(dataframe: pd.DataFrame, group_column: str, key: str) -> None:
    numeric = [column for column in numeric_candidates(dataframe) if not str(column).startswith("_")]
    if len(numeric) < 2:
        st.info("Недостаточно числовых колонок.")
        return
    c1, c2 = st.columns(2)
    x = c1.selectbox("X", numeric, index=numeric.index("SiO2") if "SiO2" in numeric else 0, key=f"{key}_x")
    y_options = [column for column in numeric if column != x]
    y = c2.selectbox("Y", y_options, key=f"{key}_y")
    l1, l2 = st.columns(2)
    x_label = l1.text_input("Подпись X", value=x, key=f"{key}_xlabel")
    y_label = l2.text_input("Подпись Y", value=y, key=f"{key}_ylabel")
    a1, a2, a3 = st.columns(3)
    log_x = a1.checkbox("log X", key=f"{key}_logx")
    log_y = a2.checkbox("log Y", key=f"{key}_logy")
    title = a3.text_input("Заголовок", value=f"{y} vs {x}", key=f"{key}_title")
    styles = _shared_styles(dataframe, key, group_column)
    preset_names = list(FIGURE_PRESETS)
    preset_name = st.selectbox(
        "Журнальный preset", preset_names,
        index=preset_names.index("Lithos") if "Lithos" in preset_names else 0,
        key=f"{key}_preset",
    )
    preset = FIGURE_PRESETS[preset_name]
    figure = build_scatter(
        dataframe, x, y, group_column if group_column in dataframe.columns else None,
        x_label=x_label, y_label=y_label, title=title,
        marker_size=preset.marker_size, log_x=log_x, log_y=log_y,
        style_map=styles, show_grid=preset.grid, monochrome=preset.monochrome,
        figure_size=(preset.width_in, preset.height_in), font_family=preset.font_family,
        font_size=preset.font_size, tick_size=preset.tick_size, spine_width=preset.spine_width,
    )
    st.pyplot(figure, width="stretch")
    _figure_exports(figure, f"whole_rock_{y}_vs_{x}", key)
    plt.close(figure)


def _pattern_tab(dataframe: pd.DataFrame, group_column: str, key: str) -> None:
    mode = st.segmented_control("Тип", ["REE", "Spider"], default="REE", key=f"{key}_mode") or "REE"
    order = REE_ORDER if mode == "REE" else SPIDER_ORDER
    reference_names = list(NORMALIZATION_REFERENCES)
    default_ref = 1 if mode == "REE" and len(reference_names) > 1 else min(2, len(reference_names) - 1)
    ref_name = st.selectbox("Нормировка", reference_names, index=max(0, default_ref), key=f"{key}_ref")
    reference = NORMALIZATION_REFERENCES[ref_name]
    available = available_elements(dataframe, order, require_known_units=reference is not None)
    if len(available) < 2:
        st.info("Недостаточно trace-element данных с известными единицами.")
        return
    elements = st.multiselect("Элементы", list(order), default=available, key=f"{key}_elements")
    pattern = prepare_pattern(dataframe, elements, reference)
    groups = dataframe[group_column] if group_column in dataframe.columns else None
    labels = dataframe["Rock"] if "Rock" in dataframe.columns else None
    figure = build_pattern_figure(
        pattern, labels=labels, group=groups, title=f"Whole-rock {mode}",
        ylabel="Sample / reference" if reference is not None else "Concentration",
        font_family="Arial", font_size=9.0, figure_size=(7.5, 5.5),
    )
    st.pyplot(figure, width="stretch")
    _figure_exports(figure, f"whole_rock_{mode.lower()}", key)
    plt.close(figure)


def _tectonic_tab(dataframe: pd.DataFrame, group_column: str, key: str) -> None:
    labels = {preset_key: preset.title for preset_key, preset in TECTONIC_PRESETS.items()}
    preset_id = st.selectbox("Диаграмма", list(labels), format_func=lambda value: labels[value], key=f"{key}_preset")
    preset = TECTONIC_PRESETS[preset_id]
    st.warning(
        "Tectonic discrimination — интерпретационный инструмент, а не автоматический диагноз. "
        "Этот preset Pearce et al. (1984) разработан для гранитоидов; применяйте его только к подходящим породам и вместе с геологическими ограничениями."
    )
    st.caption(f"{preset.source} · DOI {preset.doi}. {preset.note}")
    try:
        prepared = prepare_tectonic_dataframe(dataframe, preset_id)
    except ValueError as exc:
        st.info(str(exc))
        return
    if prepared.empty:
        st.info("После проверки положительных Y/Nb/Rb значений точек не осталось.")
        return
    if group_column in dataframe.columns and group_column not in prepared.columns:
        prepared[group_column] = dataframe.loc[prepared.index, group_column]
    styles = _shared_styles(prepared, key, group_column)
    figure = build_tectonic_figure(
        prepared, preset_id,
        group_column=group_column if group_column in prepared.columns else None,
        style_map=styles, marker_size=54, font_family="Arial", font_size=9.0,
        tick_size=8.0, figure_size=(7.2, 5.4),
    )
    st.pyplot(figure, width="stretch")
    _figure_exports(figure, preset_id, key)
    plt.close(figure)


def _isotope_tab(project_id: int, focus_ids: list[int], key: str) -> None:
    dataframe = whole_rock_isotope_comparison_dataframe(project_id)
    if dataframe.empty:
        st.info("Нет изотопных данных.")
        return
    dataframe = _source_filter(dataframe, f"{key}_source")
    dataframe = _apply_plot_groups(dataframe, focus_ids)
    group_column = _PLOT_GROUP_COLUMN
    numeric = [column for column in numeric_candidates(dataframe) if not str(column).startswith("_")]
    if len(numeric) < 2:
        st.info("Для изотопной XY-диаграммы нужны минимум две числовые величины.")
        return
    c1, c2 = st.columns(2)
    x = c1.selectbox("X", numeric, key=f"{key}_x")
    y = c2.selectbox("Y", [column for column in numeric if column != x], key=f"{key}_y")
    styles = _shared_styles(dataframe, key, group_column)
    figure = build_scatter(
        dataframe, x, y, group_column,
        x_label=x, y_label=y, title=f"{y} vs {x}", style_map=styles,
        figure_size=(7.2, 5.2), font_family="Arial", font_size=9.0, tick_size=8.0,
    )
    st.pyplot(figure, width="stretch")
    _figure_exports(figure, f"isotope_{y}_vs_{x}", key)
    plt.close(figure)


def render_whole_rock_compare_page() -> None:
    project = active_project()
    render_page_header(
        "Сравнить породы и литературу",
        "Whole-rock данные работают как исследовательская выборка: источники можно включать и выключать, "
        "фокусную породу держать отдельной серией, а отдельные образцы скрывать без удаления.",
        eyebrow="Породы",
        context=str(project["name"]) if project else "Проект не выбран",
    )
    if project is None:
        st.info("Сначала выберите проект.")
        return
    project_id = int(project["id"])
    key = f"rock_compare_{project_id}"
    dataframe = whole_rock_comparison_dataframe(project_id)
    if dataframe.empty:
        st.info("В проекте пока нет валовых составов пород.")
        return

    focus_ids = _focus_ids(project_id, dataframe)
    if focus_ids:
        if "Rock" in dataframe.columns:
            focus_names = dataframe.loc[
                pd.to_numeric(dataframe["_rock_id"], errors="coerce").isin(focus_ids), "Rock"
            ].astype(str).tolist()
        else:
            focus_names = list(map(str, focus_ids))
        c1, c2 = st.columns([4, 1])
        c1.success("Фокус: " + ", ".join(focus_names) + ". Остальные породы остаются сравнительным фоном.")
        if c2.button("Снять фокус", key=f"{key}_clear_focus", width="stretch"):
            st.session_state.pop("whole_rock_workspace_context", None)
            st.session_state.pop("whole_rock_workspace_rock_ids", None)
            st.rerun()

    dataframe = _source_filter(dataframe, f"{key}_source")
    dataframe = _series_filter(dataframe, key)
    if dataframe.empty:
        st.info("После фильтров не осталось пород.")
        return
    visible_focus_ids = []
    if focus_ids and "_rock_id" in dataframe.columns:
        visible_ids = set(pd.to_numeric(dataframe["_rock_id"], errors="coerce").dropna().astype(int).tolist())
        visible_focus_ids = [rock_id for rock_id in focus_ids if rock_id in visible_ids]
    if focus_ids and not visible_focus_ids:
        st.warning("Фокусная порода скрыта текущими source/series фильтрами.")
    dataframe = _apply_plot_groups(dataframe, visible_focus_ids)
    group_column = _PLOT_GROUP_COLUMN

    sources = dataframe[ROCK_SOURCE_COLUMN].nunique(dropna=True) if ROCK_SOURCE_COLUMN in dataframe.columns else 1
    render_badges([
        (f"пород · {len(dataframe)}", "accent"),
        (f"источников · {sources}", "neutral"),
        (f"фокус · {len(visible_focus_ids)}", "success" if visible_focus_ids else "neutral"),
    ])
    tabs = st.tabs(["XY / Harker", "REE / Spider", "Тектонические", "Изотопы"])
    with tabs[0]:
        _xy_tab(dataframe, group_column, f"{key}_xy")
    with tabs[1]:
        _pattern_tab(dataframe, group_column, f"{key}_pattern")
    with tabs[2]:
        _tectonic_tab(dataframe, group_column, f"{key}_tectonic")
    with tabs[3]:
        _isotope_tab(project_id, focus_ids, f"{key}_isotope")
