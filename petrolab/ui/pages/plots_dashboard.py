from __future__ import annotations

import matplotlib.pyplot as plt
import streamlit as st

from petrolab.analysis_groups import WORK_GROUP_COLUMN, attach_work_groups
from petrolab.dataframe_utils import apply_quick_filter, dataset_label
from petrolab.db import list_datasets
from petrolab.derived import load_unified_with_derived
from petrolab.io_utils import numeric_candidates
from petrolab.minerals.registry import MINERALS
from petrolab.plotting import build_scatter, figure_png_bytes, figure_svg_bytes
from petrolab.settings_service import load_settings
from petrolab.ui.layout import render_badges, render_page_header
from petrolab.ui.pages.plots_advanced import render_advanced_xy_workspace
from petrolab.ui.project_context import active_project_id
from petrolab.ui.xy_components import (
    render_quick_interactive,
    sanitize_xy_rows,
    style_dataframe,
    style_map,
)
from petrolab.visualization_presets import FIGURE_PRESETS


def _quick_workspace(project_id: int) -> None:
    datasets = list_datasets(project_id)
    if not datasets:
        st.info("В активном проекте нет данных для графика.")
        return
    labels = {dataset_label(item): int(item["id"]) for item in datasets}
    settings = load_settings()
    preset_name = str(settings.get("default_figure_preset", "Lithos"))
    preset = FIGURE_PRESETS.get(preset_name, FIGURE_PRESETS["Lithos"])

    left, right = st.columns([1, 2.2], gap="large")
    with left:
        st.markdown("### Данные")
        selected_labels = st.multiselect(
            "Наборы", list(labels), default=list(labels), key="quick_plot_datasets"
        )
        selected_ids = [labels[label] for label in selected_labels]
        if not selected_ids:
            st.info("Выберите хотя бы один набор.")
            return
        dataframe = attach_work_groups(load_unified_with_derived(project_id, selected_ids))
        minerals = sorted(dataframe["Минерал"].dropna().astype(str).unique())
        selected_minerals = st.multiselect(
            "Минералы",
            minerals,
            default=minerals,
            key="quick_plot_minerals",
            format_func=lambda key: MINERALS.get(key, MINERALS["generic"]).name_ru,
        )
        if not selected_minerals:
            st.info("Выберите хотя бы один минерал.")
            return
        dataframe = dataframe[dataframe["Минерал"].astype(str).isin(selected_minerals)]
        query = st.text_input(
            "Поиск", placeholder="Образец, поколение, группа…", key="quick_plot_search"
        )
        dataframe = apply_quick_filter(dataframe, query)
        numeric = numeric_candidates(dataframe)
        if len(numeric) < 2:
            st.info("После фильтрации недостаточно числовых колонок.")
            return
        x = st.selectbox("X", numeric, key="quick_x")
        y = st.selectbox("Y", numeric, index=min(1, len(numeric) - 1), key="quick_y")
        categorical = [
            column
            for column in dataframe.columns
            if not str(column).startswith("_")
            and column not in numeric
            and dataframe[column].nunique(dropna=True) <= 80
        ]
        preferred = [
            column
            for column in [WORK_GROUP_COLUMN, "Generation", "Набор", "Минерал"]
            if column in categorical
        ]
        groups = preferred + [column for column in categorical if column not in preferred]
        group = st.selectbox("Группа", ["Без группировки"] + groups, key="quick_group")
        group_col = None if group == "Без группировки" else group
        with st.expander("Оси и вид", expanded=False):
            log_x = st.checkbox("Логарифмическая X", key="quick_log_x")
            log_y = st.checkbox("Логарифмическая Y", key="quick_log_y")
            title = st.text_input("Заголовок", key="quick_title")
            marker_size = st.slider(
                "Размер точек",
                20,
                120,
                int(round(preset.marker_size)),
                2,
                key="quick_marker_size",
            )

        plot_source = sanitize_xy_rows(
            dataframe,
            x,
            y,
            log_x=log_x,
            log_y=log_y,
            group_column=group_col,
        )
        if plot_source.empty:
            st.info("После фильтрации не осталось точек для выбранных осей.")
            return
        if group_col:
            names = plot_source[group_col].astype(str).unique().tolist()
        else:
            names = ["Все точки"]
        styles = style_map(style_dataframe([str(value) for value in names]))
        render_badges([
            (f"{len(plot_source):,} точек".replace(",", " "), "accent"),
            (f"{len(names)} групп", "neutral"),
        ])

    with right:
        render_quick_interactive(
            plot_source,
            x,
            y,
            group_col,
            x_label=x,
            y_label=y,
            title=title,
            log_x=log_x,
            log_y=log_y,
            styles=styles,
        )

    st.markdown('<div class="petrolab-export-zone"></div>', unsafe_allow_html=True)
    st.markdown("### Публикационный экспорт")
    figure = build_scatter(
        plot_source,
        x,
        y,
        group_col,
        x_label=x,
        y_label=y,
        title=title,
        marker_size=marker_size,
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
    e1, e2, e3 = st.columns([1, 1, 2])
    e1.download_button(
        "SVG", figure_svg_bytes(figure), file_name="petrolab_xy.svg",
        mime="image/svg+xml", width="stretch"
    )
    e2.download_button(
        "PNG", figure_png_bytes(figure, preset.dpi), file_name="petrolab_xy.png",
        mime="image/png", width="stretch"
    )
    e3.caption(
        f"{preset.title} · {preset.font_family} · {preset.dpi} dpi · "
        f"{preset.width_in:g} × {preset.height_in:g} in"
    )
    plt.close(figure)


def render_plots_dashboard_page() -> None:
    render_page_header(
        "XY-диаграммы",
        "Быстрое построение для ежедневной работы и полный редактор для фильтрации, отбора точек и публикационного экспорта.",
        eyebrow="Исследование",
    )
    project_id = active_project_id()
    if project_id is None:
        st.info("Сначала создайте проект.")
        return
    quick, advanced = st.tabs(["Быстрое построение", "Расширенный редактор"])
    with quick:
        _quick_workspace(project_id)
    with advanced:
        render_advanced_xy_workspace(project_id)
