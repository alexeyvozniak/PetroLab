from __future__ import annotations

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

from petrolab.analysis_groups import WORK_GROUP_COLUMN, attach_work_groups
from petrolab.dataframe_utils import apply_quick_filter, dataset_label
from petrolab.db import list_datasets, list_projects
from petrolab.derived import load_unified_with_derived
from petrolab.io_utils import numeric_candidates
from petrolab.minerals.registry import MINERALS
from petrolab.plotting import build_scatter, figure_png_bytes, figure_svg_bytes
from petrolab.settings_service import load_settings
from petrolab.ui.layout import render_badges, render_page_header
from petrolab.ui.pages import plots as legacy


def _project_id() -> int | None:
    projects = list_projects()
    if not projects:
        return None
    ids = [int(item["id"]) for item in projects]
    try:
        value = int(st.session_state.get("active_project_id", ids[0]))
    except (TypeError, ValueError):
        value = ids[0]
    if value not in ids:
        value = ids[0]
    st.session_state["active_project_id"] = value
    return value


def _quick_workspace(project_id: int) -> None:
    datasets = list_datasets(project_id)
    if not datasets:
        st.info("В активном проекте нет данных для графика."); return
    labels = {dataset_label(item): int(item["id"]) for item in datasets}

    left, right = st.columns([1, 2.2], gap="large")
    with left:
        st.markdown("### Данные")
        selected_labels = st.multiselect("Наборы", list(labels), default=list(labels), key="quick_plot_datasets")
        selected_ids = [labels[label] for label in selected_labels]
        if not selected_ids:
            st.info("Выберите хотя бы один набор."); return
        dataframe = attach_work_groups(load_unified_with_derived(project_id, selected_ids))
        minerals = sorted(dataframe["Минерал"].dropna().astype(str).unique())
        selected_minerals = st.multiselect(
            "Минералы", minerals, default=minerals, key="quick_plot_minerals",
            format_func=lambda key: MINERALS.get(key, MINERALS["generic"]).name_ru,
        )
        if not selected_minerals:
            st.info("Выберите хотя бы один минерал."); return
        dataframe = dataframe[dataframe["Минерал"].astype(str).isin(selected_minerals)]
        query = st.text_input("Поиск", placeholder="Образец, поколение, группа…", key="quick_plot_search")
        dataframe = apply_quick_filter(dataframe, query)
        numeric = numeric_candidates(dataframe)
        if len(numeric) < 2:
            st.info("После фильтрации недостаточно числовых колонок."); return
        x = st.selectbox("X", numeric, key="quick_x")
        y_default = min(1, len(numeric) - 1)
        y = st.selectbox("Y", numeric, index=y_default, key="quick_y")
        categorical = [column for column in dataframe.columns if not str(column).startswith("_") and column not in numeric and dataframe[column].nunique(dropna=True) <= 80]
        preferred = [column for column in [WORK_GROUP_COLUMN, "Generation", "Набор", "Минерал"] if column in categorical]
        groups = preferred + [column for column in categorical if column not in preferred]
        group = st.selectbox("Группа", ["Без группировки"] + groups, key="quick_group")
        group_col = None if group == "Без группировки" else group
        with st.expander("Оси и вид", expanded=False):
            log_x = st.checkbox("Логарифмическая X", key="quick_log_x")
            log_y = st.checkbox("Логарифмическая Y", key="quick_log_y")
            title = st.text_input("Заголовок", key="quick_title")
            marker_size = st.slider("Размер точек", 20, 120, 48, 2, key="quick_marker_size")

        plot_source = dataframe.copy()
        plot_source[x] = pd.to_numeric(plot_source[x], errors="coerce")
        plot_source[y] = pd.to_numeric(plot_source[y], errors="coerce")
        plot_source = plot_source.dropna(subset=[x, y])
        if log_x: plot_source = plot_source[plot_source[x] > 0]
        if log_y: plot_source = plot_source[plot_source[y] > 0]
        if plot_source.empty:
            st.info("После фильтрации не осталось точек для выбранных осей."); return
        if group_col:
            names = plot_source[group_col].astype("string").fillna("Без группы").replace("", "Без группы").unique().tolist()
        else:
            names = ["Все точки"]
        style_df = legacy._style_df_from_groups([str(value) for value in names])
        style_map = legacy._style_map_from_df(style_df)
        render_badges([(f"{len(plot_source):,} точек".replace(",", " "), "accent"), (f"{len(names)} групп", "neutral")])

    with right:
        legacy._render_interactive_workspace(
            plot_source, project_id, x, y, group_col, x, y, title, log_x, log_y, style_map
        )

    st.markdown('<div class="petrolab-export-zone"></div>', unsafe_allow_html=True)
    st.markdown("### Публикационный экспорт")
    settings = load_settings()
    figure = build_scatter(
        plot_source, x, y, group_col,
        x_label=x, y_label=y, title=title, marker_size=marker_size,
        log_x=log_x, log_y=log_y, style_map=style_map,
        font_family="Arial", font_size=9.0, tick_size=8.5,
    )
    e1, e2, e3 = st.columns([1, 1, 2])
    e1.download_button("SVG", figure_svg_bytes(figure), file_name="petrolab_xy.svg", mime="image/svg+xml", width="stretch")
    e2.download_button("PNG", figure_png_bytes(figure, 600), file_name="petrolab_xy.png", mime="image/png", width="stretch")
    e3.caption(f"Arial · 600 dpi · шаблон по умолчанию: {settings.get('default_figure_preset', 'Lithos')}")
    plt.close(figure)


def render_plots_dashboard_page() -> None:
    render_page_header(
        "XY-диаграммы",
        "Сначала выберите данные и оси — график остаётся главным объектом. Расширенные фильтры и журнальное оформление доступны отдельно.",
        eyebrow="Исследование",
    )
    project_id = _project_id()
    if project_id is None:
        st.info("Сначала создайте проект."); return
    quick, advanced = st.tabs(["Быстрое построение", "Расширенный редактор"])
    with quick:
        _quick_workspace(project_id)
    with advanced:
        legacy.render_plots_page()
