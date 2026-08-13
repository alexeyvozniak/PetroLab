from __future__ import annotations

from io import BytesIO

import pandas as pd
import streamlit as st

from petrolab.analysis_groups import set_work_group
from petrolab.interactive_plotting import build_interactive_scatter, selected_analysis_ids
from petrolab.statistics import (
    correlation_matrix,
    descriptive_statistics,
    numeric_feature_candidates,
    prepare_matrix,
    run_clustering,
    run_pca,
)
from petrolab.ui.data_scope import render_analysis_scope


def _xlsx_bytes(sheets: dict[str, pd.DataFrame]) -> bytes:
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        for name, dataframe in sheets.items():
            dataframe.to_excel(writer, sheet_name=name[:31], index=True)
    return buffer.getvalue()


def _feature_selector(dataframe: pd.DataFrame, key: str) -> list[str]:
    numeric = numeric_feature_candidates(dataframe)
    preferred = [
        column for column in numeric
        if column.startswith("apfu_") or column in {"SiO2", "TiO2", "Al2O3", "Cr2O3", "MgO", "CaO", "Na2O", "K2O", "Mg#", "Cr#"}
        or "[µg/g]" in column
    ]
    return st.multiselect(
        "Переменные",
        numeric,
        default=preferred[: min(12, len(preferred))] or numeric[: min(8, len(numeric))],
        key=key,
    )


def render_statistics_page() -> None:
    st.title("Статистика и кластеры")
    st.write(
        "Статистика работает поверх единой базы и производных параметров. Исходные данные не меняются: "
        "результат кластера можно при желании сохранить как локальную «Рабочую группу»."
    )
    scope = render_analysis_scope("statistics")
    if scope is None:
        return
    dataframe = scope.dataframe

    tab_desc, tab_corr, tab_pca, tab_cluster = st.tabs(["Описание", "Корреляции", "PCA", "Кластеры"])

    with tab_desc:
        columns = _feature_selector(dataframe, "stats_desc_features")
        if columns:
            stats = descriptive_statistics(dataframe, columns)
            st.dataframe(stats, width="stretch", height=520)
            st.download_button(
                "Скачать статистику Excel",
                _xlsx_bytes({"Statistics": stats}),
                file_name="descriptive_statistics.xlsx",
                key="stats_desc_download",
            )

    with tab_corr:
        columns = _feature_selector(dataframe, "stats_corr_features")
        method = st.segmented_control("Коэффициент", ["pearson", "spearman", "kendall"], default="spearman", key="stats_corr_method")
        if len(columns) >= 2:
            corr = correlation_matrix(dataframe, columns, method=str(method))
            st.dataframe(corr.style.background_gradient(cmap="RdBu_r", vmin=-1, vmax=1), width="stretch", height=560)
            st.download_button(
                "Скачать матрицу Excel",
                _xlsx_bytes({"Correlation": corr}),
                file_name="correlation_matrix.xlsx",
                key="stats_corr_download",
            )

    with tab_pca:
        columns = _feature_selector(dataframe, "stats_pca_features")
        if len(columns) >= 2:
            c1, c2 = st.columns(2)
            scaler = c1.selectbox("Масштабирование", ["standard", "robust", "none"], key="stats_pca_scaler")
            impute = c2.selectbox("Пропуски", ["median", "mean"], key="stats_pca_impute")
            prepared = prepare_matrix(dataframe, columns, scaler=scaler, impute=impute)
            n_components = min(6, len(columns), len(prepared.index))
            pca = run_pca(prepared, n_components=max(2, n_components))
            explained = pd.DataFrame({
                "PC": pca.scores.columns,
                "Explained variance, %": pca.explained_variance * 100.0,
            })
            st.dataframe(explained, width="stretch", hide_index=True)
            score_view = dataframe.loc[pca.scores.index, [column for column in ["_analysis_id", "Sample", "Grain", "Point", "Generation", "Набор", "Минерал"] if column in dataframe.columns]].copy()
            score_view = score_view.join(pca.scores)
            color_candidates = [column for column in ["Generation", "Минерал", "Набор", "Рабочая группа"] if column in score_view.columns]
            color = st.selectbox("Группировка PCA", ["Нет"] + color_candidates, key="stats_pca_group")
            color = None if color == "Нет" else color
            fig = build_interactive_scatter(score_view, "PC1", "PC2", group_col=color, x_label="PC1", y_label="PC2", title="PCA scores")
            event = st.plotly_chart(fig, width="stretch", on_select="rerun", selection_mode=("points", "box", "lasso"), key="stats_pca_plot")
            ids = selected_analysis_ids(event)
            if ids:
                st.caption(f"Выбрано точек: {len(ids)}")
            st.subheader("Loadings")
            st.dataframe(pca.loadings, width="stretch", height=360)
            st.download_button(
                "Скачать PCA Excel",
                _xlsx_bytes({"Scores": score_view.set_index("_analysis_id"), "Loadings": pca.loadings, "Variance": explained.set_index("PC")}),
                file_name="pca.xlsx",
                key="stats_pca_download",
            )

    with tab_cluster:
        columns = _feature_selector(dataframe, "stats_cluster_features")
        if len(columns) >= 2:
            c1, c2, c3 = st.columns(3)
            method = c1.selectbox("Метод", ["kmeans", "hierarchical"], format_func=lambda value: "K-means" if value == "kmeans" else "Иерархический", key="stats_cluster_method")
            n_clusters = c2.slider("Число кластеров", 2, 12, 3, key="stats_cluster_n")
            scaler = c3.selectbox("Масштабирование", ["standard", "robust", "none"], key="stats_cluster_scaler")
            prepared = prepare_matrix(dataframe, columns, scaler=scaler, impute="median")
            result = run_clustering(prepared, method=method, n_clusters=n_clusters)
            cluster_view = dataframe.loc[result.labels.index, [column for column in ["_analysis_id", "Sample", "Grain", "Point", "Generation", "Набор", "Минерал"] if column in dataframe.columns]].copy()
            cluster_view["Cluster"] = result.labels.astype(int).to_numpy()
            st.dataframe(cluster_view, width="stretch", hide_index=True, height=360)

            pca = run_pca(prepared, n_components=2)
            plot_view = cluster_view.join(pca.scores)
            fig = build_interactive_scatter(plot_view, "PC1", "PC2", group_col="Cluster", title=f"{result.method} · PCA projection")
            event = st.plotly_chart(fig, width="stretch", on_select="rerun", selection_mode=("points", "box", "lasso"), key="stats_cluster_plot")
            chosen = selected_analysis_ids(event)
            if chosen:
                st.caption(f"Выбрано: {len(chosen)}")

            st.subheader("Сохранить кластеры как рабочие группы")
            prefix = st.text_input("Префикс", value="Cluster", key="stats_cluster_prefix")
            if st.button("Записать группы", key="stats_cluster_save"):
                total = 0
                for cluster_number, subset in cluster_view.groupby("Cluster"):
                    ids = subset["_analysis_id"].astype(str).tolist()
                    total += set_work_group(ids, f"{prefix} {int(cluster_number) + 1}")
                st.success(f"Назначено рабочих групп: {total} анализов.")
            st.download_button(
                "Скачать кластеры Excel",
                _xlsx_bytes({"Clusters": cluster_view.set_index("_analysis_id")}),
                file_name="clusters.xlsx",
                key="stats_cluster_download",
            )
