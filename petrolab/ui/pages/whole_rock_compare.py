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
from petrolab.ui.layout import render_badges, render_page_header, render_section_header
from petrolab.ui.project_context import active_project
from petrolab.ui.xy_components import style_dataframe, style_map
from petrolab.visualization_presets import FIGURE_PRESETS


def _source_filter(dataframe: pd.DataFrame, key: str) -> pd.DataFrame:
    if ROCK_SOURCE_COLUMN not in dataframe.columns:
        return dataframe
    sources = sorted(dataframe[ROCK_SOURCE_COLUMN].fillna("Свои / источник не указан").astype(str).unique().tolist())
    chosen = st.multiselect(
        "Источники / статьи",
        sources,
        default=sources,
        key=f"{key}_sources",
        help="Отключение источника скрывает его только в текущем представлении и не удаляет данные.",
    )
    return dataframe[dataframe[ROCK_SOURCE_COLUMN].astype(str).isin(chosen)].copy()


def _shared_styles(dataframe: pd.DataFrame, key: str) -> dict:
    if ROCK_SOURCE_COLUMN not in dataframe.columns:
        return {}
    groups = sorted(dataframe[ROCK_SOURCE_COLUMN].fillna("Свои / источник не указан").astype(str).unique().tolist())
    if not groups:
        return {}
    with st.expander("Стили своих и литературных серий", expanded=True):
        st.caption(
            "Для большой литературной выборки уменьшите Alpha или выберите «Поле». Confidence ellipse, convex hull и KDE работают так же, как в минералогических XY-графиках."
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
        "SVG",
        figure_svg_bytes(fig),
        file_name=f"{stem}.svg",
        mime="image/svg+xml",
        width="stretch",
        key=f"{key}_svg",
    )
    c2.download_button(
        "PNG 600 dpi",
        figure_png_bytes(fig, 600),
        file_name=f"{stem}.png",
        mime="image/png",
        width="stretch",
        key=f"{key}_png",
    )


def _xy_tab(dataframe: pd.DataFrame) -> None:
    numeric = numeric_candidates(dataframe)
    if len(numeric) < 2:
        st.info("Недостаточно числовых колонок.")
        return
    c1, c2 = st.columns(2)
    x = c1.selectbox("X", numeric, index=numeric.index("SiO2") if "SiO2" in numeric else 0, key="rock_compare_x")
    y_options = [column for column in numeric if column != x]
    y = c2.selectbox("Y", y_options, key="rock_compare_y")
    l1, l2 = st.columns(2)
    x_label = l1.text_input("Подпись X", value=x, key="rock_compare_xlabel")
    y_label = l2.text_input("Подпись Y", value=y, key="rock_compare_ylabel")
    a1, a2, a3 = st.columns(3)
    log_x = a1.checkbox("log X", key="rock_compare_logx")
    log_y = a2.checkbox("log Y", key="rock_compare_logy")
    title = a3.text_input("Заголовок", value=f"{y} vs {x}", key="rock_compare_title")
    styles = _shared_styles(dataframe, "rock_compare_xy")
    preset_name = st.selectbox("Журнальный preset", list(FIGURE_PRESETS), index=list(FIGURE_PRESETS).index("Lithos"), key="rock_compare_preset")
    preset = FIGURE_PRESETS[preset_name]
    figure = build_scatter(
        dataframe,
        x,
        y,
        ROCK_SOURCE_COLUMN if ROCK_SOURCE_COLUMN in dataframe.columns else None,
        x_label=x_label,
        y_label=y_label,
        title=title,
        marker_size=preset.marker_size,
        log_x=log_x,
        log_y=log_y,
        style_map=styles,
        show_grid=preset.grid,
        monochrome=preset.monochrome,
        figure_size=(preset.width_in, preset.height_in),
        font_family=preset.font_family,
        font_size=preset.font_size,
        tick_size=preset.tick_size,
        spine_width=preset.spine_width,
    )
    st.pyplot(figure, width="stretch")
    _figure_exports(figure, f"whole_rock_{y}_vs_{x}", "rock_compare_xy")
    plt.close(figure)


def _pattern_tab(dataframe: pd.DataFrame) -> None:
    mode = st.segmented_control("Тип", ["REE", "Spider"], default="REE", key="rock_compare_pattern_mode") or "REE"
    order = REE_ORDER if mode == "REE" else SPIDER_ORDER
    reference_names = list(NORMALIZATION_REFERENCES)
    default_ref = 1 if mode == "REE" and len(reference_names) > 1 else min(2, len(reference_names) - 1)
    ref_name = st.selectbox("Нормировка", reference_names, index=max(0, default_ref), key="rock_compare_pattern_ref")
    reference = NORMALIZATION_REFERENCES[ref_name]
    available = available_elements(dataframe, order, require_known_units=reference is not None)
    if len(available) < 2:
        st.info("Недостаточно trace-element данных с известными единицами.")
        return
    elements = st.multiselect("Элементы", list(order), default=available, key="rock_compare_pattern_elements")
    pattern = prepare_pattern(dataframe, elements, reference)
    source_groups = dataframe[ROCK_SOURCE_COLUMN] if ROCK_SOURCE_COLUMN in dataframe.columns else None
    labels = dataframe["Rock"] if "Rock" in dataframe.columns else None
    figure = build_pattern_figure(
        pattern,
        labels=labels,
        group=source_groups,
        title=f"Whole-rock {mode}",
        ylabel="Sample / reference" if reference is not None else "Concentration",
        font_family="Arial",
        font_size=9.0,
        figure_size=(7.5, 5.5),
    )
    st.pyplot(figure, width="stretch")
    _figure_exports(figure, f"whole_rock_{mode.lower()}", "rock_compare_pattern")
    plt.close(figure)


def _tectonic_tab(dataframe: pd.DataFrame) -> None:
    labels = {key: preset.title for key, preset in TECTONIC_PRESETS.items()}
    preset_id = st.selectbox(
        "Диаграмма",
        list(labels),
        format_func=lambda value: labels[value],
        key="rock_compare_tectonic_preset",
    )
    preset = TECTONIC_PRESETS[preset_id]
    st.warning(
        "Tectonic discrimination — интерпретационный инструмент, а не автоматический диагноз. Этот preset Pearce et al. (1984) разработан для гранитоидов; применяйте его только к подходящим породам и вместе с геологическими ограничениями."
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
    styles = _shared_styles(prepared, "rock_compare_tectonic")
    figure = build_tectonic_figure(
        prepared,
        preset_id,
        group_column=ROCK_SOURCE_COLUMN if ROCK_SOURCE_COLUMN in prepared.columns else None,
        style_map=styles,
        marker_size=54,
        font_family="Arial",
        font_size=9.0,
        tick_size=8.0,
        figure_size=(7.2, 5.4),
    )
    st.pyplot(figure, width="stretch")
    _figure_exports(figure, preset_id, "rock_compare_tectonic")
    plt.close(figure)


def _isotope_tab(project_id: int) -> None:
    dataframe = whole_rock_isotope_comparison_dataframe(project_id)
    if dataframe.empty:
        st.info("Нет изотопных данных.")
        return
    dataframe = _source_filter(dataframe, "rock_iso_compare")
    numeric = numeric_candidates(dataframe)
    numeric = [column for column in numeric if not str(column).startswith("_")]
    if len(numeric) < 2:
        st.info("Для изотопной XY-диаграммы нужны минимум две числовые величины.")
        return
    c1, c2 = st.columns(2)
    x = c1.selectbox("X", numeric, key="rock_iso_compare_x")
    y = c2.selectbox("Y", [column for column in numeric if column != x], key="rock_iso_compare_y")
    styles = _shared_styles(dataframe, "rock_iso_compare")
    figure = build_scatter(
        dataframe,
        x,
        y,
        ROCK_SOURCE_COLUMN if ROCK_SOURCE_COLUMN in dataframe.columns else None,
        x_label=x,
        y_label=y,
        title=f"{y} vs {x}",
        style_map=styles,
        figure_size=(7.2, 5.2),
        font_family="Arial",
        font_size=9.0,
        tick_size=8.0,
    )
    st.pyplot(figure, width="stretch")
    _figure_exports(figure, f"isotope_{y}_vs_{x}", "rock_iso_compare")
    plt.close(figure)


def render_whole_rock_compare_page() -> None:
    project = active_project()
    render_page_header(
        "Сравнить породы и литературу",
        "Whole-rock данные работают как исследовательская выборка: источники можно включать и выключать, литературные серии делать полупрозрачными или полями, а фигуры сразу экспортировать для статьи.",
        eyebrow="Породы",
        context=str(project["name"]) if project else "Проект не выбран",
    )
    if project is None:
        st.info("Сначала выберите проект.")
        return
    project_id = int(project["id"])
    dataframe = whole_rock_comparison_dataframe(project_id)
    if dataframe.empty:
        st.info("В проекте пока нет валовых составов пород.")
        return
    dataframe = _source_filter(dataframe, "rock_compare")
    if dataframe.empty:
        st.info("Включите хотя бы один источник.")
        return
    sources = dataframe[ROCK_SOURCE_COLUMN].nunique(dropna=True) if ROCK_SOURCE_COLUMN in dataframe.columns else 1
    render_badges([
        (f"пород · {len(dataframe)}", "accent"),
        (f"источников · {sources}", "neutral"),
    ])
    tabs = st.tabs(["XY / Harker", "REE / Spider", "Тектонические", "Изотопы"])
    with tabs[0]:
        _xy_tab(dataframe)
    with tabs[1]:
        _pattern_tab(dataframe)
    with tabs[2]:
        _tectonic_tab(dataframe)
    with tabs[3]:
        _isotope_tab(project_id)
