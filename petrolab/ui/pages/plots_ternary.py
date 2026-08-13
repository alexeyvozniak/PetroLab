from __future__ import annotations

import io
import json

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

from petrolab.analysis_groups import WORK_GROUP_COLUMN, clear_work_group, list_work_groups, set_work_group
from petrolab.db import list_style_profiles, save_plot_recipe
from petrolab.interactive_plotting import selected_analysis_ids
from petrolab.io_utils import numeric_candidates
from petrolab.outliers import exclude_analysis_ids, robust_outliers
from petrolab.plotting import figure_png_bytes, figure_svg_bytes
from petrolab.ternary_data import (
    TERNARY_A,
    TERNARY_B,
    TERNARY_C,
    TERNARY_REASON,
    invalid_reason_counts,
    prepare_ternary,
)
from petrolab.ternary_overlays import attach_ternary_classification
from petrolab.ternary_plotting import build_interactive_ternary, build_publication_ternary
from petrolab.ui.components import collect_related_images, render_asset_gallery
from petrolab.ui.plot_style_controls import render_figure_style_controls
from petrolab.ui.ternary_controls import render_ternary_selection
from petrolab.visualization_presets import POINT_STYLE_PRESETS


_NORMALIZATION_LABELS = {
    "Авто": "auto",
    "Нормировать каждую строку к 100%": "normalize",
    "Считать значения уже согласованными": "already",
}


def _point_label(row: pd.Series) -> str:
    parts = [str(row.get(field, "")).strip() for field in ["Sample", "Grain", "Point"]]
    identity = " / ".join(value for value in parts if value) or "точка"
    return f"{identity} · {str(row.get('_analysis_id', ''))[:8]}"


def _render_selected_points(
    dataframe: pd.DataFrame,
    selected_ids: list[str],
    project_id: int | None,
    component_labels: tuple[str, str, str],
) -> None:
    if not selected_ids or dataframe.empty:
        return
    selected = dataframe[dataframe["_analysis_id"].astype(str).isin(selected_ids)].copy()
    if selected.empty:
        return

    a_label, b_label, c_label = component_labels
    summary_columns = [
        column
        for column in [
            "Sample",
            "Grain",
            "Point",
            "Generation",
            WORK_GROUP_COLUMN,
            "Классификационное поле",
            TERNARY_A,
            TERNARY_B,
            TERNARY_C,
            "Набор",
            "Источник",
            "_source_row",
        ]
        if column in selected.columns
    ]
    display = selected[summary_columns].copy()
    display = display.rename(columns={TERNARY_A: a_label, TERNARY_B: b_label, TERNARY_C: c_label})
    st.dataframe(display.head(1000), width="stretch", hide_index=True, height=230)

    point_map = {_point_label(row): str(row["_analysis_id"]) for _, row in selected.iterrows()}
    chosen = st.selectbox("Открыть выбранную точку", list(point_map), key="ternary_selected_point")
    row = selected[selected["_analysis_id"].astype(str) == point_map[chosen]].iloc[0]
    visible_columns = [column for column in dataframe.columns if not str(column).startswith("_")]
    properties = pd.DataFrame(
        {
            "Параметр": visible_columns,
            "Значение": ["" if pd.isna(row.get(column)) else str(row.get(column)) for column in visible_columns],
        }
    )
    left, right = st.columns([1.1, 1.0])
    with left:
        st.dataframe(properties, width="stretch", hide_index=True, height=420)
    with right:
        assets = collect_related_images(row, project_id=project_id)
        if assets:
            render_asset_gallery(assets, max_items=8, width=520)
        else:
            st.caption("Для этой точки пока нет связанных изображений.")


def _style_profile(group_col: str | None, project_id: int | None) -> dict:
    if not group_col:
        return {}
    records = [
        record
        for record in list_style_profiles(project_id)
        if not record["grouping_column"] or record["grouping_column"] == group_col
    ]
    if not records:
        return {}
    labels = {
        f"{record['name']} · {record['grouping_column'] or 'общий'}": record
        for record in records
    }
    chosen = st.selectbox("Сохранённый профиль маркеров", ["—"] + list(labels), key="ternary_style_profile")
    return {} if chosen == "—" else labels[chosen]["styles"]


def _preset_style_map(dataframe: pd.DataFrame, group_col: str | None, preset_name: str) -> dict[str, dict]:
    preset = POINT_STYLE_PRESETS[preset_name]
    if group_col and group_col in dataframe.columns:
        names = dataframe[group_col].fillna("—").astype(str).drop_duplicates().tolist()
    else:
        names = ["Все точки"]
    return {
        str(name): {
            "marker": preset.markers[index % len(preset.markers)],
            "alpha": preset.alpha,
            "size_multiplier": preset.size_multiplier,
            "filled": preset.filled,
        }
        for index, name in enumerate(names)
    }


def render_ternary_workspace(
    dataframe: pd.DataFrame,
    *,
    project_id: int | None,
    selected_dataset_ids: list[int],
    selected_minerals: list[str],
    query: str,
    column_filters: dict,
    recipe: dict,
) -> None:
    st.subheader("Треугольная диаграмма")
    try:
        selection = render_ternary_selection(dataframe, recipe)
    except ValueError as exc:
        st.error(str(exc))
        return

    dataframe = selection.dataframe
    mode = selection.mode
    preset_id = selection.preset_id
    a_col, b_col, c_col = selection.a_col, selection.b_col, selection.c_col
    a_label, b_label, c_label = selection.a_label, selection.b_label, selection.c_label
    classification_overlay = selection.overlay
    render_overlay = classification_overlay if selection.show_overlay else None

    normalization_default = recipe.get("ternary_normalization", "auto")
    reverse_norm = {value: label for label, value in _NORMALIZATION_LABELS.items()}
    norm_label = st.selectbox(
        "Нормировка",
        list(_NORMALIZATION_LABELS),
        index=list(_NORMALIZATION_LABELS).index(reverse_norm.get(normalization_default, "Авто")),
        key="ternary_normalization",
    )
    normalization = _NORMALIZATION_LABELS[norm_label]

    categorical = [
        column
        for column in dataframe.columns
        if not str(column).startswith("_")
        and dataframe[column].nunique(dropna=True) <= 80
        and column not in numeric_candidates(dataframe)
    ]
    preferred = [
        column
        for column in [WORK_GROUP_COLUMN, "Набор", "Generation", "Group", "Sample"]
        if column in categorical
    ]
    group_options = ["Без группировки"] + preferred + [
        column for column in categorical if column not in preferred
    ]
    saved_group = recipe.get("group_col") if recipe.get("group_col") in group_options else "Без группировки"
    group = st.selectbox(
        "Группировка",
        group_options,
        index=group_options.index(saved_group),
        key="ternary_group",
    )
    group_col = None if group == "Без группировки" else group

    style = render_figure_style_controls(dataframe, key_prefix="ternary_style")
    style_map = _preset_style_map(dataframe, group_col, style.point_style_name)
    saved_style = _style_profile(group_col, project_id)
    for name, overrides in saved_style.items():
        style_map.setdefault(str(name), {}).update(overrides)

    try:
        preparation = prepare_ternary(dataframe, a_col, b_col, c_col, normalization=normalization)
    except ValueError as exc:
        st.error(str(exc))
        return

    q1, q2, q3 = st.columns(3)
    q1.metric("Всего строк", preparation.total_rows)
    q2.metric("Вошло в ternary", preparation.valid_rows)
    q3.metric("Исключено QC", preparation.invalid_rows)
    if preparation.invalid_rows:
        with st.expander("Почему строки не вошли в диаграмму", expanded=False):
            st.dataframe(invalid_reason_counts(preparation), width="stretch", hide_index=True)
            preview = preparation.invalid.copy()
            columns = [
                column
                for column in ["Sample", "Grain", "Point", a_col, b_col, c_col, TERNARY_REASON]
                if column in preview.columns
            ]
            st.dataframe(preview[columns].head(300), width="stretch", hide_index=True, height=240)

    plot_data = preparation.valid.copy()
    if classification_overlay is not None:
        plot_data = attach_ternary_classification(plot_data, classification_overlay.overlay_id)
    if plot_data.empty:
        st.warning("После проверки не осталось валидных точек.")
        return

    with st.expander("Автоматическая проверка выбросов ternary", expanded=False):
        method_label = st.selectbox(
            "Метод",
            ["Нет", "MAD", "IQR"],
            index=["Нет", "MAD", "IQR"].index(str(recipe.get("ternary_outlier_method", "Нет"))),
            key="ternary_outlier_method",
        )
        threshold = 3.5 if method_label == "MAD" else 1.5
        flagged = pd.DataFrame()
        exclude_flagged = False
        if method_label != "Нет":
            threshold = st.number_input(
                "Порог" if method_label == "MAD" else "Множитель IQR",
                min_value=0.1,
                max_value=20.0,
                value=float(recipe.get("ternary_outlier_threshold", threshold)),
                step=0.1,
                key="ternary_outlier_threshold",
            )
            result = robust_outliers(
                plot_data,
                [TERNARY_A, TERNARY_B, TERNARY_C],
                method=method_label,
                threshold=float(threshold),
            )
            flagged = plot_data.loc[result.outlier_mask].copy()
            st.info(f"Статистически отмечено возможных выбросов: {len(flagged)}. Анализы не удаляются.")
            exclude_flagged = st.checkbox(
                "Исключить отмеченные точки только из этой диаграммы",
                value=bool(recipe.get("ternary_exclude_auto", False)),
                key="ternary_exclude_auto",
            )
            if not flagged.empty:
                columns = [
                    column
                    for column in [
                        "Sample",
                        "Grain",
                        "Point",
                        "Классификационное поле",
                        a_col,
                        b_col,
                        c_col,
                    ]
                    if column in flagged.columns
                ]
                st.dataframe(flagged[columns].head(300), width="stretch", hide_index=True, height=220)

    excluded = preparation.invalid.copy()
    if exclude_flagged and not flagged.empty:
        excluded = pd.concat([excluded, flagged], ignore_index=True, sort=False)
        plot_data = exclude_analysis_ids(plot_data, flagged["_analysis_id"].astype(str).tolist())

    interactive_ids = {str(value) for value in st.session_state.get("ternary_interactive_excluded_ids", [])}
    if interactive_ids:
        removed = plot_data[plot_data["_analysis_id"].astype(str).isin(interactive_ids)].copy()
        if not removed.empty:
            excluded = pd.concat([excluded, removed], ignore_index=True, sort=False)
        plot_data = exclude_analysis_ids(plot_data, sorted(interactive_ids))

    st.caption(
        f"Нормировка: {preparation.normalization_applied}. В рабочую диаграмму входит {len(plot_data)} точек."
    )
    if plot_data.empty:
        st.warning("После фильтрации не осталось точек.")
        return

    title = st.text_input("Заголовок", value=str(recipe.get("title", "")), key="ternary_title")
    interactive = build_interactive_ternary(
        plot_data,
        a_label=a_label,
        b_label=b_label,
        c_label=c_label,
        group_col=group_col,
        title=title,
        style_map=style_map,
        overlay=render_overlay,
    )
    st.markdown("#### Интерактивный отбор")
    st.caption("Кликните точку; выбор привязан к immutable `_analysis_id`. Для XY по-прежнему доступны box/lasso.")
    event = st.plotly_chart(
        interactive,
        width="stretch",
        theme=None,
        key="petrolab_interactive_ternary",
        on_select="rerun",
        selection_mode=("points",),
        config={"displaylogo": False, "scrollZoom": True},
    )
    selected_ids = selected_analysis_ids(event)
    if selected_ids:
        c1, c2 = st.columns(2)
        if c1.button(
            f"Исключить выбранные из этой ternary ({len(selected_ids)})",
            key="ternary_exclude_selected",
            type="primary",
            width="stretch",
        ):
            st.session_state.ternary_interactive_excluded_ids = sorted(interactive_ids | set(selected_ids))
            st.rerun()

        existing_groups = list_work_groups()
        group_choice = c2.selectbox(
            "Рабочая группа",
            ["Новая группа…"] + existing_groups,
            key="ternary_work_group_choice",
        )
        new_name = ""
        if group_choice == "Новая группа…":
            new_name = st.text_input("Название новой группы", key="ternary_new_group_name")
        target = new_name.strip() if group_choice == "Новая группа…" else group_choice
        g1, g2 = st.columns(2)
        if g1.button("Назначить группу", disabled=not target, key="ternary_assign_group", width="stretch"):
            changed = set_work_group(selected_ids, target)
            st.success(f"Рабочая группа назначена для {changed} точек.")
            st.rerun()
        if g2.button("Убрать рабочую группу", key="ternary_clear_group", width="stretch"):
            changed = clear_work_group(selected_ids)
            st.success(f"Рабочая группа очищена у {changed} точек.")
            st.rerun()
        _render_selected_points(plot_data, selected_ids, project_id, (a_label, b_label, c_label))

    if interactive_ids and st.button("Вернуть интерактивно исключённые ternary-точки", key="ternary_restore"):
        st.session_state.ternary_interactive_excluded_ids = []
        st.rerun()

    st.markdown("#### Публикационная фигура")
    annotate_top_n = 0
    if style.label_points and style.point_label_column:
        annotate_top_n = st.slider(
            "Сколько точек подписывать",
            1,
            1000,
            int(recipe.get("annotate_top_n", 25)),
            key="ternary_annotate_n",
        )

    figure = build_publication_ternary(
        plot_data,
        a_label=a_label,
        b_label=b_label,
        c_label=c_label,
        group_col=group_col,
        title=title,
        marker_size=style.marker_size,
        style_map=style_map,
        show_grid=style.grid,
        show_legend=style.show_legend,
        annotate=style.label_points,
        label_col=style.point_label_column,
        annotate_top_n=annotate_top_n,
        figure_size=(style.width_in, style.height_in),
        font_family=style.font_family,
        font_size=style.font_size,
        title_size=style.font_size + 1.0,
        line_width=style.line_width,
        monochrome=style.monochrome,
        overlay=render_overlay,
    )
    st.pyplot(figure, width="content")
    png = figure_png_bytes(figure, dpi=style.dpi)
    svg = figure_svg_bytes(figure)
    plt.close(figure)

    export_data = plot_data.copy()
    export_data = export_data.rename(
        columns={
            TERNARY_A: f"{a_label} [%]",
            TERNARY_B: f"{b_label} [%]",
            TERNARY_C: f"{c_label} [%]",
        }
    )
    settings = {
        "chart_type": "ternary",
        "ternary_mode": mode,
        "preset_id": preset_id,
        "a_col": a_col,
        "b_col": b_col,
        "c_col": c_col,
        "a_label": a_label,
        "b_label": b_label,
        "c_label": c_label,
        "normalization": normalization,
        "normalization_applied": preparation.normalization_applied,
        "group_col": group_col or "",
        "title": title,
        "classification_overlay_id": classification_overlay.overlay_id if classification_overlay else "",
        "show_classification_overlay": bool(selection.show_overlay),
        "classification_source": classification_overlay.source_citation if classification_overlay else "",
        "classification_doi": classification_overlay.source_doi if classification_overlay else "",
        "figure_preset": style.preset_name,
        "point_style_preset": style.point_style_name,
        "font_family": style.font_family,
        "font_size": style.font_size,
        "marker_size": style.marker_size,
        "monochrome": style.monochrome,
        "grid": style.grid,
        "dpi": style.dpi,
        "auto_outlier_method": method_label,
        "auto_outlier_threshold": threshold,
        "interactive_excluded_ids": json.dumps(sorted(interactive_ids), ensure_ascii=False),
    }
    excel = io.BytesIO()
    with pd.ExcelWriter(excel, engine="openpyxl") as writer:
        export_data.to_excel(writer, index=False, sheet_name="Точки ternary")
        if not excluded.empty:
            excluded.to_excel(writer, index=False, sheet_name="Исключённые точки")
        pd.DataFrame([settings]).to_excel(writer, index=False, sheet_name="Настройки")

    d1, d2, d3 = st.columns(3)
    d1.download_button(
        f"PNG · {style.dpi} dpi",
        png,
        file_name="petrolab_ternary.png",
        mime="image/png",
        width="stretch",
    )
    d2.download_button(
        "SVG",
        svg,
        file_name="petrolab_ternary.svg",
        mime="image/svg+xml",
        width="stretch",
    )
    d3.download_button(
        "Данные ternary · Excel",
        excel.getvalue(),
        file_name="petrolab_ternary_data.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        width="stretch",
    )

    current_recipe = {
        "chart_type": "Треугольная",
        "dataset_ids": selected_dataset_ids,
        "minerals": selected_minerals,
        "query": query,
        "column_filters": column_filters,
        "ternary_mode": mode,
        "ternary_preset_id": preset_id,
        "ternary_components": {
            "a": a_col,
            "b": b_col,
            "c": c_col,
            "a_label": a_label,
            "b_label": b_label,
            "c_label": c_label,
        },
        "ternary_normalization": normalization,
        "ternary_outlier_method": method_label,
        "ternary_outlier_threshold": threshold,
        "ternary_exclude_auto": exclude_flagged,
        "ternary_interactive_excluded_ids": sorted(interactive_ids),
        "show_classification_overlay": bool(selection.show_overlay),
        "classification_overlay_id": classification_overlay.overlay_id if classification_overlay else "",
        "group_col": group_col,
        "title": title,
        "figure_preset": style.preset_name,
        "point_style_preset": style.point_style_name,
        "font_family": style.font_family,
        "font_size": style.font_size,
        "marker_size": style.marker_size,
        "show_grid": style.grid,
        "show_legend": style.show_legend,
        "monochrome": style.monochrome,
        "dpi": style.dpi,
        "annotate": style.label_points,
        "label_col": style.point_label_column,
        "annotate_top_n": annotate_top_n,
    }
    with st.expander("Сохранить рецепт ternary", expanded=False):
        recipe_name = st.text_input("Название рецепта", key="ternary_recipe_name")
        project_recipe = st.checkbox(
            "Сохранить как проектный рецепт",
            value=project_id is not None,
            disabled=project_id is None,
            key="ternary_recipe_project",
        )
        if st.button("Сохранить рецепт ternary", key="ternary_save_recipe"):
            save_plot_recipe(
                recipe_name or f"{a_label}–{b_label}–{c_label}",
                current_recipe,
                project_id=project_id if project_recipe else None,
            )
            st.success("Рецепт ternary сохранён.")
            st.rerun()
