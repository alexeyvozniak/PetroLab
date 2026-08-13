from __future__ import annotations

import pandas as pd

from petrolab.settings_service import load_settings

_GROUP_COLORS = (
    "#636EFA", "#EF553B", "#00CC96", "#AB63FA", "#FFA15A",
    "#19D3F3", "#FF6692", "#B6E880", "#FF97FF", "#FECB52",
)


def _grouped_outliers(page, dataframe, columns, method: str, threshold: float, group_column: str | None):
    if not group_column or group_column not in dataframe.columns:
        return page.robust_outliers(dataframe, columns, method=method, threshold=threshold)
    outlier_mask = pd.Series(False, index=dataframe.index, dtype=bool)
    groups = dataframe[group_column].astype("string").fillna("Без группы").replace("", "Без группы")
    for _, index in groups.groupby(groups, sort=False).groups.items():
        subset = dataframe.loc[index]
        result = page.robust_outliers(subset, columns, method=method, threshold=threshold)
        outlier_mask.loc[result.outlier_mask.index] |= result.outlier_mask
    return page.OutlierResult(~outlier_mask, outlier_mask, method, tuple(columns), float(threshold))


def _install_outlier_controls(page) -> None:
    def controls(dataframe, numeric_columns, x, y, recipe):
        original = dataframe.copy()
        cfg = recipe.get("outlier_filters", {}) if isinstance(recipe.get("outlier_filters", {}), dict) else {}
        with page.st.expander("Диапазоны и выбросы", expanded=False):
            page.st.caption("Фильтры действуют только на текущий график; исходные анализы не удаляются.")
            saved_ranges = cfg.get("ranges", {}) if isinstance(cfg.get("ranges", {}), dict) else {}
            range_columns = page.st.multiselect(
                "Ограничить числовые колонки вручную", numeric_columns,
                default=[column for column in saved_ranges if column in numeric_columns], key="plot_range_columns",
            )
            ranges = {}
            for column in range_columns:
                values = pd.to_numeric(dataframe[column], errors="coerce").replace([float("inf"), float("-inf")], pd.NA).dropna()
                if values.empty:
                    continue
                observed_min, observed_max = float(values.min()), float(values.max())
                saved = saved_ranges.get(column, [observed_min, observed_max])
                c1, c2 = page.st.columns(2)
                low = c1.number_input(f"{column}: минимум", value=float(saved[0]) if saved and saved[0] is not None else observed_min, key=f"range_low_{column}")
                high = c2.number_input(f"{column}: максимум", value=float(saved[1]) if len(saved) > 1 and saved[1] is not None else observed_max, key=f"range_high_{column}")
                if low > high:
                    page.st.error(f"{column}: минимум больше максимума")
                else:
                    ranges[column] = (float(low), float(high))
            ranged = page.apply_numeric_ranges(dataframe, ranges) if ranges else dataframe
            page.st.caption(f"После ручных диапазонов: {len(ranged)} из {len(dataframe)} точек.")

            auto_options = {"Нет": "NONE", "MAD — робастный modified z-score": "MAD", "IQR — правило Тьюки": "IQR"}
            reverse = {value: label for label, value in auto_options.items()}
            configured = str(load_settings().get("default_outlier_method", "MAD")).upper()
            saved_method = str(cfg.get("auto_method", configured)).upper()
            auto_label = page.st.selectbox(
                "Автоматически искать выбросы", list(auto_options),
                index=list(auto_options).index(reverse.get(saved_method, reverse.get(configured, "Нет"))), key="outlier_method",
            )
            auto_method = auto_options[auto_label]
            auto_columns, outlier_ids = [], []
            threshold = 0.0
            exclude_auto = bool(cfg.get("exclude_auto", False))
            outlier_scope = str(cfg.get("scope", "all"))
            outlier_group = str(cfg.get("scope_group", ""))

            if auto_method != "NONE":
                saved_auto_columns = cfg.get("auto_columns", [x, y])
                auto_columns = page.st.multiselect(
                    "Колонки для автоматической проверки", numeric_columns,
                    default=[column for column in saved_auto_columns if column in numeric_columns] or [x, y], key="outlier_columns",
                )
                default_threshold = float(cfg.get("threshold", 3.5 if auto_method == "MAD" else 1.5))
                threshold = page.st.number_input(
                    "Порог MAD" if auto_method == "MAD" else "Множитель IQR",
                    min_value=0.1, max_value=20.0, value=default_threshold, step=0.1, key="outlier_threshold",
                )
                group_candidates = [
                    column for column in [page.WORK_GROUP_COLUMN, "Generation", "Набор", "Минерал", "Sample"]
                    if column in ranged.columns and ranged[column].nunique(dropna=True) > 1
                ]
                scope_label = page.st.selectbox(
                    "Область статистики выбросов",
                    ["По всей выборке", "Внутри групп"] if group_candidates else ["По всей выборке"],
                    index=1 if outlier_scope == "group" and group_candidates else 0, key="outlier_scope",
                )
                scope_group = None
                if scope_label == "Внутри групп":
                    default_group = outlier_group if outlier_group in group_candidates else group_candidates[0]
                    scope_group = page.st.selectbox(
                        "Группа для локальной статистики", group_candidates,
                        index=group_candidates.index(default_group), key="outlier_scope_group",
                    )
                    page.st.caption("MAD/IQR считается отдельно внутри каждой выбранной геологической/рабочей группы.")
                result = _grouped_outliers(page, ranged, auto_columns, auto_method, float(threshold), scope_group)
                flagged = ranged.loc[result.outlier_mask].copy()
                if "_analysis_id" in flagged.columns:
                    outlier_ids = flagged["_analysis_id"].astype(str).tolist()
                page.st.info(f"Автоматически отмечено как возможные выбросы: {len(flagged)}. Это статистическая подсказка, а не решение об удалении.")
                if not flagged.empty:
                    preview = [column for column in ["Sample", "Grain", "Point", "Generation", *auto_columns] if column in flagged.columns]
                    page.st.dataframe(flagged[preview].head(200), width="stretch", hide_index=True, height=260)
                exclude_auto = page.st.checkbox("Исключить автоматически отмеченные точки из этого графика", value=exclude_auto, key="exclude_auto_outliers")
                outlier_scope = "group" if scope_group else "all"
                outlier_group = scope_group or ""

            limit = 3000
            candidate_map = {
                page._point_label(row): str(row["_analysis_id"])
                for _, row in ranged.head(limit).iterrows() if "_analysis_id" in ranged.columns
            }
            if len(ranged) > limit:
                page.st.caption(f"Для ручного chooser показаны первые {limit} из {len(ranged)} точек; сохранённые исключения вне chooser не теряются.")
            saved_manual = {str(value) for value in cfg.get("manual_excluded_ids", [])}
            hidden_saved = saved_manual - set(candidate_map.values())
            defaults = [label for label, analysis_id in candidate_map.items() if analysis_id in saved_manual]
            manual_labels = page.st.multiselect(
                "Исключить отдельные точки вручную", list(candidate_map), default=defaults,
                key="manual_outlier_exclusions",
            ) if candidate_map else []
            manual_ids = [candidate_map[label] for label in manual_labels]
            if hidden_saved:
                keep_hidden = page.st.checkbox(
                    f"Сохранять {len(hidden_saved)} ранее исключённых точек вне текущего chooser",
                    value=True, key="keep_hidden_manual_exclusions",
                )
                if keep_hidden:
                    manual_ids.extend(sorted(hidden_saved))

        filtered = ranged
        excluded_ids = set(manual_ids)
        if exclude_auto:
            excluded_ids.update(outlier_ids)
        if excluded_ids:
            filtered = page.exclude_analysis_ids(filtered, tuple(excluded_ids))
        before_ids = set(original.get("_analysis_id", pd.Series(dtype=str)).astype(str))
        after_ids = set(filtered.get("_analysis_id", pd.Series(dtype=str)).astype(str))
        removed = original[original["_analysis_id"].astype(str).isin(before_ids - after_ids)].copy() if "_analysis_id" in original.columns else pd.DataFrame()
        config = {
            "ranges": {column: [bounds[0], bounds[1]] for column, bounds in ranges.items()},
            "auto_method": auto_method, "auto_columns": auto_columns, "threshold": threshold,
            "exclude_auto": exclude_auto, "manual_excluded_ids": list(dict.fromkeys(manual_ids)),
            "scope": outlier_scope, "scope_group": outlier_group,
        }
        return filtered, config, removed

    page._outlier_controls = controls


def install() -> None:
    from petrolab.ui.pages import plots as page
    from petrolab.outliers import OutlierResult

    page.OutlierResult = OutlierResult

    def style_map_from_df(dataframe):
        return {
            str(row["Группа"]): {
                "marker": row["Маркер"], "size_multiplier": float(row["Размер ×"]),
                "alpha": float(row["Alpha"]), "filled": bool(row["Заливка"]),
                "color": _GROUP_COLORS[index % len(_GROUP_COLORS)],
            }
            for index, (_, row) in enumerate(dataframe.iterrows())
        }
    page._style_map_from_df = style_map_from_df
    _install_outlier_controls(page)

    original_build_scatter = page.build_scatter
    def finite_publication_scatter(dataframe, x, y, group=None, **kwargs):
        work = dataframe.copy()
        for column in (x, y):
            work[column] = pd.to_numeric(work[column], errors="coerce").replace([float("inf"), float("-inf")], pd.NA)
        work = work.dropna(subset=[x, y])
        if kwargs.get("log_x"):
            work = work[work[x] > 0]
        if kwargs.get("log_y"):
            work = work[work[y] > 0]
        if group and group in work.columns:
            work[group] = work[group].astype("string").fillna("Без группы").replace("", "Без группы")
        return original_build_scatter(work, x, y, group, **kwargs)
    page.build_scatter = finite_publication_scatter

    original_render = page.render_plots_page
    def guarded_render():
        recipe = page.st.session_state.get("loaded_recipe") or {}
        wanted = [int(value) for value in recipe.get("dataset_ids", []) if str(value).isdigit()]
        if wanted:
            active_project = page.st.session_state.get("active_project_id")
            available = {int(item["id"]) for item in page.list_datasets(int(active_project))} if active_project is not None else {int(item["id"]) for item in page.list_datasets()}
            if not any(dataset_id in available for dataset_id in wanted):
                page.st.warning("Сохранённый рецепт ссылается на datasets, которых больше нет в активном проекте. PetroLab не заменяет их автоматически всеми наборами.")
                if page.st.button("Сбросить устаревший рецепт", key="reset_stale_recipe"):
                    page.st.session_state.loaded_recipe = None
                    page.st.session_state.plot_interactive_excluded_ids = []
                    page.st.rerun()
                return
        return original_render()
    page.render_plots_page = guarded_render

    if not hasattr(page, "_petrolab_original_interactive_workspace"):
        page._petrolab_original_interactive_workspace = page._render_interactive_workspace
    original_workspace = page._petrolab_original_interactive_workspace
    page._petrolab_workspace_call_index = 0

    def dashboard_workspace(dataframe, project_id, x, y, group_col, x_label, y_label, title, log_x, log_y, style_map):
        call_index = int(page._petrolab_workspace_call_index)
        page._petrolab_workspace_call_index = call_index + 1
        if call_index > 0:
            return original_workspace(dataframe, project_id, x, y, group_col, x_label, y_label, title, log_x, log_y, style_map)
        page.st.subheader("Интерактивный график")
        page.st.caption("Кликните точку или выделите область. Для исключений и рабочих групп используйте «Расширенный редактор».")
        figure = page.build_interactive_scatter(
            dataframe, x, y, group_col, x_label=x_label, y_label=y_label,
            title=title, log_x=log_x, log_y=log_y, style_map=style_map,
        )
        event = page.st.plotly_chart(
            figure, width="stretch", theme=None, key="petrolab_quick_interactive_plot",
            on_select="rerun", selection_mode=("points", "box", "lasso"),
            config={"displaylogo": False, "scrollZoom": True},
        )
        selected_ids = page.selected_analysis_ids(event)
        if selected_ids:
            page.st.caption(f"Выбрано точек: {len(selected_ids)}.")
    page._render_interactive_workspace = dashboard_workspace

    from petrolab.ui.image_page_policy import install as install_image_page_policy
    install_image_page_policy()
