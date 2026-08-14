from __future__ import annotations

import io
import json

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

from petrolab.analysis_groups import WORK_GROUP_COLUMN, attach_work_groups
from petrolab.dataframe_utils import apply_column_filters, apply_quick_filter, dataset_label
from petrolab.db import (
    list_datasets,
    list_plot_recipes,
    list_style_profiles,
    save_plot_recipe,
    save_style_profile,
)
from petrolab.derived import load_unified_with_derived
from petrolab.io_utils import numeric_candidates
from petrolab.minerals.registry import MINERALS
from petrolab.plot_presets import JOURNAL_PRESETS
from petrolab.plotting import MARKERS, build_scatter, figure_png_bytes, figure_svg_bytes
from petrolab.ui.plot_actions import (
    delete_plot_recipe,
    delete_style_profile,
    render_plot_confirmations,
)
from petrolab.ui.xy_components import (
    apply_interactive_exclusions,
    render_advanced_interactive,
    render_outlier_controls,
    sanitize_xy_rows,
    style_dataframe,
    style_map,
)


def _recipe_controls(project_id: int) -> tuple[dict, list[dict]]:
    """Load/reset saved XY recipes without rendering another project scope."""
    recipe_records = list_plot_recipes(project_id)
    style_records = list_style_profiles(project_id)
    with st.expander("Сохранённые рецепты и профили", expanded=False):
        if recipe_records:
            recipe_map = {
                f"{record['name']} · {('общий' if record['project_id'] is None else 'проект')}": record
                for record in recipe_records
            }
            chosen_label = st.selectbox(
                "Загрузить рецепт",
                ["—"] + list(recipe_map),
                key="recipe_select",
            )
            load_col, delete_col = st.columns(2)
            if chosen_label != "—":
                chosen = recipe_map[chosen_label]
                if load_col.button("Применить рецепт", key="load_recipe_btn", width="stretch"):
                    st.session_state.loaded_recipe = chosen["config"]
                    cfg = chosen["config"].get("outlier_filters", {})
                    st.session_state.plot_interactive_excluded_ids = list(
                        cfg.get("interactive_excluded_ids", []) if isinstance(cfg, dict) else []
                    )
                    st.rerun()
                if delete_col.button("Удалить рецепт", key="delete_recipe_btn", width="stretch"):
                    delete_plot_recipe(int(chosen["id"]))
                    if "_pending_destructive_plot_recipe" not in st.session_state:
                        st.success("Рецепт удалён.")
                    st.rerun()
        else:
            st.caption("Сохранённых рецептов пока нет.")

        if st.button("Сбросить применённый рецепт", key="reset_recipe_btn"):
            st.session_state.loaded_recipe = None
            st.session_state.plot_interactive_excluded_ids = []
            st.rerun()

    recipe = st.session_state.get("loaded_recipe") or {}
    if not isinstance(recipe, dict):
        recipe = {}
    if "plot_interactive_excluded_ids" not in st.session_state:
        cfg = recipe.get("outlier_filters", {})
        st.session_state.plot_interactive_excluded_ids = list(
            cfg.get("interactive_excluded_ids", []) if isinstance(cfg, dict) else []
        )
    return recipe, style_records


def _stale_recipe_guard(project_id: int, recipe: dict) -> bool:
    wanted: list[int] = []
    for value in recipe.get("dataset_ids", []):
        try:
            wanted.append(int(value))
        except (TypeError, ValueError):
            continue
    if not wanted:
        return False
    available = {int(item["id"]) for item in list_datasets(project_id)}
    if any(dataset_id in available for dataset_id in wanted):
        return False
    st.warning(
        "Сохранённый рецепт ссылается на наборы, которых больше нет в активном проекте. "
        "PetroLab не заменяет их автоматически всеми наборами."
    )
    if st.button("Сбросить устаревший рецепт", key="reset_stale_recipe"):
        st.session_state.loaded_recipe = None
        st.session_state.plot_interactive_excluded_ids = []
        st.rerun()
    return True


def _filter_controls(dataframe: pd.DataFrame, recipe: dict) -> tuple[pd.DataFrame, str, dict[str, list[str]]]:
    query = st.text_input("Поиск", value=recipe.get("query", ""), key="plot_search")
    dataframe = apply_quick_filter(dataframe, query)
    chosen_filters: dict[str, list[str]] = {}
    with st.expander("Фильтры по группам и категориям", expanded=False):
        candidates = [
            column
            for column in dataframe.columns
            if not str(column).startswith("_") and dataframe[column].nunique(dropna=True) <= 100
        ]
        preferred = [
            column
            for column in [
                WORK_GROUP_COLUMN, "Проект", "Набор", "Минерал", "Источник", "Лист",
                "Generation", "Group", "Type", "Sample", "Grain",
            ]
            if column in candidates
        ]
        choices = st.multiselect(
            "Колонки для фильтрации",
            preferred + [column for column in candidates if column not in preferred],
            default=[column for column in recipe.get("column_filters", {}) if column in candidates],
            key="column_filter_columns",
        )
        for column in choices:
            values = sorted(dataframe[column].dropna().astype(str).unique().tolist())
            defaults = [
                value
                for value in recipe.get("column_filters", {}).get(column, [])
                if value in values
            ]
            chosen_filters[column] = st.multiselect(
                column,
                values,
                default=defaults,
                key=f"filter_vals_{column}",
            )
        if chosen_filters:
            dataframe = apply_column_filters(dataframe, chosen_filters)
    return dataframe, query, chosen_filters


def _appearance_controls(
    plot_source: pd.DataFrame,
    recipe: dict,
    preset_cfg: dict,
    x: str,
    y: str,
) -> dict:
    c1, c2, c3, c4 = st.columns(4)
    x_label = c1.text_input("Подпись X", value=recipe.get("x_label", x))
    y_label = c2.text_input("Подпись Y", value=recipe.get("y_label", y))
    marker_size = c3.slider(
        "Размер маркеров",
        10,
        180,
        int(recipe.get("marker_size", preset_cfg["marker_size"])),
        2,
    )
    title = c4.text_input("Заголовок", value=recipe.get("title", ""))

    with st.expander("Оси, подписи и журнальное оформление", expanded=False):
        a1, a2, a3, a4 = st.columns(4)
        x_min = a1.number_input("X min", value=recipe.get("x_min", None), step=0.1)
        x_max = a2.number_input("X max", value=recipe.get("x_max", None), step=0.1)
        y_min = a3.number_input("Y min", value=recipe.get("y_min", None), step=0.1)
        y_max = a4.number_input("Y max", value=recipe.get("y_max", None), step=0.1)
        b1, b2, b3, b4 = st.columns(4)
        log_x = b1.checkbox("Логарифмическая X", value=recipe.get("log_x", False))
        log_y = b2.checkbox("Логарифмическая Y", value=recipe.get("log_y", False))
        show_grid = b3.checkbox("Сетка", value=recipe.get("show_grid", preset_cfg["show_grid"]))
        monochrome = b4.checkbox("Ч/б режим", value=recipe.get("monochrome", preset_cfg["monochrome"]))
        d1, d2, d3 = st.columns(3)
        show_legend = d1.checkbox("Показывать легенду", value=recipe.get("show_legend", preset_cfg["show_legend"]))
        annotate = d2.checkbox("Подписывать точки", value=recipe.get("annotate", False))
        label_candidates = [
            column
            for column in plot_source.columns
            if not str(column).startswith("_")
            and plot_source[column].nunique(dropna=True) <= max(200, len(plot_source))
        ]
        label_default = recipe.get("label_col")
        label_choice = d3.selectbox(
            "Поле для подписи",
            ["—"] + label_candidates,
            index=1 + label_candidates.index(label_default) if label_default in label_candidates else 0,
        )
        label_col = None if label_choice == "—" else label_choice
        annotate_top_n = (
            st.slider("Сколько точек подписывать", 1, 1000, int(recipe.get("annotate_top_n", 25)))
            if annotate and label_col
            else 0
        )
        e1, e2, e3, e4 = st.columns(4)
        figure_width = e1.number_input(
            "Ширина фигуры", 3.0, 20.0,
            value=float(recipe.get("figure_width", preset_cfg["figure_width"])), step=0.1,
        )
        figure_height = e2.number_input(
            "Высота фигуры", 3.0, 20.0,
            value=float(recipe.get("figure_height", preset_cfg["figure_height"])), step=0.1,
        )
        font_size = e3.number_input(
            "Размер шрифта", 6.0, 24.0,
            value=float(recipe.get("font_size", preset_cfg["font_size"])), step=0.5,
        )
        tick_size = e4.number_input(
            "Размер подписей делений", 6.0, 24.0,
            value=float(recipe.get("tick_size", preset_cfg["tick_size"])), step=0.5,
        )
        f1, f2 = st.columns(2)
        spine_width = f1.number_input(
            "Толщина осей", 0.5, 3.0,
            value=float(recipe.get("spine_width", preset_cfg["spine_width"])), step=0.1,
        )
        title_size = f2.number_input(
            "Размер заголовка", 6.0, 28.0,
            value=float(recipe.get("title_size", float(recipe.get("font_size", preset_cfg["font_size"])) + 1.0)),
            step=0.5,
        )
    return {
        "x_label": x_label, "y_label": y_label, "marker_size": marker_size, "title": title,
        "x_min": x_min, "x_max": x_max, "y_min": y_min, "y_max": y_max,
        "log_x": log_x, "log_y": log_y, "show_grid": show_grid, "monochrome": monochrome,
        "show_legend": show_legend, "annotate": annotate, "label_col": label_col,
        "annotate_top_n": annotate_top_n, "figure_width": figure_width,
        "figure_height": figure_height, "font_size": font_size, "tick_size": tick_size,
        "spine_width": spine_width, "title_size": title_size,
    }


def _style_controls(
    plot_source: pd.DataFrame,
    group_col: str | None,
    recipe: dict,
    style_records: list[dict],
    project_id: int,
) -> dict:
    if not group_col or group_col not in plot_source.columns:
        return {}

    group_values = sorted(plot_source[group_col].astype("string").fillna("Без группы").replace("", "Без группы").unique().tolist())
    with st.expander("Маркеры и стили групп", expanded=False):
        profile_map = {
            f"{record['name']} · {record['grouping_column'] or 'без поля'}": record
            for record in style_records
            if not record["grouping_column"] or record["grouping_column"] == group_col
        }
        selected_profile = (
            st.selectbox("Готовый профиль", ["—"] + list(profile_map), key="style_profile_select")
            if profile_map else "—"
        )
        existing_style = (
            profile_map[selected_profile]["styles"]
            if profile_map and selected_profile != "—"
            else recipe.get("style_map", {})
        )
        editor = st.data_editor(
            style_dataframe(group_values, existing=existing_style),
            width="stretch",
            hide_index=True,
            column_config={
                "Маркер": st.column_config.SelectboxColumn("Маркер", options=MARKERS),
                "Размер ×": st.column_config.NumberColumn("Размер ×", min_value=0.2, max_value=5.0, step=0.1),
                "Alpha": st.column_config.NumberColumn("Alpha", min_value=0.1, max_value=1.0, step=0.05),
                "Заливка": st.column_config.CheckboxColumn("Заливка"),
            },
            key=f"style_editor_{group_col}",
        )
        styles = style_map(editor)
        p1, p2 = st.columns(2)
        profile_name = p1.text_input("Название профиля стилей", key="style_profile_name")
        project_profile = p2.checkbox("Сохранить как проектный профиль", value=True)
        if st.button("Сохранить профиль стилей", key="save_style_profile"):
            save_style_profile(
                profile_name or f"Профиль {group_col}",
                group_col,
                styles,
                project_id=project_id if project_profile else None,
            )
            st.success("Профиль стилей сохранён.")
            st.rerun()
        if selected_profile != "—" and st.button("Удалить выбранный профиль", key="delete_style_profile"):
            delete_style_profile(int(profile_map[selected_profile]["id"]))
            st.rerun()
        return styles


def _export_and_save(
    plot_dataframe: pd.DataFrame,
    excluded_dataframe: pd.DataFrame,
    *,
    project_id: int,
    selected_ids: list[int],
    selected_minerals: list[str],
    query: str,
    chosen_filters: dict[str, list[str]],
    outlier_config: dict,
    preset: str,
    x: str,
    y: str,
    group_col: str | None,
    appearance: dict,
    styles: dict,
) -> None:
    st.subheader("Публикационная фигура")
    figure = build_scatter(
        plot_dataframe,
        x,
        y,
        group_col,
        x_label=appearance["x_label"],
        y_label=appearance["y_label"],
        title=appearance["title"],
        marker_size=appearance["marker_size"],
        xlim=(appearance["x_min"], appearance["x_max"]),
        ylim=(appearance["y_min"], appearance["y_max"]),
        log_x=appearance["log_x"],
        log_y=appearance["log_y"],
        show_grid=appearance["show_grid"],
        style_map=styles,
        monochrome=appearance["monochrome"],
        show_legend=appearance["show_legend"],
        annotate=appearance["annotate"],
        label_col=appearance["label_col"],
        annotate_top_n=appearance["annotate_top_n"],
        figure_size=(appearance["figure_width"], appearance["figure_height"]),
        font_size=appearance["font_size"],
        tick_size=appearance["tick_size"],
        title_size=appearance["title_size"],
        spine_width=appearance["spine_width"],
    )
    st.pyplot(figure, width="content")
    png = figure_png_bytes(figure, dpi=600)
    svg = figure_svg_bytes(figure)
    plt.close(figure)

    d1, d2, d3 = st.columns(3)
    d1.download_button("PNG · 600 dpi", png, file_name="petrolab_plot.png", mime="image/png", width="stretch")
    d2.download_button("SVG", svg, file_name="petrolab_plot.svg", mime="image/svg+xml", width="stretch")
    excel = io.BytesIO()
    export_settings = {
        "journal_preset": preset,
        "x": x,
        "y": y,
        "group_col": group_col or "",
        **{key: value for key, value in appearance.items() if key != "label_col"},
        "label_col": appearance["label_col"] or "",
        "query": query,
        "column_filters": json.dumps(chosen_filters, ensure_ascii=False),
        "outlier_filters": json.dumps(outlier_config, ensure_ascii=False),
    }
    with pd.ExcelWriter(excel, engine="openpyxl") as writer:
        plot_dataframe.to_excel(writer, index=False, sheet_name="Точки графика")
        if not excluded_dataframe.empty:
            excluded_dataframe.to_excel(writer, index=False, sheet_name="Исключённые точки")
        pd.DataFrame([export_settings]).to_excel(writer, index=False, sheet_name="Настройки")
    d3.download_button(
        "Данные графика · Excel",
        excel.getvalue(),
        file_name="petrolab_plot_data.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        width="stretch",
    )

    current_recipe = {
        "dataset_ids": selected_ids,
        "minerals": selected_minerals,
        "query": query,
        "column_filters": chosen_filters,
        "outlier_filters": outlier_config,
        "journal_preset": preset,
        "x": x,
        "y": y,
        "group_col": group_col,
        **appearance,
        "style_map": styles,
    }
    with st.expander("Сохранить текущий рецепт графика", expanded=False):
        recipe_name = st.text_input("Название рецепта", key="save_recipe_name")
        project_recipe = st.checkbox("Сохранить как проектный рецепт", value=True)
        if st.button("Сохранить рецепт", key="save_recipe_button"):
            save_plot_recipe(
                recipe_name or f"{x} vs {y}",
                current_recipe,
                project_id=project_id if project_recipe else None,
            )
            st.success("Рецепт сохранён.")
            st.rerun()

    with st.expander("Таблица точек, вошедших в график", expanded=False):
        st.dataframe(plot_dataframe, width="stretch", hide_index=True, height=380)


def render_advanced_xy_workspace(project_id: int) -> None:
    """Render the full XY editor inside the dashboard without a nested page/scope shell."""
    render_plot_confirmations()
    recipe, style_records = _recipe_controls(project_id)
    if _stale_recipe_guard(project_id, recipe):
        return

    datasets = list_datasets(project_id)
    if not datasets:
        st.info("В активном проекте нет данных для графика.")
        return

    labels = {dataset_label(dataset): int(dataset["id"]) for dataset in datasets}
    wanted_ids = recipe.get("dataset_ids", list(labels.values()))
    defaults = [label for label, dataset_id in labels.items() if dataset_id in wanted_ids]
    selected_labels = st.multiselect(
        "Наборы",
        list(labels),
        default=defaults or ([] if recipe.get("dataset_ids") else list(labels)),
        key="plot_datasets",
    )
    selected_ids = [labels[label] for label in selected_labels]
    if not selected_ids:
        st.info("Выберите хотя бы один набор.")
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
        key="plot_minerals",
    )
    if not selected_minerals:
        st.info("Выберите хотя бы один минерал.")
        return
    dataframe = dataframe[dataframe["Минерал"].astype(str).isin(selected_minerals)]
    dataframe, query, chosen_filters = _filter_controls(dataframe, recipe)
    if dataframe.empty:
        st.info("После фильтрации не осталось строк.")
        return

    numeric = numeric_candidates(dataframe)
    if len(numeric) < 2:
        st.error("Недостаточно числовых колонок после фильтрации.")
        return

    preset_names = list(JOURNAL_PRESETS)
    preset_default = recipe.get("journal_preset", "Свой")
    if preset_default not in JOURNAL_PRESETS:
        preset_default = "Свой"
    preset = st.selectbox(
        "Шаблон графика",
        preset_names,
        index=preset_names.index(preset_default),
        key="journal_preset",
    )
    preset_cfg = JOURNAL_PRESETS[preset]

    categorical = [
        column
        for column in dataframe.columns
        if not str(column).startswith("_")
        and column not in numeric
        and dataframe[column].nunique(dropna=True) <= 80
    ]
    preferred_groups = [
        column for column in [WORK_GROUP_COLUMN, "Набор", "Минерал", "Источник", "Лист"]
        if column in categorical
    ]
    categorical = preferred_groups + [column for column in categorical if column not in preferred_groups]
    c1, c2, c3 = st.columns(3)
    x = c1.selectbox(
        "Ось X", numeric,
        index=numeric.index(recipe.get("x")) if recipe.get("x") in numeric else 0,
    )
    y = c2.selectbox(
        "Ось Y", numeric,
        index=numeric.index(recipe.get("y")) if recipe.get("y") in numeric else min(1, len(numeric) - 1),
    )
    group_options = ["Без группировки"] + categorical
    group_default = recipe.get("group_col") if recipe.get("group_col") in categorical else "Без группировки"
    group = c3.selectbox("Группировка", group_options, index=group_options.index(group_default))
    group_col = None if group == "Без группировки" else group

    finite = sanitize_xy_rows(dataframe, x, y, group_column=group_col)
    filtered, outlier_config, excluded = render_outlier_controls(finite, numeric, x, y, recipe)
    filtered, outlier_config, excluded = apply_interactive_exclusions(filtered, outlier_config, excluded)
    appearance = _appearance_controls(filtered, recipe, preset_cfg, x, y)
    plot_source = sanitize_xy_rows(
        filtered,
        x,
        y,
        log_x=appearance["log_x"],
        log_y=appearance["log_y"],
        group_column=group_col,
    )
    if plot_source.empty:
        st.info("После проверки выбранных логарифмических осей не осталось точек.")
        return
    removed_for_log = len(filtered) - len(plot_source)
    caption = f"В график входит {len(plot_source)} точек."
    if removed_for_log:
        caption += f" Для log-axis исключено неположительных значений: {removed_for_log}."
    st.caption(caption)

    styles = _style_controls(plot_source, group_col, recipe, style_records, project_id)
    render_advanced_interactive(
        plot_source,
        project_id,
        x,
        y,
        group_col,
        x_label=appearance["x_label"],
        y_label=appearance["y_label"],
        title=appearance["title"],
        log_x=appearance["log_x"],
        log_y=appearance["log_y"],
        styles=styles,
    )

    needed = [x, y] + ([group_col] if group_col else []) + ([appearance["label_col"]] if appearance["label_col"] else [])
    base_columns = [
        column
        for column in [
            "_analysis_id", "_dataset_id", "_source_row", "Проект", "Набор", "Минерал",
            "Источник", "Лист", "Sample", "Grain", "Point", "Generation", WORK_GROUP_COLUMN,
        ]
        if column in plot_source.columns
    ]
    plot_dataframe = plot_source[
        [column for column in dict.fromkeys(base_columns + needed) if column in plot_source.columns]
    ].copy()
    _export_and_save(
        plot_dataframe,
        excluded,
        project_id=project_id,
        selected_ids=selected_ids,
        selected_minerals=selected_minerals,
        query=query,
        chosen_filters=chosen_filters,
        outlier_config=outlier_config,
        preset=preset,
        x=x,
        y=y,
        group_col=group_col,
        appearance=appearance,
        styles=styles,
    )