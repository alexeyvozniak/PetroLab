from __future__ import annotations

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

from petrolab.analysis_groups import WORK_GROUP_COLUMN, attach_work_groups
from petrolab.dataframe_utils import apply_quick_filter, dataset_label
from petrolab.dataset_visibility import visible_working_datasets
from petrolab.db import list_accessible_datasets
from petrolab.derived import load_unified_with_derived
from petrolab.io_utils import numeric_candidates
from petrolab.minerals.registry import MINERALS
from petrolab.plotting import build_scatter, figure_png_bytes, figure_svg_bytes
from petrolab.publication_manifest import build_selection_manifest, manifest_json_bytes, workbook_with_manifest
from petrolab.settings_service import load_settings
from petrolab.source_registry import SOURCE_LABEL_COLUMN, attach_study_metadata
from petrolab.ui.layout import render_badges, render_page_header
from petrolab.ui.navigation import navigate
from petrolab.ui.pages.plots_advanced import render_advanced_xy_workspace
from petrolab.ui.plot_manager import render_series_manager
from petrolab.ui.plot_spec import PlotSpec, send_to_multi_panel, set_current_plot_spec
from petrolab.ui.project_context import active_project_id
from petrolab.ui.smart_plot_start import (
    advanced_recipe_from_spec,
    choose_xy_recommendation,
    clear_exact_plot_scope,
    consume_plot_scope,
    seed_xy_state,
)
from petrolab.ui.source_controls import render_source_visibility_controls
from petrolab.ui.work_context import filter_dataframe_to_context, get_work_context
from petrolab.ui.xy_components import (
    render_quick_interactive,
    sanitize_xy_rows,
    style_dataframe,
    style_map,
)
from petrolab.visualization_presets import FIGURE_PRESETS


_CURATED_GROUPS = (
    "PetroLab Generation", "Generation", WORK_GROUP_COLUMN, "Sample", "Grain", "Textural zone",
    SOURCE_LABEL_COLUMN, "Источник", "Набор", "Минерал",
)


def _group_control(dataframe: pd.DataFrame, numeric: list[str], visible_sources: list[str]) -> str | None:
    categorical = [
        column for column in dataframe.columns
        if not str(column).startswith("_")
        and column not in numeric
        and dataframe[column].nunique(dropna=True) <= 80
    ]
    curated = [column for column in _CURATED_GROUPS if column in categorical]
    options = ["Без группировки", *curated]
    if any(column not in curated for column in categorical):
        options.append("Другой столбец…")
    suggested = SOURCE_LABEL_COLUMN if len(visible_sources) > 1 and SOURCE_LABEL_COLUMN in curated else "Без группировки"
    if st.session_state.get("quick_group") not in options:
        st.session_state.pop("quick_group", None)
    group = st.selectbox(
        "Группа",
        options,
        index=options.index(suggested),
        key="quick_group",
        help="Основные научные сущности показаны сразу; технические и редкие колонки спрятаны в «Другой столбец…».",
    )
    if group == "Другой столбец…":
        advanced = [column for column in categorical if column not in curated]
        group = st.selectbox("Другой столбец", advanced, key="quick_group_advanced") if advanced else "Без группировки"
    return None if group == "Без группировки" else str(group)


def _quick_workspace(project_id: int) -> None:
    datasets = visible_working_datasets(list_accessible_datasets(project_id))
    if not datasets:
        st.info("В активном проекте нет данных для графика.")
        return
    labels = {dataset_label(item): int(item["id"]) for item in datasets}

    work_context = get_work_context(project_id)
    scope = consume_plot_scope(
        st.session_state,
        project_id=project_id,
        available_dataset_ids=labels.values(),
        work_context=work_context,
    )
    had_explicit_scope = scope.explicit or bool((work_context or {}).get("dataset_ids"))
    if had_explicit_scope and not scope.dataset_ids:
        st.warning(
            "Текущий контекст графика ссылается на наборы, которых больше нет в проекте. "
            "PetroLab не расширяет такой контекст автоматически до всей базы."
        )
        return

    requested_labels = [label for label, dataset_id in labels.items() if dataset_id in scope.dataset_ids]
    default_labels = requested_labels or list(labels)
    scope_signature = (scope.dataset_ids, scope.analysis_ids, scope.context_label)
    if st.session_state.get("_quick_plot_scope_signature") != scope_signature:
        st.session_state["_quick_plot_scope_signature"] = scope_signature
        st.session_state["quick_plot_datasets"] = default_labels
        for key in (
            "quick_plot_minerals", "quick_x", "quick_y", "quick_group", "quick_group_advanced",
            "quick_plot_search",
        ):
            st.session_state.pop(key, None)

    notice = st.session_state.pop("workflow_plot_notice", "")
    if notice:
        st.success(notice)
    if scope.context_label:
        st.caption(f"Текущий контекст: **{scope.context_label}**. Данные не нужно выбирать заново.")

    settings = load_settings()
    preset_name = str(settings.get("default_figure_preset", "Lithos"))
    preset = FIGURE_PRESETS.get(preset_name, FIGURE_PRESETS["Lithos"])

    left, right = st.columns([1, 2.2], gap="large")
    with left:
        st.markdown("### Данные")
        selected_labels = st.multiselect(
            "Наборы", list(labels), default=default_labels, key="quick_plot_datasets"
        )
        selected_ids = [labels[label] for label in selected_labels]
        if not selected_ids:
            st.info("Выберите хотя бы один набор.")
            return
        dataframe = attach_study_metadata(
            attach_work_groups(load_unified_with_derived(project_id, selected_ids))
        )
        if scope.analysis_ids:
            dataframe = dataframe[dataframe["_analysis_id"].astype(str).isin(set(scope.analysis_ids))].copy()
            exact_text, exact_action = st.columns([3.2, 1])
            exact_text.caption(f"Точный переданный поднабор: {len(dataframe)} точек до QC-проверки.")
            if exact_action.button(
                "Весь набор",
                width="stretch",
                key="quick_plot_release_exact_scope",
                help="Явно снять точный analysis_id-отбор и перейти ко всем точкам выбранных наборов.",
            ):
                clear_exact_plot_scope(st.session_state)
                st.rerun()
        elif not scope.explicit and work_context:
            before_context = len(dataframe)
            dataframe = filter_dataframe_to_context(dataframe, work_context)
            if len(dataframe) != before_context:
                st.caption(f"Рабочий контекст оставил {len(dataframe)} из {before_context} аналитических строк.")
        if dataframe.empty:
            st.info("В текущем рабочем контексте нет аналитических строк.")
            return

        if "QC решение" in dataframe.columns:
            excluded = dataframe["QC решение"].astype(str).str.casefold().eq("исключить")
            if excluded.any():
                dataframe = dataframe.loc[~excluded].copy()
                st.caption(f"Скрыто по ручному решению QC: {int(excluded.sum())}.")
        if "QC уровень" in dataframe.columns:
            review_count = int(dataframe["QC уровень"].astype(str).eq("Требует проверки").sum())
            blocked_count = int(dataframe["QC уровень"].astype(str).eq("Исключить по умолчанию").sum())
            auto = dataframe.get("QC решение", pd.Series("Авто", index=dataframe.index)).astype(str).str.casefold().eq("авто")
            auto_blocked = dataframe["QC уровень"].astype(str).eq("Исключить по умолчанию") & auto
            if auto_blocked.any():
                dataframe = dataframe.loc[~auto_blocked].copy()
            if review_count or blocked_count:
                st.warning(
                    f"QC в текущем отборе: требуют проверки — {review_count}; "
                    f"исключены по автоматическому правилу — {int(auto_blocked.sum())}. "
                    "Поставьте «Включить» в QC решении, если точка должна попасть на график вопреки предупреждению."
                )
        if dataframe.empty:
            st.info("После QC-проверки в текущем контексте не осталось точек для графика.")
            return

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
            "Поиск", placeholder="Образец, поколение, статья, группа…", key="quick_plot_search"
        )
        dataframe = apply_quick_filter(dataframe, query)
        dataframe, _source_excluded, visible_sources, hidden_sources = render_source_visibility_controls(
            dataframe,
            key="quick_plot",
        )
        if dataframe.empty:
            st.info("Включите хотя бы один источник, чтобы построить график.")
            return
        numeric = numeric_candidates(dataframe)
        if len(numeric) < 2:
            st.info("После фильтрации недостаточно числовых колонок.")
            return

        recommendation = choose_xy_recommendation(selected_minerals, dataframe.columns, numeric)
        seed_xy_state(
            st.session_state,
            numeric_columns=numeric,
            recommendation=recommendation,
        )
        if recommendation is not None:
            st.caption(f"Smart Start · **{recommendation.title}** — {recommendation.note}")
        x = st.selectbox("X", numeric, key="quick_x")
        y_options = [column for column in numeric if column != x]
        if st.session_state.get("quick_y") not in y_options:
            st.session_state["quick_y"] = (
                recommendation.y
                if recommendation is not None and recommendation.y in y_options
                else y_options[0]
            )
        y = st.selectbox("Y", y_options, key="quick_y")
        group_col = _group_control(dataframe, numeric, visible_sources)
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

        plot_source, managed_series = render_series_manager(
            plot_source,
            group_col,
            key_prefix="quick_plot",
        )
        if plot_source.empty:
            return
        if group_col:
            names = list(managed_series) or plot_source[group_col].astype(str).unique().tolist()
        else:
            names = ["Все точки"]
        styles = style_map(style_dataframe([str(value) for value in names]))
        render_badges([
            (f"{len(plot_source):,} точек".replace(",", " "), "accent"),
            (f"{len(names)} групп", "neutral"),
        ])

    spec = PlotSpec(
        dataset_ids=tuple(selected_ids),
        analysis_ids=tuple(plot_source["_analysis_id"].astype(str).tolist()) if "_analysis_id" in plot_source.columns else (),
        x=x,
        y=y,
        group_column=group_col or "",
        x_label=x,
        y_label=y,
        title=title,
        log_x=bool(log_x),
        log_y=bool(log_y),
        visible_sources=tuple(str(value) for value in visible_sources),
        hidden_sources=tuple(str(value) for value in hidden_sources),
        visible_series=tuple(str(value) for value in managed_series),
        style_map=styles,
        marker_size=float(marker_size),
        figure_preset=preset_name,
        show_grid=bool(preset.grid),
    )
    set_current_plot_spec(spec)

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
            project_id=project_id,
        )
        multi_col, deep_col = st.columns(2)
        if multi_col.button(
            "＋ Добавить диаграмму",
            type="primary",
            width="stretch",
            key="quick_send_to_multi",
            help="Открыть тот же PlotSpec рядом с дополнительными связанными диаграммами.",
        ):
            send_to_multi_panel(spec)
            navigate("multi_panel")
            st.rerun()
        if deep_col.button(
            "Настроить подробнее",
            width="stretch",
            key="quick_open_advanced",
            help="Открыть глубокие настройки этого же графика без повторного выбора данных и осей.",
        ):
            st.session_state["loaded_recipe"] = advanced_recipe_from_spec(
                spec,
                minerals=selected_minerals,
                query=query,
            )
            st.session_state["_plots_show_advanced"] = True
            st.rerun()

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
    manifest = build_selection_manifest(
        kind="xy_figure",
        dataframe=plot_source,
        dataset_ids=selected_ids,
        filters={
            "database_selection": scope.context,
            "minerals": selected_minerals,
            "search": query,
            "visible_sources": visible_sources,
            "hidden_sources": hidden_sources,
            "visible_series": list(managed_series),
            "qc_policy": "manual exclude and automatic QC exclusions omitted",
        },
        recipe={
            "x": x, "y": y, "group_column": group_col or "", "log_x": log_x,
            "log_y": log_y, "title": title, "marker_size": marker_size,
            "figure_preset": preset_name, "style_map": styles,
            "source_visibility_column": SOURCE_LABEL_COLUMN,
        },
    )
    xlsx = workbook_with_manifest({"Точки графика": plot_source}, manifest)
    e1, e2, e3, e4 = st.columns(4)
    e1.download_button(
        "SVG", figure_svg_bytes(figure), file_name="petrolab_xy.svg",
        mime="image/svg+xml", width="stretch"
    )
    e2.download_button(
        "PNG", figure_png_bytes(figure, preset.dpi), file_name="petrolab_xy.png",
        mime="image/png", width="stretch"
    )
    e3.download_button(
        "XLSX + manifest", xlsx, file_name="petrolab_xy_data.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", width="stretch",
    )
    e4.download_button(
        "JSON manifest", manifest_json_bytes(manifest), file_name="petrolab_xy_manifest.json",
        mime="application/json", width="stretch",
    )
    st.caption(
        f"{preset.title} · {preset.font_family} · {preset.dpi} dpi · "
        f"{preset.width_in:g} × {preset.height_in:g} in"
    )
    plt.close(figure)


def render_plots_dashboard_page() -> None:
    render_page_header(
        "XY-диаграммы",
        "PetroLab показывает научно разумный первый график из текущего контекста, а глубина раскрывается по мере необходимости.",
        eyebrow="Исследование",
    )
    project_id = active_project_id()
    if project_id is None:
        st.info("Сначала создайте проект.")
        return

    if st.session_state.get("_plots_show_advanced"):
        back_col, text_col = st.columns([1, 4])
        if back_col.button("← К обычному графику", width="stretch", key="plots_back_from_advanced"):
            st.session_state.pop("_plots_show_advanced", None)
            st.rerun()
        text_col.caption(
            "Глубокая настройка продолжает текущий PlotSpec. Данные, оси, источники и группировка не выбираются заново."
        )
        render_advanced_xy_workspace(project_id)
        return

    _quick_workspace(project_id)
