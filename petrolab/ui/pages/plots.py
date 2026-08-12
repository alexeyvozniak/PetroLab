from __future__ import annotations

import io
import json

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

from petrolab.dataframe_utils import apply_column_filters, apply_quick_filter, dataset_label, row_identity
from petrolab.db import (
    delete_plot_recipe,
    delete_style_profile,
    list_datasets,
    list_plot_recipes,
    list_style_profiles,
    save_plot_recipe,
    save_style_profile,
)
from petrolab.derived import load_unified_with_derived
from petrolab.io_utils import numeric_candidates
from petrolab.minerals.registry import MINERALS
from petrolab.outliers import apply_numeric_ranges, exclude_analysis_ids, robust_outliers
from petrolab.plot_presets import JOURNAL_PRESETS
from petrolab.plotting import MARKERS, build_scatter, figure_png_bytes, figure_svg_bytes
from petrolab.ui.components import collect_related_images, render_asset_gallery, render_project_selector


def _style_df_from_groups(groups: list[str], existing: dict | None = None) -> pd.DataFrame:
    existing = existing or {}
    rows = []
    for index, name in enumerate(groups):
        raw = existing.get(str(name), {})
        rows.append(
            {
                "Группа": str(name),
                "Маркер": raw.get("marker", MARKERS[index % len(MARKERS)]),
                "Размер ×": float(raw.get("size_multiplier", 1.0) or 1.0),
                "Alpha": float(raw.get("alpha", 0.9) or 0.9),
                "Заливка": bool(raw.get("filled", True)),
            }
        )
    return pd.DataFrame(rows)


def _style_map_from_df(dataframe: pd.DataFrame) -> dict:
    styles = {}
    for _, row in dataframe.iterrows():
        styles[str(row["Группа"])] = {
            "marker": row["Маркер"],
            "size_multiplier": float(row["Размер ×"]),
            "alpha": float(row["Alpha"]),
            "filled": bool(row["Заливка"]),
        }
    return styles


def _point_label(row: pd.Series) -> str:
    return (
        f"{row_identity(row)} · {row.get('Источник', '')} · "
        f"строка {row.get('_source_row', '—')} · {str(row.get('_analysis_id', ''))[:8]}"
    )


def _outlier_controls(
    dataframe: pd.DataFrame,
    numeric_columns: list[str],
    x: str,
    y: str,
    recipe: dict,
) -> tuple[pd.DataFrame, dict, pd.DataFrame]:
    """Render reversible numeric/outlier filters and return the plot view plus exclusions."""
    original = dataframe.copy()
    cfg = recipe.get("outlier_filters", {}) if isinstance(recipe.get("outlier_filters", {}), dict) else {}

    with st.expander("Диапазоны и выбросы", expanded=False):
        st.caption(
            "Эти фильтры действуют только на текущий график. Они не удаляют анализы из базы "
            "и никогда не записываются в исходный Excel."
        )
        saved_ranges = cfg.get("ranges", {}) if isinstance(cfg.get("ranges", {}), dict) else {}
        range_columns = st.multiselect(
            "Ограничить числовые колонки вручную",
            numeric_columns,
            default=[column for column in saved_ranges if column in numeric_columns],
            key="plot_range_columns",
        )
        ranges: dict[str, tuple[float | None, float | None]] = {}
        for column in range_columns:
            values = pd.to_numeric(dataframe[column], errors="coerce").dropna()
            if values.empty:
                continue
            observed_min = float(values.min())
            observed_max = float(values.max())
            saved = saved_ranges.get(column, [observed_min, observed_max])
            c1, c2 = st.columns(2)
            low = c1.number_input(
                f"{column}: минимум",
                value=float(saved[0]) if saved and saved[0] is not None else observed_min,
                key=f"range_low_{column}",
            )
            high = c2.number_input(
                f"{column}: максимум",
                value=float(saved[1]) if len(saved) > 1 and saved[1] is not None else observed_max,
                key=f"range_high_{column}",
            )
            if low > high:
                st.error(f"{column}: минимум больше максимума")
            else:
                ranges[column] = (float(low), float(high))

        ranged = apply_numeric_ranges(dataframe, ranges) if ranges else dataframe
        st.caption(f"После ручных диапазонов: {len(ranged)} из {len(dataframe)} точек.")

        auto_options = {
            "Нет": "NONE",
            "MAD — робастный modified z-score": "MAD",
            "IQR — правило Тьюки": "IQR",
        }
        reverse = {value: label for label, value in auto_options.items()}
        saved_method = str(cfg.get("auto_method", "NONE")).upper()
        auto_label = st.selectbox(
            "Автоматически искать выбросы",
            list(auto_options),
            index=list(auto_options).index(reverse.get(saved_method, "Нет")),
            key="outlier_method",
        )
        auto_method = auto_options[auto_label]
        auto_columns: list[str] = []
        threshold = 0.0
        outlier_ids: list[str] = []
        flagged = pd.DataFrame()
        exclude_auto = bool(cfg.get("exclude_auto", False))

        if auto_method != "NONE":
            saved_auto_columns = cfg.get("auto_columns", [x, y])
            auto_columns = st.multiselect(
                "Колонки для автоматической проверки",
                numeric_columns,
                default=[column for column in saved_auto_columns if column in numeric_columns] or [x, y],
                key="outlier_columns",
            )
            default_threshold = float(cfg.get("threshold", 3.5 if auto_method == "MAD" else 1.5))
            threshold = st.number_input(
                "Порог MAD" if auto_method == "MAD" else "Множитель IQR",
                min_value=0.1,
                max_value=20.0,
                value=default_threshold,
                step=0.1,
                key="outlier_threshold",
            )
            result = robust_outliers(ranged, auto_columns, method=auto_method, threshold=float(threshold))
            flagged = ranged.loc[result.outlier_mask].copy()
            if "_analysis_id" in flagged.columns:
                outlier_ids = flagged["_analysis_id"].astype(str).tolist()
            st.info(
                f"Автоматически отмечено как возможные выбросы: {len(flagged)}. "
                "Это только статистическая подсказка, а не решение об удалении данных."
            )
            if not flagged.empty:
                preview_columns = [
                    column for column in ["Sample", "Grain", "Point", "Generation", *auto_columns]
                    if column in flagged.columns
                ]
                st.dataframe(flagged[preview_columns].head(200), width="stretch", hide_index=True, height=260)
            exclude_auto = st.checkbox(
                "Исключить автоматически отмеченные точки из этого графика",
                value=exclude_auto,
                key="exclude_auto_outliers",
            )

        candidate_map = {
            _point_label(row): str(row["_analysis_id"])
            for _, row in ranged.head(3000).iterrows()
            if "_analysis_id" in ranged.columns
        }
        saved_manual = {str(value) for value in cfg.get("manual_excluded_ids", [])}
        default_labels = [label for label, analysis_id in candidate_map.items() if analysis_id in saved_manual]
        manual_labels = st.multiselect(
            "Исключить отдельные точки вручную",
            list(candidate_map),
            default=default_labels,
            key="manual_outlier_exclusions",
        ) if candidate_map else []
        manual_ids = [candidate_map[label] for label in manual_labels]

    filtered = ranged
    excluded_ids = set(manual_ids)
    if exclude_auto:
        excluded_ids.update(outlier_ids)
    if excluded_ids:
        filtered = exclude_analysis_ids(filtered, tuple(excluded_ids))

    before_ids = set(original.get("_analysis_id", pd.Series(dtype=str)).astype(str))
    after_ids = set(filtered.get("_analysis_id", pd.Series(dtype=str)).astype(str))
    removed = original[original["_analysis_id"].astype(str).isin(before_ids - after_ids)].copy() if "_analysis_id" in original.columns else pd.DataFrame()

    config = {
        "ranges": {column: [bounds[0], bounds[1]] for column, bounds in ranges.items()},
        "auto_method": auto_method,
        "auto_columns": auto_columns,
        "threshold": threshold,
        "exclude_auto": exclude_auto,
        "manual_excluded_ids": manual_ids,
    }
    return filtered, config, removed


def render_plots_page() -> None:
    st.title("Диаграммы")
    st.write(
        "Исходные и сохранённые расчётные величины доступны в одном списке осей. "
        "Фильтрация выбросов обратима и относится только к текущему графику."
    )

    scope = st.radio("Область данных", ["Один проект", "Все проекты"], horizontal=True, key="plot_scope")
    project_id = None
    if scope == "Один проект":
        current_project = render_project_selector("plot_project")
        if current_project is None:
            return
        project_id = int(current_project["id"])

    datasets = list_datasets(project_id)
    if not datasets:
        st.info("Нет данных для построения графика.")
        return

    recipe_records = list_plot_recipes(project_id)
    style_records = list_style_profiles(project_id)
    with st.expander("Сохранённые рецепты графиков", expanded=False):
        if recipe_records:
            recipe_map = {
                f"{record['name']} · {('общий' if record['project_id'] is None else 'проект')}": record
                for record in recipe_records
            }
            chosen_label = st.selectbox("Загрузить рецепт", ["—"] + list(recipe_map), key="recipe_select")
            c_load, c_delete = st.columns(2)
            if chosen_label != "—":
                chosen = recipe_map[chosen_label]
                if c_load.button("Применить рецепт", key="load_recipe_btn"):
                    st.session_state.loaded_recipe = chosen["config"]
                    st.rerun()
                if c_delete.button("Удалить рецепт", key="delete_recipe_btn"):
                    delete_plot_recipe(int(chosen["id"]))
                    st.success("Рецепт удалён.")
                    st.rerun()
        else:
            st.caption("Сохранённых рецептов пока нет.")
        if st.button("Сбросить применённый рецепт", key="reset_recipe_btn"):
            st.session_state.loaded_recipe = None
            st.rerun()

    recipe = st.session_state.get("loaded_recipe") or {}
    dataset_labels = {dataset_label(dataset): int(dataset["id"]) for dataset in datasets}
    wanted_ids = recipe.get("dataset_ids", list(dataset_labels.values()))
    defaults = [label for label, dataset_id in dataset_labels.items() if dataset_id in wanted_ids]
    selected_labels = st.multiselect(
        "Наборы для графика", list(dataset_labels), default=defaults or list(dataset_labels), key="plot_datasets"
    )
    selected_ids = [dataset_labels[label] for label in selected_labels]
    if not selected_ids:
        return

    dataframe = load_unified_with_derived(project_id, selected_ids)
    if dataframe.empty:
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
    if selected_minerals:
        dataframe = dataframe[dataframe["Минерал"].astype(str).isin(selected_minerals)]

    query = st.text_input("Быстрый поиск", value=recipe.get("query", ""), key="plot_search")
    dataframe = apply_quick_filter(dataframe, query)

    with st.expander("Фильтры по группам и категориям", expanded=False):
        candidates = [
            column for column in dataframe.columns
            if not str(column).startswith("_") and dataframe[column].nunique(dropna=True) <= 100
        ]
        preferred = [
            column for column in [
                "Проект", "Набор", "Минерал", "Источник", "Лист", "Generation", "Group", "Type", "Sample", "Grain"
            ] if column in candidates
        ]
        choices = st.multiselect(
            "Колонки для фильтрации",
            preferred + [column for column in candidates if column not in preferred],
            default=[column for column in recipe.get("column_filters", {}) if column in candidates],
            key="column_filter_columns",
        )
        chosen_filters = {}
        for column in choices:
            values = sorted(dataframe[column].dropna().astype(str).unique().tolist())
            defaults = [value for value in recipe.get("column_filters", {}).get(column, []) if value in values]
            chosen_filters[column] = st.multiselect(
                column, values, default=defaults, key=f"filter_vals_{column}"
            )
        if chosen_filters:
            dataframe = apply_column_filters(dataframe, chosen_filters)

    numeric = numeric_candidates(dataframe)
    if len(numeric) < 2:
        st.error("Недостаточно числовых колонок после фильтрации.")
        return

    preset_names = list(JOURNAL_PRESETS)
    preset_default = recipe.get("journal_preset", "Свой")
    if preset_default not in JOURNAL_PRESETS:
        preset_default = "Свой"
    preset = st.selectbox(
        "Шаблон графика", preset_names, index=preset_names.index(preset_default), key="journal_preset"
    )
    preset_cfg = JOURNAL_PRESETS[preset]

    categorical = [
        column for column in dataframe.columns
        if not str(column).startswith("_")
        and column not in numeric
        and dataframe[column].nunique(dropna=True) <= 80
    ]
    preferred_groups = [column for column in ["Набор", "Минерал", "Источник", "Лист"] if column in dataframe.columns]
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

    plot_source = dataframe.copy()
    plot_source[x] = pd.to_numeric(plot_source[x], errors="coerce")
    plot_source[y] = pd.to_numeric(plot_source[y], errors="coerce")
    plot_source = plot_source.dropna(subset=[x, y])
    plot_source, outlier_config, excluded_dataframe = _outlier_controls(
        plot_source, numeric, x, y, recipe
    )
    st.caption(f"В график войдёт {len(plot_source)} точек.")

    c4, c5, c6, c7 = st.columns(4)
    x_label = c4.text_input("Подпись X", value=recipe.get("x_label", x))
    y_label = c5.text_input("Подпись Y", value=recipe.get("y_label", y))
    marker_size = c6.slider(
        "Размер маркеров", 10, 180, int(recipe.get("marker_size", preset_cfg["marker_size"])), 2
    )
    title = c7.text_input("Заголовок", value=recipe.get("title", ""))

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
            column for column in plot_source.columns
            if not str(column).startswith("_") and plot_source[column].nunique(dropna=True) <= max(200, len(plot_source))
        ]
        label_default = recipe.get("label_col")
        label_col_choice = d3.selectbox(
            "Поле для подписи", ["—"] + label_candidates,
            index=1 + label_candidates.index(label_default) if label_default in label_candidates else 0,
        )
        label_col = None if label_col_choice == "—" else label_col_choice
        annotate_top_n = (
            st.slider("Сколько точек подписывать", 1, 1000, int(recipe.get("annotate_top_n", 25)))
            if annotate and label_col else 0
        )
        e1, e2, e3, e4 = st.columns(4)
        figure_width = e1.number_input(
            "Ширина фигуры", min_value=3.0, max_value=20.0,
            value=float(recipe.get("figure_width", preset_cfg["figure_width"])), step=0.1,
        )
        figure_height = e2.number_input(
            "Высота фигуры", min_value=3.0, max_value=20.0,
            value=float(recipe.get("figure_height", preset_cfg["figure_height"])), step=0.1,
        )
        font_size = e3.number_input(
            "Размер шрифта", min_value=6.0, max_value=24.0,
            value=float(recipe.get("font_size", preset_cfg["font_size"])), step=0.5,
        )
        tick_size = e4.number_input(
            "Размер подписей делений", min_value=6.0, max_value=24.0,
            value=float(recipe.get("tick_size", preset_cfg["tick_size"])), step=0.5,
        )
        f1, f2 = st.columns(2)
        spine_width = f1.number_input(
            "Толщина осей", min_value=0.5, max_value=3.0,
            value=float(recipe.get("spine_width", preset_cfg["spine_width"])), step=0.1,
        )
        title_size = f2.number_input(
            "Размер заголовка", min_value=6.0, max_value=28.0,
            value=float(recipe.get("title_size", float(recipe.get("font_size", preset_cfg["font_size"])) + 1.0)), step=0.5,
        )

    style_map = {}
    if group_col and group_col in plot_source.columns:
        group_values = sorted(plot_source[group_col].dropna().astype(str).unique().tolist())
        with st.expander("Профили маркеров по группам", expanded=False):
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
                _style_df_from_groups(group_values, existing=existing_style),
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
            style_map = _style_map_from_df(editor)
            p1, p2 = st.columns(2)
            profile_name = p1.text_input("Название профиля стилей", key="style_profile_name")
            project_profile = p2.checkbox(
                "Сохранить как проектный профиль",
                value=project_id is not None,
                disabled=project_id is None,
            )
            if st.button("Сохранить профиль стилей", key="save_style_profile"):
                save_style_profile(
                    profile_name or f"Профиль {group_col}", group_col, style_map,
                    project_id=project_id if project_profile else None,
                )
                st.success("Профиль стилей сохранён.")
                st.rerun()
            if selected_profile != "—" and st.button("Удалить выбранный профиль", key="delete_style_profile"):
                delete_style_profile(int(profile_map[selected_profile]["id"]))
                st.rerun()

    needed = [x, y] + ([group_col] if group_col else []) + ([label_col] if label_col else [])
    base_columns = [
        column for column in [
            "_analysis_id", "_dataset_id", "_source_row", "Проект", "Набор", "Минерал", "Источник", "Лист",
            "Sample", "Grain", "Point", "Generation",
        ] if column in plot_source.columns
    ]
    plot_dataframe = plot_source[[column for column in dict.fromkeys(base_columns + needed) if column in plot_source.columns]].copy()

    figure = build_scatter(
        plot_dataframe, x, y, group_col,
        x_label=x_label, y_label=y_label, title=title, marker_size=marker_size,
        xlim=(x_min, x_max), ylim=(y_min, y_max), log_x=log_x, log_y=log_y,
        show_grid=show_grid, style_map=style_map, monochrome=monochrome,
        show_legend=show_legend, annotate=annotate, label_col=label_col,
        annotate_top_n=annotate_top_n, figure_size=(figure_width, figure_height),
        font_size=font_size, tick_size=tick_size, title_size=title_size, spine_width=spine_width,
    )
    st.pyplot(figure, width="content")
    png = figure_png_bytes(figure, dpi=600)
    svg = figure_svg_bytes(figure)
    plt.close(figure)

    d1, d2, d3 = st.columns(3)
    d1.download_button("PNG · 600 dpi", png, file_name="petrolab_plot.png", mime="image/png", width="stretch")
    d2.download_button("SVG", svg, file_name="petrolab_plot.svg", mime="image/svg+xml", width="stretch")
    plot_excel = io.BytesIO()
    settings = {
        "journal_preset": preset,
        "x": x,
        "y": y,
        "group_col": group_col or "",
        "x_label": x_label,
        "y_label": y_label,
        "title": title,
        "marker_size": marker_size,
        "x_min": x_min,
        "x_max": x_max,
        "y_min": y_min,
        "y_max": y_max,
        "log_x": log_x,
        "log_y": log_y,
        "show_grid": show_grid,
        "monochrome": monochrome,
        "show_legend": show_legend,
        "annotate": annotate,
        "label_col": label_col or "",
        "annotate_top_n": annotate_top_n,
        "figure_width": figure_width,
        "figure_height": figure_height,
        "font_size": font_size,
        "tick_size": tick_size,
        "spine_width": spine_width,
        "title_size": title_size,
        "query": query,
        "column_filters": json.dumps(chosen_filters, ensure_ascii=False),
        "outlier_filters": json.dumps(outlier_config, ensure_ascii=False),
    }
    with pd.ExcelWriter(plot_excel, engine="openpyxl") as writer:
        plot_dataframe.to_excel(writer, index=False, sheet_name="Точки графика")
        if not excluded_dataframe.empty:
            excluded_dataframe.to_excel(writer, index=False, sheet_name="Исключённые точки")
        pd.DataFrame([settings]).to_excel(writer, index=False, sheet_name="Настройки")
    d3.download_button(
        "Данные графика · Excel", plot_excel.getvalue(), file_name="petrolab_plot_data.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", width="stretch",
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
        "x_label": x_label,
        "y_label": y_label,
        "title": title,
        "marker_size": marker_size,
        "x_min": x_min,
        "x_max": x_max,
        "y_min": y_min,
        "y_max": y_max,
        "log_x": log_x,
        "log_y": log_y,
        "show_grid": show_grid,
        "monochrome": monochrome,
        "show_legend": show_legend,
        "annotate": annotate,
        "label_col": label_col,
        "annotate_top_n": annotate_top_n,
        "figure_width": figure_width,
        "figure_height": figure_height,
        "font_size": font_size,
        "tick_size": tick_size,
        "spine_width": spine_width,
        "title_size": title_size,
        "style_map": style_map,
    }
    with st.expander("Сохранить текущий рецепт графика", expanded=False):
        recipe_name = st.text_input("Название рецепта", key="save_recipe_name")
        recipe_project = st.checkbox(
            "Сохранить как проектный рецепт", value=project_id is not None, disabled=project_id is None
        )
        if st.button("Сохранить рецепт", key="save_recipe_button"):
            save_plot_recipe(
                recipe_name or f"{x} vs {y}", current_recipe,
                project_id=project_id if recipe_project else None,
            )
            st.success("Рецепт сохранён.")
            st.rerun()

    st.subheader("Точки, вошедшие в график")
    st.dataframe(plot_dataframe, width="stretch", hide_index=True, height=350)
    if not plot_dataframe.empty:
        point_map = {
            _point_label(row): str(row["_analysis_id"])
            for _, row in plot_dataframe.head(3000).iterrows()
        }
        chosen_point = st.selectbox("Открыть точку с графика", list(point_map), key="plot_point_select")
        selected_row = plot_dataframe[
            plot_dataframe["_analysis_id"].astype(str) == point_map[chosen_point]
        ].iloc[0]
        render_asset_gallery(
            collect_related_images(selected_row, project_id=project_id), max_items=10, width=650
        )
