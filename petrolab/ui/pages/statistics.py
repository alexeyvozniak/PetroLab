from __future__ import annotations

from io import BytesIO

import pandas as pd
import streamlit as st

from petrolab.analysis_groups import set_work_group
from petrolab.dataframe_utils import human_point_label
from petrolab.interactive_plotting import build_interactive_scatter, selected_analysis_ids
from petrolab.statistics import (
    CODA_DOMAIN_LABELS,
    compositional_feature_candidates,
    compositional_feature_domain,
    correlation_matrix,
    descriptive_statistics,
    logratio_variation_matrix,
    numeric_feature_candidates,
    prepare_matrix,
    run_clustering,
    run_pca,
)
from petrolab.ui.data_scope import render_analysis_scope
from petrolab.ui.layout import render_badges, render_page_header
from petrolab.ui.navigation import navigate
from petrolab.ui.project_context import active_project_id
from petrolab.ui.selection_components import render_selection_mode, render_selection_panel
from petrolab.ui.selection_context import read_row_states, read_selection, set_selection
from petrolab.ui.smart_plot_start import seed_selection_plot_handoff


def _xlsx_bytes(sheets: dict[str, pd.DataFrame]) -> bytes:
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        for name, dataframe in sheets.items():
            dataframe.to_excel(writer, sheet_name=name[:31], index=True)
    return buffer.getvalue()


def _feature_selector(dataframe: pd.DataFrame, key: str, *, coda: bool = False) -> list[str]:
    if not coda:
        numeric = numeric_feature_candidates(dataframe)
        preferred = [
            column for column in numeric
            if column.startswith("apfu_")
            or column in {"SiO2", "TiO2", "Al2O3", "Cr2O3", "MgO", "CaO", "Na2O", "K2O", "Mg#", "Cr#"}
            or "[µg/g]" in column
        ]
        return st.multiselect(
            "Переменные", numeric,
            default=preferred[: min(12, len(preferred))] or numeric[: min(8, len(numeric))],
            key=key,
        )

    candidates = compositional_feature_candidates(dataframe)
    domains = []
    for domain in ("oxide_wt", "trace_ug_g", "apfu"):
        if any(compositional_feature_domain(column) == domain for column in candidates):
            domains.append(domain)
    if not domains:
        st.info("Для CLR не найдены минимум два типа распознанных compositional components с известной шкалой.")
        return []
    domain = st.selectbox(
        "Тип композиции",
        domains,
        format_func=lambda value: CODA_DOMAIN_LABELS.get(value, value),
        key=f"{key}_domain",
    )
    options = compositional_feature_candidates(dataframe, domain)
    if domain == "oxide_wt":
        priority = ["SiO2", "TiO2", "Al2O3", "Cr2O3", "FeOt", "FeO", "Fe2O3", "MnO", "MgO", "CaO", "Na2O", "K2O", "P2O5"]
        default = [column for column in priority if column in options][:12]
    else:
        default = options[: min(12, len(options))]
    st.caption("CLR допускает только компоненты выбранного типа; wt.%, µg/g, apfu и производные показатели не смешиваются.")
    return st.multiselect("Компоненты", options, default=default, key=f"{key}_{domain}")


def _analysis_basis(key: str) -> str:
    value = st.segmented_control(
        "Геометрия данных", ["clr", "euclidean"], default="clr",
        format_func=lambda item: "CoDA · CLR" if item == "clr" else "Евклидова · exploratory",
        key=key,
    )
    if value == "clr":
        st.caption(
            "CLR использует отношения компонентов одной композиционной системы. Строки с пропуском, нулём или "
            "отрицательным значением исключаются; PetroLab не подставляет псевдосчёт без DL."
        )
    else:
        st.warning(
            "Евклидовый режим полезен для разведочного анализа, но для закрытых геохимических составов может создавать "
            "ложные зависимости. Для compositional наборов обычно предпочтителен CLR."
        )
    return str(value)


def _apply_statistical_row_states(dataframe: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    states = read_row_states()
    if dataframe.empty or not states.excluded or "_analysis_id" not in dataframe.columns:
        return dataframe, 0
    excluded = set(states.excluded)
    mask = dataframe["_analysis_id"].astype(str).isin(excluded)
    return dataframe.loc[~mask].copy(), int(mask.sum())


def _plot_controls(prefix: str) -> tuple[str, str | bool]:
    c1, c2 = st.columns([1.3, 1])
    with c1:
        tool = st.segmented_control(
            "Инструмент", ["Точка", "Прямоугольник", "Лассо", "Панорама"],
            default="Лассо", key=f"{prefix}_tool",
        ) or "Лассо"
    with c2:
        selection_mode = render_selection_mode(key_prefix=prefix)
    return selection_mode, {
        "Точка": False, "Прямоугольник": "select", "Лассо": "lasso", "Панорама": "pan",
    }.get(str(tool), "lasso")


def _human_table(dataframe: pd.DataFrame) -> pd.DataFrame:
    view = dataframe.copy()
    if "_analysis_id" in view.columns:
        view.insert(0, "Точка", [human_point_label(row) for _, row in view.iterrows()])
    visible = [column for column in view.columns if not str(column).startswith("_")]
    return view[visible]


def render_statistics_page() -> None:
    render_page_header(
        "Статистика",
        "Описание, log-ratio анализ, PCA и кластеризация поверх текущей научной выборки. Selection, Hide и Exclude — разные состояния.",
        eyebrow="Исследование",
    )
    scope = render_analysis_scope("statistics")
    if scope is None:
        return
    raw_dataframe = scope.dataframe
    dataframe, excluded_count = _apply_statistical_row_states(raw_dataframe)
    badges = [(f"{len(dataframe):,} анализов".replace(",", " "), "accent")]
    if excluded_count:
        badges.append((f"{excluded_count} исключено из статистики", "neutral"))
    render_badges(badges)

    section = st.segmented_control(
        "Раздел",
        ["Описание", "Связи", "PCA", "Кластеры"],
        default="PCA",
        key="statistics_section",
    ) or "PCA"

    if section == "Описание":
        columns = _feature_selector(dataframe, "stats_desc_features")
        if columns:
            stats = descriptive_statistics(dataframe, columns)
            st.dataframe(stats, width="stretch", height=520)
            st.download_button("Скачать Excel", _xlsx_bytes({"Statistics": stats}), file_name="descriptive_statistics.xlsx")
        return

    if section == "Связи":
        basis = _analysis_basis("stats_corr_basis")
        columns = _feature_selector(dataframe, f"stats_corr_features_{basis}", coda=basis == "clr")
        if len(columns) < 2:
            st.caption("Выберите минимум две переменные.")
        elif basis == "clr":
            try:
                variation = logratio_variation_matrix(dataframe, columns)
            except ValueError as exc:
                st.info(str(exc))
            else:
                st.caption("Variation matrix: var[ln(xᵢ/xⱼ)]. Чем меньше значение, тем стабильнее отношение двух компонентов.")
                st.dataframe(variation.style.background_gradient(cmap="viridis"), width="stretch", height=560)
                st.download_button("Скачать Excel", _xlsx_bytes({"Logratio variation": variation}), file_name="logratio_variation_matrix.xlsx")
        else:
            method = st.segmented_control("Коэффициент", ["pearson", "spearman", "kendall"], default="spearman", key="stats_corr_method")
            corr = correlation_matrix(dataframe, columns, method=str(method))
            st.dataframe(corr.style.background_gradient(cmap="RdBu_r", vmin=-1, vmax=1), width="stretch", height=560)
            st.download_button("Скачать Excel", _xlsx_bytes({"Correlation": corr}), file_name="correlation_matrix.xlsx")
        return

    project_id = active_project_id()

    if section == "PCA":
        basis = _analysis_basis("stats_pca_basis")
        columns = _feature_selector(dataframe, f"stats_pca_features_{basis}", coda=basis == "clr")
        if len(columns) < 2:
            st.caption("Для PCA выберите минимум две переменные.")
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
        if prepared.excluded_rows:
            st.caption(f"CLR: исключено строк с пропуском/нулём/отрицательным компонентом: {prepared.excluded_rows}.")
        if len(prepared.index) < 2:
            st.info("После обработки остался один анализ. Для PCA нужны минимум два.")
            return
        pca = run_pca(prepared, n_components=max(2, min(6, prepared.matrix.shape[1], len(prepared.index))))
        explained = pd.DataFrame({"PC": pca.scores.columns, "Объяснённая дисперсия, %": pca.explained_variance * 100.0})
        st.dataframe(explained, width="stretch", hide_index=True)
        meta = [column for column in ["_analysis_id", "Sample", "Grain", "Point", "Generation", "PetroLab Generation", "Набор", "Минерал", "Рабочая группа"] if column in dataframe.columns]
        score_view = dataframe.loc[pca.scores.index, meta].copy().join(pca.scores)
        groups = [column for column in ["PetroLab Generation", "Generation", "Рабочая группа", "Sample", "Grain", "Минерал", "Набор"] if column in score_view.columns]
        group = st.selectbox("Группировка", ["Нет", *groups, "Другой столбец…"], key="stats_pca_group")
        if group == "Другой столбец…":
            other = [column for column in score_view.columns if not str(column).startswith("_") and column not in {"PC1", "PC2"} and score_view[column].nunique(dropna=True) <= 80]
            group = st.selectbox("Другой столбец", other, key="stats_pca_other_group") if other else "Нет"
        mode, dragmode = _plot_controls("stats_pca")
        context = read_selection()
        fig = build_interactive_scatter(
            score_view, "PC1", "PC2", group_col=None if group == "Нет" else group,
            x_label="PC1", y_label="PC2", title="PCA · CLR" if basis == "clr" else "PCA · Euclidean",
            selected_ids=context.analysis_ids, dragmode=dragmode,
        )
        event = st.plotly_chart(fig, width="stretch", on_select="rerun", selection_mode=("points", "box", "lasso"), key="stats_pca_plot")
        ids = selected_analysis_ids(event)
        if ids:
            set_selection(ids, origin="PCA", mode=mode)
        render_selection_panel(raw_dataframe, project_id=int(project_id) if project_id is not None else None, key_prefix="stats_pca_selection")
        st.markdown("#### Нагрузки")
        st.dataframe(pca.loadings, width="stretch", height=360)
        st.download_button("Скачать PCA Excel", _xlsx_bytes({"Scores": score_view.set_index("_analysis_id"), "Loadings": pca.loadings, "Variance": explained.set_index("PC")}), file_name="pca.xlsx")
        return

    basis = _analysis_basis("stats_cluster_basis")
    columns = _feature_selector(dataframe, f"stats_cluster_features_{basis}", coda=basis == "clr")
    if len(columns) < 2:
        st.caption("Для кластеризации выберите минимум две переменные.")
        return
    c1, c2 = st.columns(2)
    methods = ["kmeans", "hierarchical", "dbscan", "hdbscan"]
    labels = {"kmeans": "K-means", "hierarchical": "Иерархический", "dbscan": "DBSCAN", "hdbscan": "HDBSCAN"}
    method = c1.selectbox("Метод", methods, format_func=lambda value: labels[value], key="stats_cluster_method")
    if basis == "clr":
        scaler = "none"
        c2.caption("CLR используется без дополнительного scaler.")
    else:
        scaler = c2.selectbox("Масштабирование", ["standard", "robust", "none"], key="stats_cluster_scaler")
    try:
        prepared = prepare_matrix(dataframe, columns, scaler=scaler, impute="median", transform=basis)
    except ValueError as exc:
        st.info(str(exc))
        return
    if prepared.excluded_rows:
        st.caption(f"CLR: исключено строк с пропуском/нулём/отрицательным компонентом: {prepared.excluded_rows}.")
    if len(prepared.index) < 2:
        st.info("Для кластеризации нужны минимум два анализа.")
        return
    kwargs = {"method": method}
    if method in {"kmeans", "hierarchical"}:
        maximum = min(12, len(prepared.index))
        kwargs["n_clusters"] = st.slider("Число кластеров", 2, maximum, min(3, maximum), key="stats_cluster_n")
    elif method == "dbscan":
        p1, p2 = st.columns(2)
        kwargs["eps"] = p1.number_input("eps", min_value=0.05, max_value=10.0, value=0.8, step=0.05, key="stats_dbscan_eps")
        kwargs["min_samples"] = p2.number_input("min_samples", min_value=2, max_value=max(2, len(prepared.index)), value=min(5, len(prepared.index)), step=1, key="stats_dbscan_min_samples")
    else:
        p1, p2 = st.columns(2)
        kwargs["min_cluster_size"] = p1.number_input("Минимальный размер кластера", min_value=2, max_value=max(2, len(prepared.index)), value=min(5, len(prepared.index)), step=1, key="stats_hdbscan_min_cluster")
        kwargs["min_samples"] = p2.number_input("min_samples", min_value=1, max_value=max(1, len(prepared.index)), value=min(5, len(prepared.index)), step=1, key="stats_hdbscan_min_samples")
    result = run_clustering(prepared, **kwargs)
    meta = [column for column in ["_analysis_id", "_dataset_id", "Sample", "Grain", "Point", "Generation", "PetroLab Generation", "Набор", "Минерал"] if column in dataframe.columns]
    cluster_view = dataframe.loc[result.labels.index, meta].copy()
    cluster_view["Cluster"] = result.labels.astype(int).to_numpy()
    st.dataframe(_human_table(cluster_view), width="stretch", hide_index=True, height=360)
    clusters = sorted({int(value) for value in result.labels if int(value) >= 0})
    noise = int((result.labels == -1).sum())
    render_badges([(f"{len(clusters)} кластеров", "accent"), (f"{noise} шум/неуверенные", "neutral")])

    cluster_options = [*clusters]
    if noise:
        cluster_options.append(-1)
    chosen_clusters = st.multiselect(
        "Кластеры в общий отбор",
        cluster_options,
        format_func=lambda value: "Шум / −1" if int(value) == -1 else f"Cluster {int(value) + 1}",
        key="stats_cluster_choose",
    )
    chosen_rows = cluster_view[cluster_view["Cluster"].isin(chosen_clusters)].copy() if chosen_clusters else cluster_view.iloc[0:0].copy()
    cluster_ids = chosen_rows["_analysis_id"].astype(str).tolist() if not chosen_rows.empty else []
    cluster_dataset_ids: list[int] = []
    if not chosen_rows.empty and "_dataset_id" in chosen_rows.columns:
        cluster_dataset_ids = list(dict.fromkeys(
            int(value)
            for value in pd.to_numeric(chosen_rows["_dataset_id"], errors="coerce").dropna().tolist()
        ))
    h1, h2 = st.columns(2)
    if h1.button("Выбрать эти кластеры", disabled=not cluster_ids, width="stretch", key="stats_cluster_select"):
        set_selection(cluster_ids, origin="Кластеры", mode="replace", label=", ".join(str(value) for value in chosen_clusters), metadata={"clusters": chosen_clusters})
        st.rerun()
    if h2.button("Показать эти кластеры на XY", disabled=not cluster_ids, type="primary", width="stretch", key="stats_cluster_to_xy"):
        set_selection(cluster_ids, origin="Кластеры", mode="replace", label=", ".join(str(value) for value in chosen_clusters), metadata={"clusters": chosen_clusters})
        seed_selection_plot_handoff(
            st.session_state,
            dataset_ids=cluster_dataset_ids,
            analysis_ids=cluster_ids,
            origin="Кластеры",
        )
        navigate("plots")
        st.rerun()

    pca = run_pca(prepared, n_components=2)
    plot_view = cluster_view.join(pca.scores)
    mode, dragmode = _plot_controls("stats_cluster_plot_linked")
    context = read_selection()
    cluster_fig = build_interactive_scatter(
        plot_view, "PC1", "PC2", group_col="Cluster",
        title=f"{result.method} · {'CLR' if basis == 'clr' else 'Euclidean'} PCA",
        selected_ids=context.analysis_ids, dragmode=dragmode,
    )
    cluster_event = st.plotly_chart(
        cluster_fig, width="stretch", key="stats_cluster_plot", on_select="rerun",
        selection_mode=("points", "box", "lasso"),
    )
    event_ids = selected_analysis_ids(cluster_event)
    if event_ids:
        set_selection(event_ids, origin="Кластеризация", mode=mode)
    render_selection_panel(raw_dataframe, project_id=int(project_id) if project_id is not None else None, key_prefix="stats_cluster_selection")

    with st.expander("Сохранить кластеры как рабочие группы"):
        prefix = st.text_input("Префикс", value="Cluster", key="stats_cluster_prefix")
        include_noise = st.checkbox("Сохранить шум (−1) отдельной рабочей группой", value=False, key="stats_cluster_noise")
        if st.button("Записать группы", key="stats_cluster_save"):
            total = 0
            for number, subset in cluster_view.groupby("Cluster"):
                if int(number) == -1 and not include_noise:
                    continue
                name = f"{prefix} noise" if int(number) == -1 else f"{prefix} {int(number) + 1}"
                total += set_work_group(subset["_analysis_id"].astype(str).tolist(), name)
            st.success(f"Назначено: {total} анализов.")
    st.download_button("Скачать кластеры Excel", _xlsx_bytes({"Clusters": cluster_view.set_index("_analysis_id")}), file_name="clusters.xlsx")
