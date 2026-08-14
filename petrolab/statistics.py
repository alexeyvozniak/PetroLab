from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.cluster import AgglomerativeClustering, DBSCAN, HDBSCAN, KMeans
from sklearn.decomposition import PCA
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import RobustScaler, StandardScaler


@dataclass(frozen=True)
class PreparedMatrix:
    matrix: np.ndarray
    index: pd.Index
    columns: tuple[str, ...]
    scaler_name: str
    transform_name: str = "euclidean"
    excluded_rows: int = 0


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
    return dataframe[columns].apply(pd.to_numeric, errors="coerce").replace([np.inf, -np.inf], np.nan)


def numeric_feature_candidates(dataframe: pd.DataFrame, *, exclude_meta: bool = True) -> list[str]:
    result: list[str] = []
    for column in dataframe.columns:
        if exclude_meta and str(column).startswith("_"):
            continue
        values = pd.to_numeric(dataframe[column], errors="coerce").replace([np.inf, -np.inf], np.nan)
        if values.notna().sum() >= 2:
            result.append(str(column))
    return result


def _positive_complete_rows(numeric: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Return rows suitable for log-ratio analysis without inventing replacement values.

    PetroLab deliberately does not add arbitrary pseudocounts. Rows containing a missing,
    zero or negative selected component are excluded from CLR/ILR analysis. Detection-limit
    aware replacement belongs in an explicit preprocessing workflow where the censoring
    information is available.
    """
    valid = numeric.notna().all(axis=1) & numeric.gt(0).all(axis=1)
    clean = numeric.loc[valid].copy()
    return clean, int((~valid).sum())


def clr_transform(dataframe: pd.DataFrame, columns: list[str]) -> tuple[pd.DataFrame, int]:
    """Centered log-ratio transform following Aitchison compositional geometry."""
    numeric = _numeric_frame(dataframe, columns)
    clean, excluded = _positive_complete_rows(numeric)
    if clean.empty:
        raise ValueError(
            "Для CLR не осталось строк, где все выбранные компоненты конечны и > 0. "
            "PetroLab не подставляет псевдосчёт автоматически."
        )
    logs = np.log(clean)
    clr = logs.sub(logs.mean(axis=1), axis=0)
    clr.columns = [str(column) for column in columns]
    return clr, excluded


def _helmert_ilr_basis(component_count: int) -> np.ndarray:
    if component_count < 2:
        raise ValueError("Для ILR нужны минимум два компонента.")
    basis = np.zeros((component_count, component_count - 1), dtype=float)
    for j in range(1, component_count):
        scale = np.sqrt(1.0 / (j * (j + 1.0)))
        basis[:j, j - 1] = scale
        basis[j, j - 1] = -j * scale
    return basis


def ilr_transform(dataframe: pd.DataFrame, columns: list[str]) -> tuple[pd.DataFrame, int]:
    """Isometric log-ratio coordinates using a deterministic Helmert basis."""
    clr, excluded = clr_transform(dataframe, columns)
    basis = _helmert_ilr_basis(len(columns))
    values = clr.to_numpy(dtype=float) @ basis
    names = [f"ILR{i + 1}" for i in range(values.shape[1])]
    return pd.DataFrame(values, index=clr.index, columns=names), excluded


def logratio_variation_matrix(dataframe: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """Aitchison variation matrix: var[ln(x_i/x_j)] for positive complete pairs."""
    if len(columns) < 2:
        raise ValueError("Для variation matrix нужны минимум две переменные.")
    numeric = _numeric_frame(dataframe, columns)
    result = pd.DataFrame(np.nan, index=columns, columns=columns, dtype=float)
    for left in columns:
        result.loc[left, left] = 0.0
        for right in columns:
            if left == right:
                continue
            pair = numeric[[left, right]].dropna()
            pair = pair[(pair[left] > 0) & (pair[right] > 0)]
            if len(pair) < 2:
                continue
            ratio = np.log(pair[left].to_numpy(dtype=float) / pair[right].to_numpy(dtype=float))
            result.loc[left, right] = float(np.var(ratio, ddof=1))
    return result


def prepare_matrix(
    dataframe: pd.DataFrame,
    columns: list[str],
    *,
    scaler: str = "standard",
    impute: str = "median",
    transform: str = "euclidean",
) -> PreparedMatrix:
    if not columns:
        raise ValueError("Нужно выбрать хотя бы одну числовую колонку.")
    transform = str(transform).lower()

    if transform in {"clr", "ilr"}:
        transformed, excluded = (
            clr_transform(dataframe, columns)
            if transform == "clr"
            else ilr_transform(dataframe, columns)
        )
        if len(transformed) < 1:
            raise ValueError("После log-ratio преобразования не осталось строк.")
        # Additional component-wise scaling changes Aitchison geometry; keep the transformed
        # coordinates in their natural geometry and make that contract explicit.
        if scaler not in {"none", ""}:
            raise ValueError("Для CLR/ILR используйте масштабирование «none»: дополнительный scaler меняет log-ratio геометрию.")
        return PreparedMatrix(
            transformed.to_numpy(dtype=float),
            transformed.index,
            tuple(map(str, transformed.columns)),
            "none",
            transform,
            excluded,
        )

    numeric = _numeric_frame(dataframe, columns)
    numeric = numeric.loc[numeric.notna().any(axis=1)]
    if numeric.empty:
        raise ValueError("После отбора не осталось строк с числовыми данными.")
    missing = [column for column in numeric.columns if numeric[column].notna().sum() == 0]
    if missing:
        raise ValueError("После очистки не осталось конечных значений в колонках: " + ", ".join(map(str, missing)))
    filled = SimpleImputer(strategy="median" if impute == "median" else "mean").fit_transform(numeric)
    if scaler == "robust":
        scaled, scaler_name = RobustScaler().fit_transform(filled), "RobustScaler"
    elif scaler == "none":
        scaled, scaler_name = filled, "none"
    else:
        scaled, scaler_name = StandardScaler().fit_transform(filled), "StandardScaler"
    return PreparedMatrix(scaled, numeric.index, tuple(columns), scaler_name, "euclidean", 0)


def run_pca(prepared: PreparedMatrix, n_components: int = 2) -> PCAResult:
    if prepared.matrix.shape[0] < 2:
        raise ValueError("Для PCA нужны минимум два анализа после обработки пропусков.")
    n_components = int(max(1, min(n_components, prepared.matrix.shape[0], prepared.matrix.shape[1])))
    model = PCA(n_components=n_components)
    scores = model.fit_transform(prepared.matrix)
    names = [f"PC{i + 1}" for i in range(n_components)]
    return PCAResult(
        pd.DataFrame(scores, index=prepared.index, columns=names),
        pd.DataFrame(model.components_.T, index=prepared.columns, columns=names),
        model.explained_variance_ratio_.copy(),
    )


def run_clustering(
    prepared: PreparedMatrix,
    *,
    method: str = "kmeans",
    n_clusters: int = 3,
    random_state: int = 42,
    eps: float = 0.8,
    min_samples: int = 5,
    min_cluster_size: int = 5,
) -> ClusterResult:
    sample_count = len(prepared.index)
    if sample_count < 2:
        raise ValueError("Для кластерного анализа нужны минимум два анализа после обработки пропусков.")
    method = str(method).lower()
    centers = None
    if method == "dbscan":
        labels = DBSCAN(
            eps=float(max(eps, 1e-6)),
            min_samples=int(max(2, min(min_samples, sample_count))),
        ).fit_predict(prepared.matrix)
        method_name = "DBSCAN"
    elif method == "hdbscan":
        labels = HDBSCAN(
            min_cluster_size=int(max(2, min(min_cluster_size, sample_count))),
            min_samples=int(max(1, min(min_samples, sample_count))),
        ).fit_predict(prepared.matrix)
        method_name = "HDBSCAN"
    else:
        n_clusters = int(max(2, min(n_clusters, sample_count)))
        if method == "hierarchical":
            labels = AgglomerativeClustering(n_clusters=n_clusters).fit_predict(prepared.matrix)
            method_name = "AgglomerativeClustering"
        else:
            model = KMeans(n_clusters=n_clusters, n_init=20, random_state=random_state)
            labels = model.fit_predict(prepared.matrix)
            centers = pd.DataFrame(model.cluster_centers_, columns=prepared.columns)
            method_name = "KMeans"
    return ClusterResult(pd.Series(labels, index=prepared.index, name="Cluster"), centers, method_name)


def correlation_matrix(dataframe: pd.DataFrame, columns: list[str], method: str = "pearson") -> pd.DataFrame:
    return _numeric_frame(dataframe, columns).corr(method=method)


def descriptive_statistics(dataframe: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    numeric = _numeric_frame(dataframe, columns)
    stats = numeric.describe(percentiles=[0.25, 0.5, 0.75]).T
    stats["missing"] = numeric.isna().sum()
    stats["median"] = numeric.median()
    stats["mad"] = (numeric.sub(numeric.median()).abs()).median()
    return stats
