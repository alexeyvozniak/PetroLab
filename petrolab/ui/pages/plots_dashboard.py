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
from petrolab.ui.advanced_recipe_state import (
    advanced_recipe_for_entry,
    current_advanced_recipe,
    deep_state_summary,
)
from petrolab.ui.layout import render_badges, render_page_header
from petrolab.ui.navigation import navigate
from petrolab.ui.pages.plots_advanced import render_advanced_xy_workspace
from petrolab.ui.plot_manager import render_series_manager
from petrolab.ui.plot_spec import PlotSpec, read_current_plot_spec, send_to_multi_panel, set_current_plot_spec
from petrolab.ui.project_context import active_project_id
from petrolab.ui.smart_plot_start import (
    QUICK_CUSTOM_GRAPH_CHOICE,
    advanced_recipe_from_spec,
    clear_exact_plot_scope,
    consume_plot_scope,
    restore_quick_plot_state,
    seed_xy_state,
    sync_xy_recommendation_state,
    xy_recommendations,
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


def _analysis_universe_ids(dataframe: pd.DataFrame) -> tuple[str, ...]:
    """Return immutable graph membership before reversible presentation filters.

    Source/series visibility, log-axis sanitation and other display controls must not
    silently redefine the scientific DataUniverse handed to another linked view.
    """
    if "_analysis_id" not in dataframe.columns:
        return ()
    values = [str(value).strip() for value in dataframe["_analysis_id"].tolist()]
    return tuple(dict.fromkeys(value for value in values if value))


def _apply_graph_choice(choice_axes: dict[str, tuple[str, str]]) -> None:
    choice = str(st.session_state.get("quick_graph_choice") or "")
    pair = choice_axes.get(choice)
    if pair is None:
        return
    st.session_state["quick_x"] = pair[0]
    st.session_state["quick_y"] = pair[1]


def _mark_custom_axes() -> None:
    st.session_state["quick_graph_choice"] = QUICK_CUSTOM_GRAPH_CHOICE


def _swap_quick_axes() -> None:
    x = str(st.session_state.get("quick_x") or "")
    y = str(st.session_state.get("quick_y") or "")
    if not x or not y or x == y:
        return
    st.session_state["quick_x"] = y
    st.session_state["quick_y"] = x
    st.session_state["quick_graph_choice"] = QUICK_CUSTOM_GRAPH_CHOICE


def _group_control(dataframe: pd.DataFrame, numeric: list[str], visible_sources: list[str]) -> str | None:
    categorical = [
        column for column in dataframe.columns
        if not str(column).startswith("_")
        and column not in numeric
        and dataframe[column].nunique(dropna=True) <= 80
    ]
    curated = [column for column in _CURATED_GROUPS if column in categorical]
    advanced = [column for column in categorical if column not in curated]
    options = ["Без группировки", *curated]
    if advanced:
        options.append("Другой столбец…")

    pending = str(st.session_state.pop("_quick_resume_group_pending", "") or "")
    if pending:
        if pending in curated:
            st.session_state["quick_group"] = pending
        elif pending in advanced:
            st.session_state["quick_group"] = "Другой столбец…"
            st.session_state["quick_group_advanced"] = pending
        else:
            st.session_state["quick_group"] = "Без группировки"

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
        current_advanced = st.session_state.get("quick_group_advanced")
        if current_advanced not in advanced:
            st.session_state.pop("quick_group_advanced", None)
        group = st.selectbox("Другой столбец", advanced, key="quick_group_advanced") if advanced else "Без группировки"
    return None if group == "Без группировки" else str(group)


def _clear_quick_state_for_new_scope() -> None:
    for key in (
        "quick_plot_minerals", "quick_graph_choice", "quick_x", "quick_y",
        "quick_group", "quick_group_advanced", "quick_plot_search",
        "_quick_graph_recommendation_signature",
    ):
        st.session_state.pop(key, None)
    for key in list(st.session_state):
        if str(key).startswith("_quick_resume_"):
            st.session_state.pop(key, None)


def _apply_pending_dataset_resume(labels: dict[str, int]) -> None:
    raw = st.session_state.pop("_quick_resume_dataset_ids", None)
    if not isinstance(raw, (list, tuple)):
        return
    wanted: set[int] = set()
    for value in raw:
        try:
            wanted.add(int(value))
        except (TypeError, ValueError):
            continue
    chosen = [label for label, dataset_id in labels.items() if dataset_id in wanted]
    if chosen:
        st.session_state["quick_plot_datasets"] = chosen


def _deep_state_caption() -> None:
    summary = deep_state_summary(current_advanced_recipe(st.session_state))
    if not summary:
        return
    st.caption(
        "Расширенные настройки сохранены отдельно и сейчас не применяются: "
        + ", ".join(summary)
        + ". «Настроить подробнее» восстановит их только если научный контекст совместим."
    )


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
        _clear_quick_state_for_new_scope()
    _apply_pending_dataset_resume(labels)

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
        universe_analysis_ids = _analysis_universe_ids(dataframe)
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

        ranked = xy_recommendations(selected_minerals, dataframe.columns, numeric, limit=4)
        recommendation = ranked[0] if ranked else None
        seed_xy_state(
            st.session_state,
            numeric_columns=numeric,
            recommendation=recommendation,
        )
        sync_xy_recommendation_state(st.session_state, ranked)

        choice_axes = {f"rec:{index}": (item.x, item.y) for index, item in enumerate(ranked)}
        choice_labels = {
            f"rec:{index}": (
                f"Рекомендовано · {item.title}" if index == 0 else f"Другой график · {item.title}"
            )
            for index, item in enumerate(ranked)
        }
        choice_labels[QUICK_CUSTOM_GRAPH_CHOICE] = "Свои оси"
        choice_options = [*choice_axes, QUICK_CUSTOM_GRAPH_CHOICE]
        if st.session_state.get("quick_graph_choice") not in choice_options:
            st.session_state["quick_graph_choice"] = choice_options[0] if ranked else QUICK_CUSTOM_GRAPH_CHOICE
        selected_choice = st.selectbox(
            "График",
            choice_options,
            key="quick_graph_choice",
            format_func=lambda value: choice_labels.get(str(value), str(value)),
            on_change=_apply_graph_choice,
            args=(choice_axes,),
            help="Рекомендации только выбирают доступный стартовый вид. Они не меняют данные и не являются научной классификацией.",
        )
        selected_recommendation = None
        if str(selected_choice).startswith("rec:"):
            try:
                selected_recommendation = ranked[int(str(selected_choice).split(":", 1)[1])]
            except (ValueError, IndexError):
                selected_recommendation = recommendation
        if selected_recommendation is not None:
            st.caption(f"Smart Start · {selected_recommendation.note}")

        ax_x, ax_swap, ax_y = st.columns([1, 0.34, 1], gap="small")
        x = ax_x.selectbox(
            "X",
            numeric,
            key="quick_x",
            on_change=_mark_custom_axes,
        )
        y_options = [column for column in numeric if column != x]
        if st.session_state.get("quick_y") not in y_options:
            st.session_state["quick_y"] = (
                recommendation.y
                if recommendation is not None and recommendation.y in y_options
                else y_options[0]
            )
        ax_swap.button(
            "⇄",
            width="stretch",
            key="quick_swap_axes",
            help="Поменять X и Y местами.",
            on_click=_swap_quick_axes,
        )
        y = ax_y.selectbox(
            "Y",
            y_options,
            key="quick_y",
            on_change=_mark_custom_axes,
        )
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

        resume_group = str(st.session_state.get("_quick_resume_series_group") or "")
        resume_visible_raw = st.session_state.get("_quick_resume_visible_series")
        resume_visible = (
            tuple(str(value) for value in resume_visible_raw if str(value))
            if resume_group == str(group_col or "") and isinstance(resume_visible_raw, (list, tuple))
            else None
        )
        series_epoch = str(st.session_state.get("_quick_series_epoch", 0))
        series_token = f"{group_col or 'none'}_{series_epoch}"
        plot_source, managed_series = render_series_manager(
            plot_source,
            group_col,
            key_prefix="quick_plot",
            initial_visible_series=resume_visible,
            widget_token=series_token,
        )
        if plot_source.empty:
            return
        st.session_state["_quick_resume_visible_series"] = list(managed_series)
        st.session_state["_quick_resume_series_group"] = str(group_col or "")

        if group_col:
            names = list(managed_series) or plot_source[group_col].astype(str).unique().tolist()
        else:
            names = ["Все точки"]
        existing_styles = st.session_state.get("_quick_resume_style_map")
        if not isinstance(existing_styles, dict):
            existing_styles = {}
        styles = style_map(style_dataframe([str(value) for value in names], existing=existing_styles))
        st.session_state["_quick_resume_style_map"] = {
            str(key): dict(value) for key, value in styles.items()
        }
        render_badges([
            (f"{len(plot_source):,} точек".replace(",", " "), "accent"),
            (f"{len(names)} групп", "neutral"),
        ])

    spec = PlotSpec(
        dataset_ids=tuple(selected_ids),
        analysis_ids=universe_analysis_ids,
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
        _deep_state_caption()
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
            compact_recipe = advanced_recipe_from_spec(
                spec,
                minerals=selected_minerals,
                query=query,
            )
            merge = advanced_recipe_for_entry(
                compact_recipe,
                current_advanced_recipe(st.session_state),
            )
            st.session_state["loaded_recipe"] = merge.recipe
            outlier_cfg = merge.recipe.get("outlier_filters", {})
            st.session_state["plot_interactive_excluded_ids"] = list(
                outlier_cfg.get("interactive_excluded_ids", [])
                if isinstance(outlier_cfg, dict) else []
            )
            if merge.resumed_deep_state:
                st.session_state["_plots_advanced_notice"] = (
                    "Возвращены сохранённые расширенные настройки: "
                    + ", ".join(merge.deep_summary)
                    + "."
                )
            elif merge.dropped_incompatible_deep_state:
                st.session_state["_plots_advanced_notice"] = (
                    "Предыдущие deep-only настройки не применены, потому что изменились "
                    "данные, минералы или X/Y. Это защищает новую диаграмму от скрытых старых фильтров."
                )
            st.session_state["_plots_show_advanced"] = True
            st.rerun()

    with st.expander("Экспорт и публикация", expanded=False):
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
            current = read_current_plot_spec()
            if current is not None:
                restore_quick_plot_state(st.session_state, current)
                st.session_state["_quick_resume_dataset_ids"] = list(current.dataset_ids)
            st.session_state.pop("_plots_show_advanced", None)
            st.rerun()
        text_col.caption(
            "Глубокая настройка продолжает текущий PlotSpec. При возврате compact-workbench восстанавливает представимые настройки; deep-only диапазоны/выбросы сохраняются отдельно и не становятся новым DataUniverse."
        )
        advanced_notice = str(st.session_state.pop("_plots_advanced_notice", "") or "")
        if advanced_notice:
            st.info(advanced_notice)
        render_advanced_xy_workspace(project_id)
        return

    _quick_workspace(project_id)