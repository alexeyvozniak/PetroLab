from __future__ import annotations

from io import BytesIO

import pandas as pd
import streamlit as st

from petrolab.analysis_groups import set_work_group
from petrolab.interactive_plotting import build_interactive_scatter, selected_analysis_ids
from petrolab.statistics import (
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
        if column.startswith("apfu_")
        or column in {"SiO2", "TiO2", "Al2O3", "Cr2O3", "MgO", "CaO", "Na2O", "K2O", "Mg#", "Cr#"}
        or "[µg/g]" in column
    ]
    return st.multiselect(
        "Переменные",
        numeric,
        default=preferred[: min(12, len(preferred))] or numeric[: min(8, len(numeric))],
        key=key,
    )


def _analysis_basis(key: str) -> str:
    value = st.segmented_control(
        "Геометрия данных",
        ["clr", "euclidean"],
        default="clr",
        format_func=lambda item: "CoDA · CLR" if item == "clr" else "Евклидова · exploratory",
        key=key,
    )
    if value == "clr":
        st.caption(
            "CLR использует отношения компонентов (Aitchison geometry). Строки с пропуском, нулём или отрицательным "
            "значением среди выбранных компонентов исключаются; PetroLab не подставляет псевдосчёт без DL."
        )
    else:
        st.warning(
            "Евклидовый режим полезен для разведочного анализа, но для закрытых геохимических составов может создавать "
            "ложные зависимости. Для major-element и других compositional наборов обычно предпочтителен CLR."
        )
    return str(value)


def render_statistics_page() -> None:
    render_page_header(
        "Статистика",
        "Описание, log-ratio анализ, PCA и кластеризация поверх текущей научной выборки. Исходные анализы не изменяются.",
        eyebrow="Исследование",
    )
    scope = render_analysis_scope("statistics")
    if scope is None:
        return
    dataframe = scope.dataframe
    render_badges([(f"{len(dataframe):,} анализов".replace(",", " "), "accent")])
    tab_desc, tab_corr, tab_pca, tab_cluster = st.tabs(["Описание", "Связи", "PCA", "Кластеры"])

    with tab_desc:
        columns = _feature_selector(dataframe, "stats_desc_features")
        if columns:
            stats = descriptive_statistics(dataframe, columns)
            st.dataframe(stats, width="stretch", height=520)
            st.download_button("Скачать Excel", _xlsx_bytes({"Statistics": stats}), file_name="descriptive_statistics.xlsx")

    with tab_corr:
        columns = _feature_selector(dataframe, "stats_corr_features")
        basis = _analysis_basis("stats_corr_basis")
        if len(columns) < 2:
            st.caption("Выберите минимум две переменные.")
        elif basis == "clr":
            variation = logratio_variation_matrix(dataframe, columns)
            st.caption(
                "Variation matrix: var[ln(xᵢ/xⱼ)]. Чем меньше значение, тем стабильнее отношение двух компонентов. "
                "Это не обычный коэффициент корреляции."
            )
            st.dataframe(variation.style.background_gradient(cmap="viridis"), width="stretch", height=560)
            st.download_button("Скачать Excel", _xlsx_bytes({"Logratio variation": variation}), file_name="logratio_variation_matrix.xlsx")
        else:
            method = st.segmented_control("Коэффициент", ["pearson", "spearman", "kendall"], default="spearman", key="stats_corr_method")
            corr = correlation_matrix(dataframe, columns, method=str(method))
            st.dataframe(corr.style.background_gradient(cmap="RdBu_r", vmin=-1, vmax=1), width="stretch", height=560)
            st.download_button("Скачать Excel", _xlsx_bytes({"Correlation": corr}), file_name="correlation_matrix.xlsx")

    with tab_pca:
        columns = _feature_selector(dataframe, "stats_pca_features")
        if len(columns) < 2:
            st.caption("Для PCA выберите минимум две переменные.")
        else:
            basis = _analysis_basis("stats_pca_basis")
            if basis == "clr":
                scaler, impute = "none", "median"
            else:
                c1, c2 = st.columns(2)
                scaler = c1.selectbox("Масштабирование", ["standard", "robust", "none"], key="stats_pca_scaler")
                impute = c2.selectbox(
                    "Пропуски",
                    ["median", "mean"],
                    format_func=lambda value: "Медиана" if value == "median" else "Среднее",
                    key="stats_pca_impute",
                )
            try:
                prepared = prepare_matrix(dataframe, columns, scaler=scaler, impute=impute, transform=basis)
            except ValueError as exc:
                st.info(str(exc)); prepared = None
            if prepared is not None and prepared.excluded_rows:
                st.caption(f"CLR: исключено строк с пропуском/нулём/отрицательным компонентом: {prepared.excluded_rows}.")
            if prepared is not None and len(prepared.index) >= 2:
                pca = run_pca(prepared, n_components=max(2, min(6, prepared.matrix.shape[1], len(prepared.index))))
                explained = pd.DataFrame({"PC": pca.scores.columns, "Объяснённая дисперсия, %": pca.explained_variance * 100.0})
                st.dataframe(explained, width="stretch", hide_index=True)
                meta = [column for column in ["_analysis_id", "Sample", "Grain", "Point", "Generation", "PetroLab Generation", "Набор", "Минерал"] if column in dataframe.columns]
                score_view = dataframe.loc[pca.scores.index, meta].copy().join(pca.scores)
                groups = [column for column in ["PetroLab Generation", "Generation", "Минерал", "Набор", "Рабочая группа"] if column in score_view.columns]
                group = st.selectbox("Группировка", ["Нет"] + groups, key="stats_pca_group")
                fig = build_interactive_scatter(
                    score_view, "PC1", "PC2",
                    group_col=None if group == "Нет" else group,
                    x_label="PC1", y_label="PC2",
                    title="PCA · CLR" if basis == "clr" else "PCA · Euclidean",
                )
                event = st.plotly_chart(fig, width="stretch", on_select="rerun", selection_mode=("points", "box", "lasso"), key="stats_pca_plot")
                ids = selected_analysis_ids(event)
                if ids:
                    render_badges([(f"Выбрано: {len(ids)}", "accent")])
                st.markdown("#### Нагрузки")
                st.dataframe(pca.loadings, width="stretch", height=360)
                st.download_button(
                    "Скачать PCA Excel",
                    _xlsx_bytes({"Scores": score_view.set_index("_analysis_id"), "Loadings": pca.loadings, "Variance": explained.set_index("PC")}),
                    file_name="pca.xlsx",
                )
            elif prepared is not None:
                st.info("После обработки остался один анализ. Для PCA нужны минимум два.")

    with tab_cluster:
        columns = _feature_selector(dataframe, "stats_cluster_features")
        if len(columns) < 2:
            st.caption("Для кластеризации выберите минимум две переменные.")
            return
        basis = _analysis_basis("stats_cluster_basis")
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
            st.info(str(exc)); return
        if prepared.excluded_rows:
            st.caption(f"CLR: исключено строк с пропуском/нулём/отрицательным компонентом: {prepared.excluded_rows}.")
        if len(prepared.index) < 2:
            st.info("Для кластеризации нужны минимум два анализа."); return
        kwargs = {"method": method}
        if method in {"kmeans", "hierarchical"}:
            maximum = min(12, len(prepared.index))
            kwargs["n_clusters"] = st.slider("Число кластеров", 2, maximum, min(3, maximum), key="stats_cluster_n")
        elif method == "dbscan":
            p1, p2 = st.columns(2)
            kwargs["eps"] = p1.number_input("eps", min_value=0.05, max_value=10.0, value=0.8, step=0.05, key="stats_dbscan_eps")
            kwargs["min_samples"] = p2.number_input("min_samples", min_value=2, max_value=max(2, len(prepared.index)), value=min(5, len(prepared.index)), step=1, key="stats_dbscan_min_samples")
            st.caption("DBSCAN не требует заранее задавать число кластеров; label −1 означает шум/выброс.")
        else:
            p1, p2 = st.columns(2)
            kwargs["min_cluster_size"] = p1.number_input("Минимальный размер кластера", min_value=2, max_value=max(2, len(prepared.index)), value=min(5, len(prepared.index)), step=1, key="stats_hdbscan_min_cluster")
            kwargs["min_samples"] = p2.number_input("min_samples", min_value=1, max_value=max(1, len(prepared.index)), value=min(5, len(prepared.index)), step=1, key="stats_hdbscan_min_samples")
            st.caption("HDBSCAN оценивает число кластеров по плотности; label −1 означает шум/неуверенные точки.")
        result = run_clustering(prepared, **kwargs)
        meta = [column for column in ["_analysis_id", "Sample", "Grain", "Point", "Generation", "PetroLab Generation", "Набор", "Минерал"] if column in dataframe.columns]
        cluster_view = dataframe.loc[result.labels.index, meta].copy()
        cluster_view["Cluster"] = result.labels.astype(int).to_numpy()
        st.dataframe(cluster_view, width="stretch", hide_index=True, height=360)
        clusters = len({int(value) for value in result.labels if int(value) >= 0})
        noise = int((result.labels == -1).sum())
        render_badges([(f"{clusters} кластеров", "accent"), (f"{noise} шум/неуверенные", "neutral")])
        pca = run_pca(prepared, n_components=2)
        plot_view = cluster_view.join(pca.scores)
        title = f"{result.method} · {'CLR' if basis == 'clr' else 'Euclidean'} PCA"
        st.plotly_chart(build_interactive_scatter(plot_view, "PC1", "PC2", group_col="Cluster", title=title), width="stretch", key="stats_cluster_plot")
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
