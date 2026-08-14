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
from petrolab.settings_service import load_settings
from petrolab.ui.components import collect_related_images, render_asset_gallery
from petrolab.ui.data_scope import render_analysis_scope
from petrolab.ui.layout import render_page_header
from petrolab.ui.plot_style_controls import render_custom_fields, render_figure_style_controls
from petrolab.visualization_presets import POINT_STYLE_PRESETS, SCIENTIFIC_PLOT_PRESETS


MINERAL_PRESET_ALIASES = {
    "ilmenite": "fe_ti_oxide",
}
_PATTERN_YLABELS = {
    "Без нормировки": "Concentration [µg/g equivalent]",
    "CI-хондрит · McDonough & Sun (1995)": "Sample / CI chondrite",
    "Primitive mantle · Sun & McDonough (1989)": "Sample / primitive mantle",
}
_LINE_STYLES = ("-", "--", ":", "-.")


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


def _selected_point_details(dataframe: pd.DataFrame, selected_ids: list[str]) -> None:
    if not selected_ids or "_analysis_id" not in dataframe.columns:
        return
    selected = dataframe[dataframe["_analysis_id"].astype(str).isin(selected_ids)].copy()
    st.caption(f"Выбрано интерактивно: {len(selected)}")
    preview = [
        column for column in ["Sample", "Grain", "Point", "Generation", "Набор", "Минерал"]
        if column in selected.columns
    ]
    if preview:
        st.dataframe(selected[preview].head(200), width="stretch", hide_index=True, height=220)
    if len(selected) == 1:
        row = selected.iloc[0]
        assets = collect_related_images(row)
        if assets:
            render_asset_gallery(assets)


def _mineral_filtered_presets(dataframe: pd.DataFrame) -> dict:
    presets = {
        key: preset
        for key, preset in SCIENTIFIC_PLOT_PRESETS.items()
        if preset.plot_type == "xy"
    }
    if "Минерал" not in dataframe.columns:
        return presets
    present = set(dataframe["Минерал"].dropna().astype(str))
    return {
        key: preset
        for key, preset in presets.items()
        if preset.mineral_key is None
        or MINERAL_PRESET_ALIASES.get(str(preset.mineral_key), str(preset.mineral_key)) in present
    }


def _axis_candidates(dataframe: pd.DataFrame, requested: str, numeric: list[str]) -> list[str]:
    """Return only columns that preserve the preset quantity and unit semantics."""
    candidates: list[str] = []
    if requested in numeric:
        candidates.append(requested)
    prefix = f"{requested} ["
    for column in numeric:
        text = str(column)
        if text.startswith(prefix) and "µg/g" in text and text not in candidates:
            candidates.append(text)
    return candidates


def _sync_science_axis_defaults(preset_id: str, preset, x: str, y: str, matches_preset: bool) -> None:
    """Reset literature labels only when the selected axes/preset actually change."""
    signature = (str(preset_id), str(x), str(y))
    key = "_science_xy_axis_signature"
    if st.session_state.get(key) == signature:
        return
    if matches_preset:
        st.session_state["science_xy_title"] = preset.title
        st.session_state["science_xy_xlabel"] = preset.x_label or x
        st.session_state["science_xy_ylabel"] = preset.y_label or y
    else:
        st.session_state["science_xy_title"] = ""
        st.session_state["science_xy_xlabel"] = str(x)
        st.session_state["science_xy_ylabel"] = str(y)
    st.session_state[key] = signature


def _render_scientific_xy(dataframe: pd.DataFrame) -> None:
    numeric = numeric_candidates(dataframe)
    applicable = _mineral_filtered_presets(dataframe)
    if not applicable:
        st.info("Для выбранных минералов пока нет готовых научных XY preset'ов.")
        return
    if not numeric:
        st.warning("Нет числовых колонок.")
        return

    preset_id = st.selectbox(
        "Научный шаблон",
        list(applicable),
        format_func=lambda key: applicable[key].title,
        key="science_xy_preset",
    )
    preset = applicable[preset_id]

    x_candidates = _axis_candidates(dataframe, preset.x, numeric)
    y_candidates = _axis_candidates(dataframe, preset.y, numeric)
    x_default = x_candidates[0] if x_candidates else numeric[0]
    y_default = y_candidates[0] if y_candidates else next((column for column in numeric if column != x_default), numeric[0])
    if not x_candidates or not y_candidates:
        missing = [name for name, candidates in [(preset.x, x_candidates), (preset.y, y_candidates)] if not candidates]
        st.warning(
            "В выбранных данных нет ожидаемых колонок шаблона: " + ", ".join(missing) +
            ". Оси можно выбрать вручную; литературную подпись отсутствующей оси ПетроЛаб не подставляет."
        )

    c1, c2 = st.columns(2)
    x = c1.selectbox("Ось X", numeric, index=numeric.index(x_default), key="science_xy_x")
    y = c2.selectbox("Ось Y", numeric, index=numeric.index(y_default), key="science_xy_y")
    matches_preset = x in x_candidates and y in y_candidates
    _sync_science_axis_defaults(preset_id, preset, x, y, matches_preset)

    if matches_preset:
        st.caption(f"Источник: {preset.source}" + (f" · DOI {preset.doi}" if preset.doi else ""))
        if preset.note:
            st.info(preset.note)
    else:
        st.caption(
            "Пользовательские оси: литературное название, source citation и overlay preset'а отключены."
        )

    l1, l2 = st.columns(2)
    x_label = l1.text_input("Подпись X", key="science_xy_xlabel")
    y_label = l2.text_input("Подпись Y", key="science_xy_ylabel")
    title = st.text_input("Название рисунка", key="science_xy_title")

    categories = _categorical_candidates(dataframe)
    group_column = st.selectbox("Группировать точки", ["Без группировки"] + categories, key="science_xy_group")
    group_column = None if group_column == "Без группировки" else group_column

    style = render_figure_style_controls(dataframe, key_prefix="science_xy")
    fields = render_custom_fields("science_xy")
    overlay_enabled = False
    if preset.overlay_id and preset.overlay_id in XY_OVERLAYS:
        if not matches_preset:
            st.caption("Литературный overlay отключён: выбранные оси отличаются от схемы preset'а.")
        else:
            overlay_enabled = st.checkbox(
                "Показывать литературное поле/линию",
                value=True,
                key="science_xy_overlay",
            )
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
    _selected_point_details(dataframe, selected_analysis_ids(event))

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
        overlay_id=preset.overlay_id if overlay_enabled and matches_preset else None,
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


def _apply_pattern_group_styles(figure, pattern, group: pd.Series | None, *, monochrome: bool) -> None:
    """Keep all curves of one geological group visually consistent."""
    if group is None or pattern.data.empty or not figure.axes:
        return
    groups = (
        group.reindex(pattern.data.index)
        .astype("string")
        .fillna("Без группы")
        .replace("", "Без группы")
    )
    names = list(dict.fromkeys(groups.tolist()))
    colors = plt.rcParams["axes.prop_cycle"].by_key().get("color", ["black"])
    styles = {
        name: (colors[index % len(colors)], _LINE_STYLES[index % len(_LINE_STYLES)])
        for index, name in enumerate(names)
    }
    for line, name in zip(figure.axes[0].lines, groups.tolist()):
        color, linestyle = styles[name]
        if monochrome:
            line.set_color("black")
            line.set_linestyle(linestyle)
        else:
            line.set_color(color)


def _render_pattern(dataframe: pd.DataFrame) -> None:
    mode = st.segmented_control("Тип", ["REE", "Spider / multi-element"], default="REE", key="pattern_mode")
    preferred = REE_ORDER if mode == "REE" else SPIDER_ORDER
    settings = load_settings()
    reference_names = list(NORMALIZATION_REFERENCES)
    preferred_reference = (
        str(settings.get("default_ree_reference", reference_names[1]))
        if mode == "REE" else "Primitive mantle · Sun & McDonough (1989)"
    )
    reference_name = st.selectbox(
        "Нормировка",
        reference_names,
        index=reference_names.index(preferred_reference) if preferred_reference in reference_names else (1 if mode == "REE" else 2),
        key="pattern_ref",
    )
    reference = NORMALIZATION_REFERENCES[reference_name]
    available = available_elements(
        dataframe,
        preferred,
        require_known_units=True,
        reference=reference,
    )
    if len(available) < 2:
        st.info(
            "Недостаточно элементов с подходящими числовыми концентрациями. REE/spider использует "
            "только колонки с известной единицей ppm/µg/g-equivalent; K, P и Ti также могут быть "
            "стехиометрически получены из K2O, P2O5 и TiO2 wt.% с явным provenance."
        )
        return
    selected = st.multiselect("Элементы", list(preferred), default=available, key="pattern_elements")
    pattern = prepare_pattern(dataframe, selected, reference)
    if pattern.missing_elements:
        st.caption("Не использованы: " + ", ".join(pattern.missing_elements))
    if pattern.missing_reference_elements:
        st.caption("Нет валидного значения в выбранной нормировке: " + ", ".join(pattern.missing_reference_elements))
    converted = [label for label in pattern.source_columns.values() if "→" in label]
    if converted:
        st.caption("Стехиометрические преобразования: " + "; ".join(converted))
    st.caption(f"Вошло кривых: {len(pattern.data)} · исключено пустых строк: {pattern.excluded_rows}")

    categories = _categorical_candidates(dataframe)
    group = st.selectbox("Легенда/группа", ["Каждый анализ"] + categories, key="pattern_group")
    group_series = None if group == "Каждый анализ" else dataframe[group]
    label_candidates = [column for column in ["Sample", "Grain", "Point", "Generation", "Набор"] if column in dataframe.columns]
    label_column = st.selectbox("Подпись отдельной кривой", ["Индекс"] + label_candidates, key="pattern_label")
    labels = None if label_column == "Индекс" else dataframe[label_column]
    style = render_figure_style_controls(dataframe, key_prefix="pattern")
    ylabel = _PATTERN_YLABELS.get(reference_name, "Concentration")
    title = st.text_input("Название", value="REE pattern" if mode == "REE" else "Multi-element pattern", key="pattern_title")
    point_style = POINT_STYLE_PRESETS[style.point_style_name]
    figure = build_pattern_figure(
        pattern,
        labels=labels,
        group=group_series,
        title=title,
        ylabel=ylabel,
        log_y=st.checkbox("Логарифмическая Y", value=True, key="pattern_log"),
        show_legend=style.show_legend,
        linewidth=style.line_width,
        alpha=point_style.alpha,
        marker=point_style.markers[0],
        marker_size=max(2.0, style.marker_size / 14.0),
        grid=style.grid,
        monochrome=style.monochrome,
        font_family=style.font_family,
        font_size=style.font_size,
        figure_size=(style.width_in, style.height_in),
    )
    _apply_pattern_group_styles(figure, pattern, group_series, monochrome=style.monochrome)
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
    figure = build_histogram_figure(
        dataframe,
        column,
        bins=bins,
        group_column=group,
        density=density,
        grid=style.grid,
        monochrome=style.monochrome,
        show_legend=style.show_legend,
        font_family=style.font_family,
        font_size=style.font_size,
        figure_size=(style.width_in, style.height_in),
    )
    st.pyplot(figure, width="stretch")
    c1, c2 = st.columns(2)
    c1.download_button(
        "PNG",
        figure_bytes(figure, "png", style.dpi),
        file_name="histogram.png",
        mime="image/png",
        key="hist_png",
    )
    c2.download_button(
        "SVG",
        figure_bytes(figure, "svg", style.dpi),
        file_name="histogram.svg",
        mime="image/svg+xml",
        key="hist_svg",
    )
    plt.close(figure)


def _render_boxplot(dataframe: pd.DataFrame) -> None:
    numeric = numeric_candidates(dataframe)
    if not numeric:
        st.info("Нет числовых колонок.")
        return
    columns = st.multiselect("Числовые параметры", numeric, default=numeric[:1], key="box_columns")
    categories = _categorical_candidates(dataframe)
    group = st.selectbox("Группировка", ["Нет"] + categories, key="box_group")
    group = None if group == "Нет" else group
    style = render_figure_style_controls(dataframe, key_prefix="box")
    if not columns:
        return
    if group and len(columns) > 1:
        st.warning(
            "Grouped boxplot требует ровно один числовой параметр. "
            "График не построен: выберите один Y или отключите группировку."
        )
        return
    figure = build_boxplot_figure(
        dataframe,
        columns,
        group_column=group,
        show_fliers=st.checkbox("Показывать выбросы", value=True, key="box_fliers"),
        grid=style.grid,
        font_family=style.font_family,
        font_size=style.font_size,
        figure_size=(style.width_in, style.height_in),
    )
    st.pyplot(figure, width="stretch")
    c1, c2 = st.columns(2)
    c1.download_button(
        "PNG",
        figure_bytes(figure, "png", style.dpi),
        file_name="boxplot.png",
        mime="image/png",
        key="box_png",
    )
    c2.download_button(
        "SVG",
        figure_bytes(figure, "svg", style.dpi),
        file_name="boxplot.svg",
        mime="image/svg+xml",
        key="box_svg",
    )
    plt.close(figure)


def render_science_plots_page() -> None:
    render_page_header(
        "Научные диаграммы",
        "Классификационные XY, REE/spider, гистограммы и boxplot с проверяемыми литературными полями и явной нормировкой.",
        eyebrow="Исследование",
    )
    scope = render_analysis_scope("science_plots")
    if scope is None:
        return
    tab_xy, tab_pattern, tab_hist, tab_box = st.tabs([
        "Классификационные и рабочие XY",
        "REE / Spider",
        "Гистограмма",
        "Boxplot",
    ])
    with tab_xy:
        _render_scientific_xy(scope.dataframe)
    with tab_pattern:
        _render_pattern(scope.dataframe)
    with tab_hist:
        _render_histogram(scope.dataframe)
    with tab_box:
        _render_boxplot(scope.dataframe)
