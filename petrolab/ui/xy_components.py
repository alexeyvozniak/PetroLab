from __future__ import annotations

import pandas as pd
import streamlit as st

from petrolab.analysis_groups import WORK_GROUP_COLUMN, list_work_groups, set_work_group
from petrolab.dataframe_utils import display_value, row_identity
from petrolab.interactive_plotting import build_interactive_scatter, selected_analysis_ids
from petrolab.outliers import OutlierResult, apply_numeric_ranges, exclude_analysis_ids, robust_outliers
from petrolab.plotting import MARKERS
from petrolab.settings_service import load_settings
from petrolab.ui.components import collect_related_images, render_asset_gallery
from petrolab.ui.plot_actions import clear_work_group


GROUP_COLORS = (
    "#636EFA", "#EF553B", "#00CC96", "#AB63FA", "#FFA15A",
    "#19D3F3", "#FF6692", "#B6E880", "#FF97FF", "#FECB52",
)


def style_dataframe(groups: list[str], existing: dict | None = None) -> pd.DataFrame:
    existing = existing or {}
    rows: list[dict] = []
    for index, name in enumerate(groups):
        raw = existing.get(str(name), {})
        rows.append({
            "Группа": str(name),
            "Маркер": raw.get("marker", MARKERS[index % len(MARKERS)]),
            "Размер ×": float(raw.get("size_multiplier", 1.0) or 1.0),
            "Alpha": float(raw.get("alpha", 0.9) or 0.9),
            "Заливка": bool(raw.get("filled", True)),
        })
    return pd.DataFrame(rows)


def style_map(dataframe: pd.DataFrame) -> dict[str, dict]:
    return {
        str(row["Группа"]): {
            "marker": row["Маркер"],
            "size_multiplier": float(row["Размер ×"]),
            "alpha": float(row["Alpha"]),
            "filled": bool(row["Заливка"]),
            "color": GROUP_COLORS[index % len(GROUP_COLORS)],
        }
        for index, (_, row) in enumerate(dataframe.iterrows())
    }


def point_label(row: pd.Series) -> str:
    return (
        f"{row_identity(row)} · {row.get('Источник', '')} · "
        f"строка {row.get('_source_row', '—')} · {str(row.get('_analysis_id', ''))[:8]}"
    )


def grouped_outliers(
    dataframe: pd.DataFrame,
    columns: list[str],
    method: str,
    threshold: float,
    group_column: str | None,
) -> OutlierResult:
    if not group_column or group_column not in dataframe.columns:
        return robust_outliers(dataframe, columns, method=method, threshold=threshold)
    outlier_mask = pd.Series(False, index=dataframe.index, dtype=bool)
    groups = (
        dataframe[group_column]
        .astype("string")
        .fillna("Без группы")
        .replace("", "Без группы")
    )
    for _, index in groups.groupby(groups, sort=False).groups.items():
        result = robust_outliers(
            dataframe.loc[index],
            columns,
            method=method,
            threshold=threshold,
        )
        outlier_mask.loc[result.outlier_mask.index] |= result.outlier_mask
    return OutlierResult(
        ~outlier_mask,
        outlier_mask,
        method,
        tuple(columns),
        float(threshold),
    )


def render_outlier_controls(
    dataframe: pd.DataFrame,
    numeric_columns: list[str],
    x: str,
    y: str,
    recipe: dict,
) -> tuple[pd.DataFrame, dict, pd.DataFrame]:
    """Render reversible range/outlier filters without mutating analytical storage."""
    original = dataframe.copy()
    cfg = recipe.get("outlier_filters", {})
    if not isinstance(cfg, dict):
        cfg = {}

    with st.expander("Диапазоны и выбросы", expanded=False):
        st.caption("Фильтры действуют только на текущий график; исходные анализы не удаляются.")
        saved_ranges = cfg.get("ranges", {})
        if not isinstance(saved_ranges, dict):
            saved_ranges = {}
        range_columns = st.multiselect(
            "Ограничить числовые колонки вручную",
            numeric_columns,
            default=[column for column in saved_ranges if column in numeric_columns],
            key="plot_range_columns",
        )
        ranges: dict[str, tuple[float, float]] = {}
        for column in range_columns:
            values = (
                pd.to_numeric(dataframe[column], errors="coerce")
                .replace([float("inf"), float("-inf")], pd.NA)
                .dropna()
            )
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

        options = {
            "Нет": "NONE",
            "MAD — робастный modified z-score": "MAD",
            "IQR — правило Тьюки": "IQR",
        }
        reverse = {value: label for label, value in options.items()}
        configured = str(load_settings().get("default_outlier_method", "MAD")).upper()
        saved_method = str(cfg.get("auto_method", configured)).upper()
        auto_label = st.selectbox(
            "Автоматически искать выбросы",
            list(options),
            index=list(options).index(reverse.get(saved_method, reverse.get(configured, "Нет"))),
            key="outlier_method",
        )
        auto_method = options[auto_label]
        auto_columns: list[str] = []
        outlier_ids: list[str] = []
        threshold = 0.0
        exclude_auto = bool(cfg.get("exclude_auto", False))
        outlier_scope = str(cfg.get("scope", "all"))
        outlier_group = str(cfg.get("scope_group", ""))

        if auto_method != "NONE":
            auto_columns = st.multiselect(
                "Колонки для автоматической проверки",
                numeric_columns,
                default=[c for c in cfg.get("auto_columns", [x, y]) if c in numeric_columns] or [x, y],
                key="outlier_columns",
            )
            threshold = st.number_input(
                "Порог MAD" if auto_method == "MAD" else "Множитель IQR",
                min_value=0.1,
                max_value=20.0,
                value=float(cfg.get("threshold", 3.5 if auto_method == "MAD" else 1.5)),
                step=0.1,
                key="outlier_threshold",
            )
            candidates = [
                column
                for column in [WORK_GROUP_COLUMN, "Generation", "Набор", "Минерал", "Sample"]
                if column in ranged.columns and ranged[column].nunique(dropna=True) > 1
            ]
            scope_options = ["По всей выборке", "Внутри групп"] if candidates else ["По всей выборке"]
            scope_label = st.selectbox(
                "Область статистики выбросов",
                scope_options,
                index=1 if outlier_scope == "group" and candidates else 0,
                key="outlier_scope",
            )
            scope_group = None
            if scope_label == "Внутри групп":
                default_group = outlier_group if outlier_group in candidates else candidates[0]
                scope_group = st.selectbox(
                    "Группа для локальной статистики",
                    candidates,
                    index=candidates.index(default_group),
                    key="outlier_scope_group",
                )
                st.caption("MAD/IQR считается отдельно внутри каждой выбранной геологической/рабочей группы.")
            result = grouped_outliers(
                ranged,
                auto_columns,
                auto_method,
                float(threshold),
                scope_group,
            )
            flagged = ranged.loc[result.outlier_mask].copy()
            if "_analysis_id" in flagged.columns:
                outlier_ids = flagged["_analysis_id"].astype(str).tolist()
            st.info(
                f"Автоматически отмечено как возможные выбросы: {len(flagged)}. "
                "Это статистическая подсказка, а не решение об удалении."
            )
            if not flagged.empty:
                preview = [
                    column
                    for column in ["Sample", "Grain", "Point", "Generation", *auto_columns]
                    if column in flagged.columns
                ]
                st.dataframe(flagged[preview].head(200), width="stretch", hide_index=True, height=260)
            exclude_auto = st.checkbox(
                "Исключить автоматически отмеченные точки из этого графика",
                value=exclude_auto,
                key="exclude_auto_outliers",
            )
            outlier_scope = "group" if scope_group else "all"
            outlier_group = scope_group or ""

        limit = 3000
        candidate_map = {
            point_label(row): str(row["_analysis_id"])
            for _, row in ranged.head(limit).iterrows()
            if "_analysis_id" in ranged.columns
        }
        if len(ranged) > limit:
            st.caption(
                f"Для ручного выбора показаны первые {limit} из {len(ranged)} точек; "
                "сохранённые исключения вне списка не теряются."
            )
        saved_manual = {str(value) for value in cfg.get("manual_excluded_ids", [])}
        hidden_saved = saved_manual - set(candidate_map.values())
        defaults = [label for label, analysis_id in candidate_map.items() if analysis_id in saved_manual]
        manual_labels = (
            st.multiselect(
                "Исключить отдельные точки вручную",
                list(candidate_map),
                default=defaults,
                key="manual_outlier_exclusions",
            )
            if candidate_map
            else []
        )
        manual_ids = [candidate_map[label] for label in manual_labels]
        if hidden_saved and st.checkbox(
            f"Сохранять {len(hidden_saved)} ранее исключённых точек вне текущего списка",
            value=True,
            key="keep_hidden_manual_exclusions",
        ):
            manual_ids.extend(sorted(hidden_saved))

    filtered = ranged
    excluded_ids = set(manual_ids)
    if exclude_auto:
        excluded_ids.update(outlier_ids)
    if excluded_ids:
        filtered = exclude_analysis_ids(filtered, tuple(excluded_ids))
    before_ids = set(original.get("_analysis_id", pd.Series(dtype=str)).astype(str))
    after_ids = set(filtered.get("_analysis_id", pd.Series(dtype=str)).astype(str))
    removed = (
        original[original["_analysis_id"].astype(str).isin(before_ids - after_ids)].copy()
        if "_analysis_id" in original.columns
        else pd.DataFrame()
    )
    config = {
        "ranges": {column: [bounds[0], bounds[1]] for column, bounds in ranges.items()},
        "auto_method": auto_method,
        "auto_columns": auto_columns,
        "threshold": threshold,
        "exclude_auto": exclude_auto,
        "manual_excluded_ids": list(dict.fromkeys(manual_ids)),
        "scope": outlier_scope,
        "scope_group": outlier_group,
    }
    return filtered, config, removed


def apply_interactive_exclusions(
    dataframe: pd.DataFrame,
    outlier_config: dict,
    excluded_dataframe: pd.DataFrame,
) -> tuple[pd.DataFrame, dict, pd.DataFrame]:
    ids = {str(value) for value in st.session_state.get("plot_interactive_excluded_ids", [])}
    if not ids or "_analysis_id" not in dataframe.columns:
        outlier_config["interactive_excluded_ids"] = sorted(ids)
        return dataframe, outlier_config, excluded_dataframe
    mask = dataframe["_analysis_id"].astype(str).isin(ids)
    removed = dataframe.loc[mask].copy()
    filtered = dataframe.loc[~mask].copy()
    outlier_config["interactive_excluded_ids"] = sorted(ids)
    if not removed.empty:
        excluded_dataframe = pd.concat([excluded_dataframe, removed], ignore_index=True, sort=False)
        if "_analysis_id" in excluded_dataframe.columns:
            excluded_dataframe = excluded_dataframe.drop_duplicates("_analysis_id", keep="first")
    return filtered, outlier_config, excluded_dataframe


def sanitize_xy_rows(
    dataframe: pd.DataFrame,
    x: str,
    y: str,
    *,
    log_x: bool = False,
    log_y: bool = False,
    group_column: str | None = None,
) -> pd.DataFrame:
    work = dataframe.copy()
    for column in (x, y):
        work[column] = pd.to_numeric(work[column], errors="coerce").replace(
            [float("inf"), float("-inf")], pd.NA
        )
    work = work.dropna(subset=[x, y])
    if log_x:
        work = work[work[x] > 0]
    if log_y:
        work = work[work[y] > 0]
    if group_column and group_column in work.columns:
        work[group_column] = (
            work[group_column]
            .astype("string")
            .fillna("Без группы")
            .replace("", "Без группы")
        )
    return work


def render_quick_interactive(
    dataframe: pd.DataFrame,
    x: str,
    y: str,
    group_column: str | None,
    *,
    x_label: str,
    y_label: str,
    title: str,
    log_x: bool,
    log_y: bool,
    styles: dict,
) -> None:
    st.subheader("Интерактивный график")
    st.caption(
        "Кликните точку или выделите область. Для исключений и рабочих групп используйте «Расширенный редактор»."
    )
    figure = build_interactive_scatter(
        dataframe,
        x,
        y,
        group_column,
        x_label=x_label,
        y_label=y_label,
        title=title,
        log_x=log_x,
        log_y=log_y,
        style_map=styles,
    )
    event = st.plotly_chart(
        figure,
        width="stretch",
        theme=None,
        key="petrolab_quick_interactive_plot",
        on_select="rerun",
        selection_mode=("points", "box", "lasso"),
        config={"displaylogo": False, "scrollZoom": True},
    )
    selected_ids = selected_analysis_ids(event)
    if selected_ids:
        st.caption(f"Выбрано точек: {len(selected_ids)}.")


def _render_selected_analysis(
    dataframe: pd.DataFrame,
    selected_ids: list[str],
    project_id: int,
    x: str,
    y: str,
) -> None:
    selected = dataframe[dataframe["_analysis_id"].astype(str).isin(selected_ids)].copy()
    if selected.empty:
        return
    summary = [
        column
        for column in [
            "Sample", "Grain", "Point", "Generation", WORK_GROUP_COLUMN,
            x, y, "Набор", "Источник", "_source_row",
        ]
        if column in selected.columns
    ]
    st.markdown(f"**Выбрано точек: {len(selected)}**")
    st.dataframe(selected[summary].head(1000), width="stretch", hide_index=True, height=240)
    point_map = {point_label(row): str(row["_analysis_id"]) for _, row in selected.iterrows()}
    inspect_label = st.selectbox(
        "Открыть выбранную точку подробно",
        list(point_map),
        key="interactive_selected_point",
    )
    analysis_id = point_map[inspect_label]
    row = selected[selected["_analysis_id"].astype(str) == analysis_id].iloc[0]
    visible = [column for column in dataframe.columns if not str(column).startswith("_")]
    properties = pd.DataFrame({
        "Параметр": visible,
        "Значение": [display_value(row.get(column)) for column in visible],
    })
    left, right = st.columns([1.1, 1.0])
    with left:
        st.dataframe(properties, width="stretch", hide_index=True, height=430)
    with right:
        assets = collect_related_images(row, project_id=project_id)
        if assets:
            render_asset_gallery(assets, max_items=8, width=520)
        else:
            st.caption("Для этой точки пока нет связанных изображений.")


def render_advanced_interactive(
    dataframe: pd.DataFrame,
    project_id: int,
    x: str,
    y: str,
    group_column: str | None,
    *,
    x_label: str,
    y_label: str,
    title: str,
    log_x: bool,
    log_y: bool,
    styles: dict,
) -> None:
    st.subheader("Интерактивный отбор точек")
    st.caption(
        "Кликните точку или выделите несколько рамкой/лассо. Исключения относятся только к текущему графику."
    )
    figure = build_interactive_scatter(
        dataframe,
        x,
        y,
        group_column,
        x_label=x_label,
        y_label=y_label,
        title=title,
        log_x=log_x,
        log_y=log_y,
        style_map=styles,
    )
    event = st.plotly_chart(
        figure,
        width="stretch",
        theme=None,
        key="petrolab_advanced_interactive_plot",
        on_select="rerun",
        selection_mode=("points", "box", "lasso"),
        config={"displaylogo": False, "scrollZoom": True},
    )
    selected_ids = selected_analysis_ids(event)
    active_excluded = [
        str(value) for value in st.session_state.get("plot_interactive_excluded_ids", [])
    ]
    if active_excluded:
        st.caption(f"Интерактивно исключено: {len(active_excluded)} точек.")

    if selected_ids:
        action1, action2 = st.columns(2)
        if action1.button(
            f"Исключить выбранные ({len(selected_ids)})",
            type="primary",
            key="exclude_plot_selection",
            width="stretch",
        ):
            st.session_state.plot_interactive_excluded_ids = sorted(
                set(active_excluded) | set(selected_ids)
            )
            st.rerun()

        existing_groups = list_work_groups()
        group_choice = action2.selectbox(
            "Рабочая группа",
            ["Новая группа…"] + existing_groups,
            key="selected_work_group_choice",
        )
        new_group_name = ""
        if group_choice == "Новая группа…":
            new_group_name = st.text_input(
                "Название новой рабочей группы",
                key="selected_work_group_name",
                placeholder="например, предполагаемые ксенокристы",
            )
        target_group = new_group_name.strip() if group_choice == "Новая группа…" else group_choice
        g1, g2 = st.columns(2)
        if g1.button(
            "Назначить группу выбранным",
            disabled=not target_group,
            key="assign_work_group",
            width="stretch",
        ):
            changed = set_work_group(selected_ids, target_group)
            st.success(f"Рабочая группа назначена для {changed} точек.")
            st.rerun()
        if g2.button("Убрать рабочую группу", key="clear_work_group", width="stretch"):
            changed = clear_work_group(selected_ids)
            if changed:
                st.success(f"Рабочая группа очищена у {changed} точек.")
                st.rerun()
        _render_selected_analysis(dataframe, selected_ids, project_id, x, y)
    else:
        st.caption("Чтобы открыть анализ и изображения, выберите точку на графике.")

    if active_excluded and st.button(
        "Вернуть все интерактивно исключённые точки",
        key="restore_interactive_exclusions",
    ):
        st.session_state.plot_interactive_excluded_ids = []
        st.rerun()
