from __future__ import annotations

import streamlit as st

from petrolab.analysis_groups import WORK_GROUP_COLUMN, attach_work_groups
from petrolab.dataframe_utils import apply_column_filters, apply_quick_filter, dataset_label
from petrolab.db import list_accessible_datasets, list_datasets, list_plot_recipes
from petrolab.derived import load_unified_with_derived
from petrolab.minerals.registry import MINERALS
from petrolab.ui.components import render_project_selector
from petrolab.ui.pages.plots_ternary import render_ternary_workspace


def render_ternary_page() -> None:
    st.title("Треугольные диаграммы")
    st.write(
        "Универсальные ternary-диаграммы и минералогические шаблоны работают с исходными "
        "и сохранёнными расчётными величинами из единой базы."
    )

    scope = st.radio("Область данных", ["Один проект", "Все проекты"], horizontal=True, key="ternary_scope")
    project_id = None
    if scope == "Один проект":
        project = render_project_selector("ternary_project")
        if project is None:
            return
        project_id = int(project["id"])

    datasets = list_datasets(None) if scope == "Все проекты" else list_accessible_datasets(int(project_id))
    if not datasets:
        st.info("Нет данных для построения ternary-диаграммы.")
        return

    recipe_records = [
        record for record in list_plot_recipes(project_id)
        if record.get("config", {}).get("chart_type") == "Треугольная"
    ]
    with st.expander("Сохранённые ternary-рецепты", expanded=False):
        if recipe_records:
            recipe_map = {
                f"{record['name']} · {('общий' if record['project_id'] is None else 'проект')}": record
                for record in recipe_records
            }
            selected_recipe = st.selectbox("Рецепт", ["—"] + list(recipe_map), key="ternary_recipe_select")
            if selected_recipe != "—" and st.button("Применить рецепт", key="ternary_recipe_load"):
                st.session_state.loaded_ternary_recipe = recipe_map[selected_recipe]["config"]
                cfg = recipe_map[selected_recipe]["config"]
                st.session_state.ternary_interactive_excluded_ids = list(
                    cfg.get("ternary_interactive_excluded_ids", [])
                )
                st.rerun()
        else:
            st.caption("Сохранённых ternary-рецептов пока нет.")
        if st.button("Сбросить ternary-рецепт", key="ternary_recipe_reset"):
            st.session_state.loaded_ternary_recipe = None
            st.session_state.ternary_interactive_excluded_ids = []
            st.rerun()

    recipe = st.session_state.get("loaded_ternary_recipe") or {}
    if "ternary_interactive_excluded_ids" not in st.session_state:
        st.session_state.ternary_interactive_excluded_ids = list(
            recipe.get("ternary_interactive_excluded_ids", [])
        )

    labels = {dataset_label(dataset): int(dataset["id"]) for dataset in datasets}
    wanted_ids = recipe.get("dataset_ids", list(labels.values()))
    defaults = [label for label, dataset_id in labels.items() if dataset_id in wanted_ids]
    selected_labels = st.multiselect(
        "Наборы данных",
        list(labels),
        default=defaults or list(labels),
        key="ternary_datasets",
    )
    selected_ids = [labels[label] for label in selected_labels]
    if not selected_ids:
        return

    dataframe = attach_work_groups(load_unified_with_derived(project_id, selected_ids))
    if dataframe.empty:
        st.info("В выбранных наборах нет аналитических строк.")
        return

    minerals = sorted(dataframe["Минерал"].dropna().astype(str).unique())
    saved_minerals = recipe.get("minerals", minerals)
    selected_minerals = st.multiselect(
        "Минералы",
        minerals,
        default=[value for value in saved_minerals if value in minerals],
        format_func=lambda key: MINERALS.get(key, MINERALS["generic"]).name_ru,
        key="ternary_minerals",
    )
    if selected_minerals:
        dataframe = dataframe[dataframe["Минерал"].astype(str).isin(selected_minerals)]

    query = st.text_input("Быстрый поиск", value=recipe.get("query", ""), key="ternary_search")
    dataframe = apply_quick_filter(dataframe, query)

    with st.expander("Фильтры по группам и категориям", expanded=False):
        candidates = [
            column for column in dataframe.columns
            if not str(column).startswith("_") and dataframe[column].nunique(dropna=True) <= 100
        ]
        preferred = [
            column for column in [
                WORK_GROUP_COLUMN, "Проект", "Набор", "Минерал", "Источник", "Лист",
                "Generation", "Group", "Type", "Sample", "Grain",
            ]
            if column in candidates
        ]
        filter_columns = st.multiselect(
            "Колонки для фильтрации",
            preferred + [column for column in candidates if column not in preferred],
            default=[column for column in recipe.get("column_filters", {}) if column in candidates],
            key="ternary_filter_columns",
        )
        chosen_filters: dict[str, list[str]] = {}
        for column in filter_columns:
            values = sorted(dataframe[column].dropna().astype(str).unique().tolist())
            saved = [value for value in recipe.get("column_filters", {}).get(column, []) if value in values]
            chosen_filters[column] = st.multiselect(
                column,
                values,
                default=saved,
                key=f"ternary_filter_{column}",
            )
        if chosen_filters:
            dataframe = apply_column_filters(dataframe, chosen_filters)

    if dataframe.empty:
        st.warning("После фильтрации не осталось точек.")
        return

    render_ternary_workspace(
        dataframe,
        project_id=project_id,
        selected_dataset_ids=selected_ids,
        selected_minerals=selected_minerals,
        query=query,
        column_filters=chosen_filters,
        recipe=recipe,
    )
