from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.cluster import AgglomerativeClustering, KMeans
from sklearn.decomposition import PCA
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import RobustScaler, StandardScaler


@dataclass(frozen=True)
class PreparedMatrix:
    matrix: np.ndarray
    index: pd.Index
    columns: tuple[str, ...]
    scaler_name: str


@dataclass(frozen=True)
class PCAResult:
    scores: pd.DataFrame
    loadings: pd.DataFrame
    explained_variance: np.ndarray


@dataclass(frozen=True)
class ClusterResult:
    labels: pd.Series
    centers: pd.DataFrame | None
    method: str


def _numeric_frame(dataframe: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """Return numeric data with non-finite values represented as missing."""
    return (
        dataframe[columns]
        .apply(pd.to_numeric, errors="coerce")
        .replace([np.inf, -np.inf], np.nan)
    )


def numeric_feature_candidates(dataframe: pd.DataFrame, *, exclude_meta: bool = True) -> list[str]:
    result: list[str] = []
    for column in dataframe.columns:
        if exclude_meta and str(column).startswith("_"):
            continue
        values = (
            pd.to_numeric(dataframe[column], errors="coerce")
            .replace([np.inf, -np.inf], np.nan)
        )
        if values.notna().sum() >= 2:
            result.append(str(column))
    return result


def prepare_matrix(
    dataframe: pd.DataFrame,
    columns: list[str],
    *,
    scaler: str = "standard",
    impute: str = "median",
) -> PreparedMatrix:
    if not columns:
        raise ValueError("Нужно выбрать хотя бы одну числовую колонку.")
    numeric = _numeric_frame(dataframe, columns)
    valid_rows = numeric.notna().any(axis=1)
    numeric = numeric.loc[valid_rows]
    if numeric.empty:
        raise ValueError("После отбора не осталось строк с числовыми данными.")

    all_missing_columns = [column for column in numeric.columns if numeric[column].notna().sum() == 0]
    if all_missing_columns:
        raise ValueError(
            "После очистки не осталось конечных значений в колонках: "
            + ", ".join(map(str, all_missing_columns))
        )

    strategy = "median" if impute == "median" else "mean"
    filled = SimpleImputer(strategy=strategy).fit_transform(numeric)
    if scaler == "robust":
        scaled = RobustScaler().fit_transform(filled)
        scaler_name = "RobustScaler"
    elif scaler == "none":
        scaled = filled
        scaler_name = "none"
    else:
        scaled = StandardScaler().fit_transform(filled)
        scaler_name = "StandardScaler"
    return PreparedMatrix(scaled, numeric.index, tuple(columns), scaler_name)


def run_pca(prepared: PreparedMatrix, n_components: int = 2) -> PCAResult:
    if prepared.matrix.shape[0] < 2:
        raise ValueError("Для PCA нужны минимум два анализа после обработки пропусков.")
    n_components = int(max(1, min(n_components, prepared.matrix.shape[0], prepared.matrix.shape[1])))
    model = PCA(n_components=n_components)
    scores = model.fit_transform(prepared.matrix)
    score_columns = [f"PC{i + 1}" for i in range(n_components)]
    loading_columns = score_columns
    return PCAResult(
        scores=pd.DataFrame(scores, index=prepared.index, columns=score_columns),
        loadings=pd.DataFrame(model.components_.T, index=prepared.columns, columns=loading_columns),
        explained_variance=model.explained_variance_ratio_.copy(),
    )


def run_clustering(
    prepared: PreparedMatrix,
    *,
    method: str = "kmeans",
    n_clusters: int = 3,
    random_state: int = 42,
) -> ClusterResult:
    sample_count = len(prepared.index)
    if sample_count < 2:
        raise ValueError("Для кластерного анализа нужны минимум два анализа после обработки пропусков.")
    n_clusters = int(max(2, min(n_clusters, sample_count)))
    if method == "hierarchical":
        model = AgglomerativeClustering(n_clusters=n_clusters)
        labels = model.fit_predict(prepared.matrix)
        centers = None
        method_name = "AgglomerativeClustering"
    else:
        model = KMeans(n_clusters=n_clusters, n_init=20, random_state=random_state)
        labels = model.fit_predict(prepared.matrix)
        centers = pd.DataFrame(model.cluster_centers_, columns=prepared.columns)
        method_name = "KMeans"
    return ClusterResult(
        labels=pd.Series(labels, index=prepared.index, name="Cluster"),
        centers=centers,
        method=method_name,
    )


def correlation_matrix(dataframe: pd.DataFrame, columns: list[str], method: str = "pearson") -> pd.DataFrame:
    numeric = _numeric_frame(dataframe, columns)
    return numeric.corr(method=method)


def descriptive_statistics(dataframe: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    numeric = _numeric_frame(dataframe, columns)
    stats = numeric.describe(percentiles=[0.25, 0.5, 0.75]).T
    stats["missing"] = numeric.isna().sum()
    stats["median"] = numeric.median()
    stats["mad"] = (numeric.sub(numeric.median()).abs()).median()
    return stats
