from __future__ import annotations

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

from petrolab.analysis_groups import WORK_GROUP_COLUMN
from petrolab.extended_plotting import (
    NORMALIZATION_REFERENCES,
    REE_ORDER,
    SPIDER_ORDER,
    available_elements,
    build_boxplot_figure,
    build_histogram_figure,
    build_pattern_figure,
    figure_bytes,
    prepare_pattern,
)
from petrolab.interactive_plotting import build_interactive_scatter, selected_analysis_ids
from petrolab.io_utils import numeric_candidates
from petrolab.scientific_overlays import XY_OVERLAYS
from petrolab.scientific_plotting import build_scientific_xy_figure
from petrolab.ui.components import collect_related_images, render_asset_gallery
from petrolab.ui.data_scope import render_analysis_scope
from petrolab.ui.plot_style_controls import render_custom_fields, render_figure_style_controls
from petrolab.visualization_presets import POINT_STYLE_PRESETS, SCIENTIFIC_PLOT_PRESETS


def _categorical_candidates(dataframe: pd.DataFrame) -> list[str]:
    preferred = [WORK_GROUP_COLUMN, "Generation", "Group", "Type", "Sample", "Набор", "Минерал", "Проект"]
    result = [column for column in preferred if column in dataframe.columns]
    for column in dataframe.columns:
        if str(column).startswith("_") or column in result:
            continue
        count = dataframe[column].nunique(dropna=True)
        if 1 < count <= 40:
            result.append(str(column))
    return result


def _style_map(group_values: list[str], preset_name: str) -> dict[str, dict]:
    preset = POINT_STYLE_PRESETS[preset_name]
    return {
        str(group): {
            "marker": preset.markers[index % len(preset.markers)],
            "alpha": preset.alpha,
            "size_multiplier": preset.size_multiplier,
            "filled": preset.filled,
        }
        for index, group in enumerate(group_values)
    }


def _selected_point_details(dataframe: pd.DataFrame, selected_ids: list[str], key_prefix: str) -> None:
    if not selected_ids or "_analysis_id" not in dataframe.columns:
        return
    selected = dataframe[dataframe["_analysis_id"].astype(str).isin(selected_ids)].copy()
    st.caption(f"Выбрано интерактивно: {len(selected)}")
    preview = [column for column in ["Sample", "Grain", "Point", "Generation", "Набор", "Минерал"] if column in selected.columns]
    st.dataframe(selected[preview].head(200), width="stretch", hide_index=True, height=220)
    if len(selected) == 1:
        row = selected.iloc[0]
        assets = collect_related_images(row)
        if assets:
            render_asset_gallery(assets, key_prefix=f"{key_prefix}_assets")


def _render_scientific_xy(dataframe: pd.DataFrame) -> None:
    numeric = numeric_candidates(dataframe)
    applicable = {
        key: preset for key, preset in SCIENTIFIC_PLOT_PRESETS.items()
        if preset.plot_type == "xy"
    }
    if not applicable:
        st.info("Научных XY preset'ов пока нет.")
        return

    preset_id = st.selectbox(
        "Научный шаблон",
        list(applicable),
        format_func=lambda key: applicable[key].title,
        key="science_xy_preset",
    )
    preset = applicable[preset_id]
    st.caption(f"Источник: {preset.source}" + (f" · DOI {preset.doi}" if preset.doi else ""))
    if preset.note:
        st.info(preset.note)

    c1, c2 = st.columns(2)
    x_default = preset.x if preset.x in numeric else (numeric[0] if numeric else "")
    y_default = preset.y if preset.y in numeric else (numeric[min(1, len(numeric) - 1)] if numeric else "")
    if not numeric:
        st.warning("Нет числовых колонок.")
        return
    x = c1.selectbox("Ось X", numeric, index=numeric.index(x_default), key="science_xy_x")
    y = c2.selectbox("Ось Y", numeric, index=numeric.index(y_default), key="science_xy_y")
    l1, l2 = st.columns(2)
    x_label = l1.text_input("Подпись X", value=preset.x_label or x, key="science_xy_xlabel")
    y_label = l2.text_input("Подпись Y", value=preset.y_label or y, key="science_xy_ylabel")
    title = st.text_input("Название рисунка", value=preset.title, key="science_xy_title")

    categories = _categorical_candidates(dataframe)
    group_column = st.selectbox("Группировать точки", ["Без группировки"] + categories, key="science_xy_group")
    group_column = None if group_column == "Без группировки" else group_column

    style = render_figure_style_controls(dataframe, key_prefix="science_xy")
    fields = render_custom_fields("science_xy")
    overlay_enabled = False
    if preset.overlay_id and preset.overlay_id in XY_OVERLAYS:
        overlay_enabled = st.checkbox("Показывать литературное поле/линию", value=True, key="science_xy_overlay")
        overlay = XY_OVERLAYS[preset.overlay_id]
        st.caption(f"Overlay: {overlay.title} · {overlay.source}")
        if overlay.note:
            st.warning(overlay.note)

    st.subheader("Интерактивный просмотр")
    group_values = (
        dataframe[group_column].fillna("Без группы").astype(str).unique().tolist()
        if group_column else ["Все точки"]
    )
    figure = build_interactive_scatter(
        dataframe,
        x,
        y,
        group_col=group_column,
        x_label=x_label,
        y_label=y_label,
        title=title,
        style_map=_style_map(group_values, style.point_style_name),
    )
    event = st.plotly_chart(
        figure,
        width="stretch",
        on_select="rerun",
        selection_mode=("points", "box", "lasso"),
        key="science_xy_interactive",
    )
    _selected_point_details(dataframe, selected_analysis_ids(event), "science_xy")

    st.subheader("Публикационный вариант")
    publication = build_scientific_xy_figure(
        dataframe,
        x=x,
        y=y,
        x_label=x_label,
        y_label=y_label,
        title=title,
        group_column=group_column,
        point_style_name=style.point_style_name,
        font_family=style.font_family,
        font_size=style.font_size,
        tick_size=style.tick_size,
        label_size=style.label_size,
        marker_size=style.marker_size,
        line_width=style.line_width,
        spine_width=style.spine_width,
        figure_size=(style.width_in, style.height_in),
        grid=style.grid,
        monochrome=style.monochrome,
        show_legend=style.show_legend,
        point_label_column=style.point_label_column if style.label_points else None,
        overlay_id=preset.overlay_id if overlay_enabled else None,
        custom_fields=fields,
    )
    st.pyplot(publication, width="stretch")
    b1, b2 = st.columns(2)
    b1.download_button(
        "PNG",
        figure_bytes(publication, "png", style.dpi),
        file_name=f"{preset_id}.png",
        mime="image/png",
        key="science_xy_png",
    )
    b2.download_button(
        "SVG",
        figure_bytes(publication, "svg", style.dpi),
        file_name=f"{preset_id}.svg",
        mime="image/svg+xml",
        key="science_xy_svg",
    )
    plt.close(publication)


def _render_pattern(dataframe: pd.DataFrame) -> None:
    mode = st.segmented_control("Тип", ["REE", "Spider / multi-element"], default="REE", key="pattern_mode")
    preferred = REE_ORDER if mode == "REE" else SPIDER_ORDER
    available = available_elements(dataframe, preferred)
    if len(available) < 2:
        st.info("Недостаточно элементов с числовыми концентрациями для выбранной диаграммы.")
        return
    selected = st.multiselect("Элементы", list(preferred), default=available, key="pattern_elements")
    reference_name = st.selectbox("Нормировка", list(NORMALIZATION_REFERENCES), index=1 if mode == "REE" else 2, key="pattern_ref")
    reference = NORMALIZATION_REFERENCES[reference_name]
    pattern = prepare_pattern(dataframe, selected, reference)
    if pattern.missing_elements:
        st.caption("Нет данных: " + ", ".join(pattern.missing_elements))
    st.caption(f"Вошло кривых: {len(pattern.data)} · исключено пустых строк: {pattern.excluded_rows}")

    categories = _categorical_candidates(dataframe)
    group = st.selectbox("Легенда/группа", ["Каждый анализ"] + categories, key="pattern_group")
    group_series = None if group == "Каждый анализ" else dataframe[group]
    label_candidates = [column for column in ["Sample", "Grain", "Point", "Generation", "Набор"] if column in dataframe.columns]
    label_column = st.selectbox("Подпись отдельной кривой", ["Индекс"] + label_candidates, key="pattern_label")
    labels = None if label_column == "Индекс" else dataframe[label_column]
    style = render_figure_style_controls(dataframe, key_prefix="pattern")
    ylabel = "Concentration" if reference is None else ("Sample / CI chondrite" if mode == "REE" else "Sample / primitive mantle")
    title = st.text_input("Название", value="REE pattern" if mode == "REE" else "Multi-element pattern", key="pattern_title")
    figure = build_pattern_figure(
        pattern,
        labels=labels,
        group=group_series,
        title=title,
        ylabel=ylabel,
        log_y=st.checkbox("Логарифмическая Y", value=True, key="pattern_log"),
        show_legend=style.show_legend,
        linewidth=style.line_width,
        alpha=POINT_STYLE_PRESETS[style.point_style_name].alpha,
        marker=POINT_STYLE_PRESETS[style.point_style_name].markers[0],
        marker_size=max(2.0, style.marker_size / 14.0),
        grid=style.grid,
        font_family=style.font_family,
        font_size=style.font_size,
        figure_size=(style.width_in, style.height_in),
    )
    st.pyplot(figure, width="stretch")
    c1, c2 = st.columns(2)
    c1.download_button("PNG", figure_bytes(figure, "png", style.dpi), file_name="pattern.png", mime="image/png", key="pattern_png")
    c2.download_button("SVG", figure_bytes(figure, "svg", style.dpi), file_name="pattern.svg", mime="image/svg+xml", key="pattern_svg")
    plt.close(figure)


def _render_histogram(dataframe: pd.DataFrame) -> None:
    numeric = numeric_candidates(dataframe)
    if not numeric:
        st.info("Нет числовых колонок.")
        return
    column = st.selectbox("Параметр", numeric, key="hist_column")
    categories = _categorical_candidates(dataframe)
    group = st.selectbox("Разделить по группам", ["Нет"] + categories, key="hist_group")
    group = None if group == "Нет" else group
    bins = st.slider("Число интервалов", 5, 100, 20, key="hist_bins")
    density = st.checkbox("Плотность вместо количества", value=False, key="hist_density")
    style = render_figure_style_controls(dataframe, key_prefix="hist")
    fig = build_histogram_figure(
        dataframe,
        column,
        bins=bins,
        group_column=group,
        density=density,
        grid=style.grid,
        font_family=style.font_family,
        font_size=style.font_size,
        figure_size=(style.width_in, style.height_in),
    )
    st.pyplot(fig, width="stretch")
    st.download_button("Скачать PNG", figure_bytes(fig, "png", style.dpi), file_name="histogram.png", mime="image/png", key="hist_png")
    plt.close(fig)


def _render_boxplot(dataframe: pd.DataFrame) -> None:
    numeric = numeric_candidates(dataframe)
    if not numeric:
        st.info("Нет числовых колонок.")
        return
    columns = st.multiselect("Числовые параметры", numeric, default=numeric[:1], key="box_columns")
    categories = _categorical_candidates(dataframe)
    group = st.selectbox("Группировка", ["Нет"] + categories, key="box_group")
    group = None if group == "Нет" else group
    if group and len(columns) > 1:
        st.caption("При группировке boxplot использует один числовой параметр; оставьте одну колонку.")
    style = render_figure_style_controls(dataframe, key_prefix="box")
    if not columns:
        return
    fig = build_boxplot_figure(
        dataframe,
        columns,
        group_column=group,
        show_fliers=st.checkbox("Показывать выбросы", value=True, key="box_fliers"),
        grid=style.grid,
        font_family=style.font_family,
        font_size=style.font_size,
        figure_size=(style.width_in, style.height_in),
    )
    st.pyplot(fig, width="stretch")
    st.download_button("Скачать PNG", figure_bytes(fig, "png", style.dpi), file_name="boxplot.png", mime="image/png", key="box_png")
    plt.close(fig)


def render_science_plots_page() -> None:
    st.title("Научные диаграммы")
    st.write(
        "Готовые схемы для минералов кимберлитов, лампрофиров и щелочно-ультраосновных пород, "
        "а также REE/spider, гистограммы и boxplot. Литературные поля рисуются только там, "
        "где в коде есть проверяемая геометрия и источник."
    )
    scope = render_analysis_scope("science_plots")
    if scope is None:
        return
    tab_xy, tab_pattern, tab_hist, tab_box = st.tabs(["Классификационные и рабочие XY", "REE / Spider", "Гистограмма", "Boxplot"])
    with tab_xy:
        _render_scientific_xy(scope.dataframe)
    with tab_pattern:
        _render_pattern(scope.dataframe)
    with tab_hist:
        _render_histogram(scope.dataframe)
    with tab_box:
        _render_boxplot(scope.dataframe)
