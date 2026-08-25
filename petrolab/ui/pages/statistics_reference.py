from __future__ import annotations

import pandas as pd
import streamlit as st

from petrolab.analysis_groups import WORK_GROUP_COLUMN, set_work_group
from petrolab.interactive_plotting import build_interactive_scatter, selected_analysis_ids
from petrolab.statistics import (
    correlation_matrix,
    descriptive_statistics,
    logratio_variation_matrix,
    prepare_matrix,
    run_clustering,
    run_pca,
)
from petrolab.ui.cluster_plot_handoff import seed_cluster_plot_handoff
from petrolab.ui.data_scope import render_analysis_scope
from petrolab.ui.layout import render_badges, render_page_header, render_work_context
from petrolab.ui.navigation import navigate
from petrolab.ui.reference_selection import render_manual_selection_table, render_selection_action_bar
from petrolab.ui.selection_context import read_row_states, read_selection, set_selection

from . import statistics as _legacy


_CLUSTER_STATE = "statistics_reference_cluster_state"


def _working_dataframe(dataframe: pd.DataFrame) -> pd.DataFrame:
    result = dataframe.copy()
    states = read_row_states()
    if states.excluded and "_analysis_id" in result.columns:
        result = result.loc[~result["_analysis_id"].astype(str).isin(set(states.excluded))].copy()

    selection = read_selection()
    if selection.analysis_ids and "_analysis_id" in result.columns:
        visible = set(result["_analysis_id"].astype(str))
        selected_visible = visible & set(selection.analysis_ids)
        if selected_visible:
            use_selection = st.toggle(
                f"Только рабочая выборка · {len(selected_visible)}",
                value=False,
                key="statistics_reference_use_selection",
                help="Статистика будет рассчитана только по точным analysis_id из общей Selection.",
            )
            if use_selection:
                result = result[result["_analysis_id"].astype(str).isin(selected_visible)].copy()
    return result


def _cluster_inputs(dataframe: pd.DataFrame) -> tuple[object, list[str], str] | None:
    basis = _legacy._analysis_basis("stats_cluster_basis")
    columns = _legacy._feature_selector(
        dataframe,
        f"stats_cluster_features_{basis}",
        coda=basis == "clr",
    )
    if len(columns) < 2:
        st.info("Выберите минимум две переменные, чтобы найти группы.")
        return None
    scaler = "none" if basis == "clr" else st.selectbox(
        "Масштабирование",
        ["standard", "robust", "none"],
        key="stats_cluster_scaler",
    )
    try:
        prepared = prepare_matrix(dataframe, columns, scaler=scaler, impute="median", transform=basis)
    except ValueError as exc:
        st.info(str(exc))
        return None
    if len(prepared.index) < 2:
        st.info("После подготовки осталось меньше двух анализов.")
        return None
    return prepared, columns, basis


def _render_cluster_stage(dataframe: pd.DataFrame, project_id: int | None) -> None:
    st.markdown("### 1. Найти группы")
    st.caption("Сначала PetroLab ищет структуру в выбранных признаках. Cluster остаётся временной аналитической меткой, пока вы явно не сохраните рабочую группу.")
    prepared_input = _cluster_inputs(dataframe)
    if prepared_input is None:
        return
    prepared, columns, basis = prepared_input

    controls = st.columns([1.2, 1.0, 1.0])
    method = controls[0].selectbox(
        "Метод",
        ["kmeans", "hierarchical", "dbscan", "hdbscan"],
        format_func=lambda value: {
            "kmeans": "K-means",
            "hierarchical": "Иерархический",
            "dbscan": "DBSCAN",
            "hdbscan": "HDBSCAN",
        }[value],
        key="stats_cluster_method",
    )
    kwargs: dict[str, object] = {"method": method}
    if method in {"kmeans", "hierarchical"}:
        maximum = max(2, min(12, len(prepared.index)))
        kwargs["n_clusters"] = controls[1].slider(
            "Число групп", 2, maximum, min(3, maximum), key="stats_cluster_n"
        )
        controls[2].caption("Количество можно менять без записи в исходные данные.")
    elif method == "dbscan":
        kwargs["eps"] = controls[1].number_input("eps", 0.05, 10.0, 0.8, 0.05, key="stats_dbscan_eps")
        kwargs["min_samples"] = controls[2].number_input(
            "min_samples", 2, max(2, len(prepared.index)), min(5, len(prepared.index)), 1,
            key="stats_dbscan_min_samples",
        )
    else:
        kwargs["min_cluster_size"] = controls[1].number_input(
            "Минимальный размер", 2, max(2, len(prepared.index)), min(5, len(prepared.index)), 1,
            key="stats_hdbscan_min_cluster",
        )
        kwargs["min_samples"] = controls[2].number_input(
            "min_samples", 1, max(1, len(prepared.index)), min(5, len(prepared.index)), 1,
            key="stats_hdbscan_min_samples",
        )

    try:
        result = run_clustering(prepared, **kwargs)
    except ValueError as exc:
        st.info(str(exc))
        return

    meta = [
        column for column in [
            "_analysis_id", "_dataset_id", "Sample", "Grain", "Point",
            "Generation", WORK_GROUP_COLUMN, "Набор", "Минерал",
        ]
        if column in dataframe.columns
    ]
    cluster_view = dataframe.loc[result.labels.index, meta].copy()
    cluster_view["Cluster"] = result.labels.astype(int).to_numpy()
    cluster_map = {
        str(analysis_id): int(cluster)
        for analysis_id, cluster in zip(
            cluster_view["_analysis_id"].astype(str), cluster_view["Cluster"].astype(int)
        )
    }
    dataset_ids = []
    if "_dataset_id" in cluster_view.columns:
        dataset_ids = list(dict.fromkeys(
            int(value)
            for value in pd.to_numeric(cluster_view["_dataset_id"], errors="coerce").dropna().tolist()
        ))
    st.session_state[_CLUSTER_STATE] = {
        "mapping": cluster_map,
        "dataset_ids": dataset_ids,
        "columns": list(columns),
        "basis": basis,
        "method": result.method,
    }

    clusters = sorted({int(value) for value in cluster_view["Cluster"] if int(value) >= 0})
    noise = int((cluster_view["Cluster"] == -1).sum())
    render_badges([
        (f"{len(clusters)} групп", "accent"),
        (f"{noise} шум / неопределённые", "neutral"),
        (f"{len(cluster_view)} анализов", "neutral"),
    ])

    left, right = st.columns([1.08, 1.0], gap="large")
    with left:
        render_manual_selection_table(
            cluster_view,
            key_prefix="statistics_reference_clusters",
            origin="Статистика · кластеры",
            columns=["Sample", "Grain", "Point", "Минерал", "Generation", WORK_GROUP_COLUMN, "Cluster"],
            height=430,
            max_rows=2500,
        )
    with right:
        pca = run_pca(prepared, n_components=2)
        plot_view = cluster_view.join(pca.scores)
        fig = build_interactive_scatter(
            plot_view,
            "PC1",
            "PC2",
            group_col="Cluster",
            title=f"{result.method} · {'CLR' if basis == 'clr' else 'Euclidean'}",
            selected_ids=read_selection().analysis_ids,
            dragmode="lasso",
        )
        event = st.plotly_chart(
            fig,
            width="stretch",
            on_select="rerun",
            selection_mode=("points", "box", "lasso"),
            key="statistics_reference_cluster_plot",
        )
        ids = selected_analysis_ids(event)
        if ids:
            set_selection(ids, origin="Статистика · PCA кластеры", mode="replace")
            st.rerun()

        options = [*clusters] + ([-1] if noise else [])
        chosen = st.multiselect(
            "Оставить в рабочей выборке",
            options,
            format_func=lambda value: "Шум / −1" if int(value) == -1 else f"Cluster {int(value) + 1}",
            key="statistics_reference_cluster_choose",
        )
        chosen_ids = cluster_view.loc[cluster_view["Cluster"].isin(chosen), "_analysis_id"].astype(str).tolist()
        choose_col, xy_col = st.columns(2)
        if choose_col.button("Выбрать группы", disabled=not chosen_ids, width="stretch"):
            set_selection(chosen_ids, origin="Статистика · кластеры", mode="replace", metadata={"clusters": chosen})
            st.rerun()
        if xy_col.button("Показать на XY", type="primary", disabled=not cluster_map, width="stretch"):
            seed_cluster_plot_handoff(
                st.session_state,
                dataset_ids=dataset_ids,
                analysis_ids=cluster_view["_analysis_id"].astype(str).tolist(),
                cluster_by_analysis_id=cluster_map,
            )
            navigate("plots")
            st.rerun()

    render_selection_action_bar(
        cluster_view,
        key_prefix="statistics_reference_cluster_bottom",
        project_id=project_id,
        show_images=True,
        show_statistics=False,
    )


def _render_pca_stage(dataframe: pd.DataFrame, project_id: int | None) -> None:
    st.markdown("### 2. Проверить структуру на PCA")
    basis = _legacy._analysis_basis("stats_pca_basis")
    columns = _legacy._feature_selector(dataframe, f"stats_pca_features_{basis}", coda=basis == "clr")
    if len(columns) < 2:
        st.info("Для PCA выберите минимум две переменные.")
        return
    if basis == "clr":
        scaler, impute = "none", "median"
    else:
        c1, c2 = st.columns(2)
        scaler = c1.selectbox("Масштабирование", ["standard", "robust", "none"], key="stats_pca_scaler")
        impute = c2.selectbox("Пропуски", ["median", "mean"], format_func=lambda value: "Медиана" if value == "median" else "Среднее", key="stats_pca_impute")
    try:
        prepared = prepare_matrix(dataframe, columns, scaler=scaler, impute=impute, transform=basis)
    except ValueError as exc:
        st.info(str(exc))
        return
    if len(prepared.index) < 2:
        st.info("Для PCA нужны минимум два анализа после обработки.")
        return
    pca = run_pca(prepared, n_components=max(2, min(6, prepared.matrix.shape[1], len(prepared.index))))
    explained = pd.DataFrame({
        "Компонента": pca.scores.columns,
        "Объяснённая дисперсия, %": pca.explained_variance * 100.0,
    })
    render_badges([
        (f"PC1 {explained.iloc[0, 1]:.1f}%", "accent"),
        (f"PC2 {explained.iloc[1, 1]:.1f}%" if len(explained) > 1 else "PC2 нет", "neutral"),
    ])

    meta = [column for column in ["_analysis_id", "_dataset_id", "Sample", "Grain", "Point", "Generation", WORK_GROUP_COLUMN, "Набор", "Минерал"] if column in dataframe.columns]
    score_view = dataframe.loc[pca.scores.index, meta].copy().join(pca.scores)
    groups = [column for column in ["Generation", WORK_GROUP_COLUMN, "Sample", "Минерал", "Набор"] if column in score_view.columns]
    group = st.selectbox("Цвет по", ["Нет", *groups], key="statistics_reference_pca_group")
    fig = build_interactive_scatter(
        score_view,
        "PC1",
        "PC2",
        group_col=None if group == "Нет" else group,
        title="PCA · CLR" if basis == "clr" else "PCA · Euclidean",
        selected_ids=read_selection().analysis_ids,
        dragmode="lasso",
    )
    event = st.plotly_chart(fig, width="stretch", on_select="rerun", selection_mode=("points", "box", "lasso"), key="statistics_reference_pca_plot")
    ids = selected_analysis_ids(event)
    if ids:
        set_selection(ids, origin="Статистика · PCA", mode="replace")
        st.rerun()

    c1, c2 = st.columns([0.9, 1.1])
    with c1:
        st.dataframe(explained, width="stretch", hide_index=True, height=250)
    with c2:
        st.caption("Нагрузки показывают, какие переменные формируют направления PC.")
        st.dataframe(pca.loadings, width="stretch", height=250)
    render_selection_action_bar(score_view, key_prefix="statistics_reference_pca_bottom", project_id=project_id, show_images=True, show_statistics=False)


def _render_difference_stage(dataframe: pd.DataFrame) -> None:
    st.markdown("### 3. Понять, чем группы отличаются")
    mode = st.segmented_control(
        "Режим",
        ["Сравнение групп", "Описание", "Связи"],
        default="Сравнение групп",
        key="statistics_reference_difference_mode",
    ) or "Сравнение групп"

    if mode == "Описание":
        columns = _legacy._feature_selector(dataframe, "stats_desc_features")
        if columns:
            stats = descriptive_statistics(dataframe, columns)
            st.dataframe(stats, width="stretch", height=520)
            st.download_button("Скачать Excel", _legacy._xlsx_bytes({"Statistics": stats}), file_name="descriptive_statistics.xlsx")
        return

    if mode == "Связи":
        basis = _legacy._analysis_basis("stats_corr_basis")
        columns = _legacy._feature_selector(dataframe, f"stats_corr_features_{basis}", coda=basis == "clr")
        if len(columns) < 2:
            st.info("Выберите минимум две переменные.")
            return
        if basis == "clr":
            try:
                matrix = logratio_variation_matrix(dataframe, columns)
            except ValueError as exc:
                st.info(str(exc))
                return
            st.caption("Variation matrix: var[ln(xᵢ/xⱼ)]. Малое значение означает более устойчивое отношение компонентов.")
        else:
            method = st.segmented_control("Коэффициент", ["pearson", "spearman", "kendall"], default="spearman", key="stats_corr_method") or "spearman"
            matrix = correlation_matrix(dataframe, columns, method=str(method))
        st.dataframe(matrix, width="stretch", height=560)
        st.download_button("Скачать Excel", _legacy._xlsx_bytes({"Relations": matrix}), file_name="statistics_relations.xlsx")
        return

    working = dataframe.copy()
    cluster_state = st.session_state.get(_CLUSTER_STATE, {})
    mapping = cluster_state.get("mapping", {}) if isinstance(cluster_state, dict) else {}
    if mapping and "_analysis_id" in working.columns:
        working["Cluster"] = working["_analysis_id"].astype(str).map(mapping)
    groups = [column for column in ["Cluster", "Generation", WORK_GROUP_COLUMN, "Sample", "Минерал", "Набор"] if column in working.columns]
    if not groups:
        st.info("Нет подходящей группирующей колонки. Сначала найдите кластеры или выберите данные с Generation/группами.")
        return
    group = st.selectbox("Сравнивать по", groups, key="statistics_reference_compare_group")
    columns = _legacy._feature_selector(working, "statistics_reference_compare_features")
    if not columns:
        return
    numeric = working[[group, *columns]].copy()
    for column in columns:
        numeric[column] = pd.to_numeric(numeric[column], errors="coerce")
    medians = numeric.groupby(group, dropna=False)[columns].median()
    spread = pd.DataFrame({
        "Переменная": columns,
        "Размах медиан": [float(medians[column].max() - medians[column].min()) for column in columns],
    }).sort_values("Размах медиан", ascending=False)
    left, right = st.columns([1.25, 0.75])
    left.dataframe(medians, width="stretch", height=420)
    right.dataframe(spread, width="stretch", hide_index=True, height=420)
    st.download_button("Скачать сравнение", _legacy._xlsx_bytes({"Group medians": medians, "Median spread": spread.set_index("Переменная")}), file_name="group_comparison.xlsx")


def _render_save_stage(dataframe: pd.DataFrame, project_id: int | None) -> None:
    st.markdown("### 4. Сохранить только осмысленный результат")
    st.caption("Сохраняется Work Group. Generation и исходная химия не переписываются.")
    state = st.session_state.get(_CLUSTER_STATE, {})
    mapping = state.get("mapping", {}) if isinstance(state, dict) else {}
    if mapping and "_analysis_id" in dataframe.columns:
        clustered = dataframe[dataframe["_analysis_id"].astype(str).isin(mapping)].copy()
        clustered["Cluster"] = clustered["_analysis_id"].astype(str).map(mapping)
        groups = sorted(int(value) for value in clustered["Cluster"].dropna().unique() if int(value) >= 0)
        chosen = st.multiselect(
            "Какие кластеры сохранить",
            groups,
            default=groups,
            format_func=lambda value: f"Cluster {int(value) + 1}",
            key="statistics_reference_save_clusters",
        )
        prefix = st.text_input("Префикс рабочих групп", value="Cluster", key="statistics_reference_save_prefix").strip()
        if st.button("Сохранить рабочие группы", type="primary", disabled=not chosen or not prefix, key="statistics_reference_save_groups"):
            total = 0
            for number in chosen:
                ids = clustered.loc[clustered["Cluster"] == int(number), "_analysis_id"].astype(str).tolist()
                total += set_work_group(ids, f"{prefix} {int(number) + 1}")
            st.success(f"Сохранено назначений: {total}. Generation не изменён.")
        render_manual_selection_table(
            clustered,
            key_prefix="statistics_reference_save_table",
            origin="Статистика · сохранение",
            columns=["Sample", "Grain", "Point", "Минерал", "Generation", "Cluster", WORK_GROUP_COLUMN],
            height=360,
            max_rows=2500,
        )
    else:
        st.info("Кластеры ещё не рассчитаны. Можно сохранить текущую ручную Selection через панель ниже.")
    render_selection_action_bar(dataframe, key_prefix="statistics_reference_save_bottom", project_id=project_id, show_images=True, show_statistics=False)


def render_statistics_reference_page() -> None:
    render_page_header(
        "Статистика",
        "Пошаговый анализ: найти группы, проверить их на PCA, понять различия и только затем сохранить рабочие группы.",
        eyebrow="Исследование",
    )
    scope = render_analysis_scope("statistics", allow_all_projects=True, show_search=True)
    if scope is None:
        return
    dataframe = _working_dataframe(scope.dataframe)
    if dataframe.empty:
        st.info("После отбора не осталось строк.")
        return

    context = read_selection()
    render_work_context(
        area="статистика · текущая область данных",
        visible_count=len(dataframe),
        selection_count=context.count,
        note="Exclude влияет на расчёт; Selection остаётся ручной рабочей выборкой",
    )
    st.markdown(
        '<div class="pd-status-strip">'
        '<div class="pd-status-item"><strong>1 · Найти группы</strong><span>кластеризация без записи</span></div>'
        '<div class="pd-status-item"><strong>2 · PCA</strong><span>проверить структуру</span></div>'
        '<div class="pd-status-item"><strong>3 · Отличия</strong><span>медианы и связи</span></div>'
        '<div class="pd-status-item"><strong>4 · Сохранить</strong><span>только Work Group</span></div>'
        '</div>',
        unsafe_allow_html=True,
    )
    stage = st.segmented_control(
        "Этап",
        ["1. Найти группы", "2. PCA", "3. Чем отличаются", "4. Сохранить"],
        default="1. Найти группы",
        key="statistics_reference_stage",
        label_visibility="collapsed",
    ) or "1. Найти группы"

    if stage.startswith("1."):
        _render_cluster_stage(dataframe, scope.project_id)
    elif stage.startswith("2."):
        _render_pca_stage(dataframe, scope.project_id)
    elif stage.startswith("3."):
        _render_difference_stage(dataframe)
    else:
        _render_save_stage(dataframe, scope.project_id)
