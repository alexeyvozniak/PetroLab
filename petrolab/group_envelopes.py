from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.neighbors import KernelDensity

EnvelopeMethod = Literal["convex_hull", "confidence_ellipse", "kde"]

_CHI2_DF2 = {
    0.68: 2.278868566,
    0.90: 4.605170186,
    0.95: 5.991464547,
}


@dataclass(frozen=True)
class EnvelopeResult:
    polygons: tuple[np.ndarray, ...]
    method: EnvelopeMethod
    level: float
    n: int
    center_x: float
    center_y: float
    metadata: dict


def _xy(dataframe: pd.DataFrame, x: str, y: str) -> np.ndarray:
    work = dataframe[[x, y]].apply(pd.to_numeric, errors="coerce")
    work = work.replace([np.inf, -np.inf], np.nan).dropna()
    return work.to_numpy(dtype=float)


def convex_hull(points: np.ndarray) -> np.ndarray:
    """Return a closed monotonic-chain convex hull."""
    if len(points) < 3:
        raise ValueError("Для convex hull требуется минимум 3 точки")
    unique = sorted({(float(x), float(y)) for x, y in points})
    if len(unique) < 3:
        raise ValueError("Для convex hull требуется минимум 3 уникальные точки")

    def cross(o, a, b) -> float:
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower = []
    for p in unique:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper = []
    for p in reversed(unique):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    hull = np.asarray(lower[:-1] + upper[:-1], dtype=float)
    return np.vstack([hull, hull[0]])


def confidence_ellipse(points: np.ndarray, level: float = 0.95, vertices: int = 181) -> np.ndarray:
    if len(points) < 3:
        raise ValueError("Для confidence ellipse требуется минимум 3 точки")
    supported = min(_CHI2_DF2, key=lambda value: abs(value - float(level)))
    center = points.mean(axis=0)
    covariance = np.cov(points, rowvar=False)
    if covariance.shape != (2, 2) or not np.isfinite(covariance).all():
        raise ValueError("Не удалось оценить ковариацию группы")
    values, vectors = np.linalg.eigh(covariance)
    if np.any(values <= 0):
        raise ValueError("Confidence ellipse не определён для вырожденной группы")
    radii = np.sqrt(values * _CHI2_DF2[supported])
    theta = np.linspace(0.0, 2.0 * np.pi, int(vertices))
    circle = np.column_stack([np.cos(theta), np.sin(theta)])
    return center + (circle * radii) @ vectors.T


def _kde_polygons(points: np.ndarray, level: float = 0.90, grid_size: int = 120) -> tuple[np.ndarray, ...]:
    if len(points) < 5:
        raise ValueError("Для KDE-поля требуется минимум 5 точек")
    mean = points.mean(axis=0)
    scale = points.std(axis=0, ddof=1)
    if np.any(~np.isfinite(scale)) or np.any(scale <= 0):
        raise ValueError("KDE-поле не определено для вырожденной группы")
    z = (points - mean) / scale
    n = len(z)
    bandwidth = max(float(n ** (-1.0 / 6.0)), 0.15)
    kde = KernelDensity(kernel="gaussian", bandwidth=bandwidth).fit(z)

    pad = 0.75
    mins = z.min(axis=0) - pad
    maxs = z.max(axis=0) + pad
    gx = np.linspace(mins[0], maxs[0], int(grid_size))
    gy = np.linspace(mins[1], maxs[1], int(grid_size))
    xx, yy = np.meshgrid(gx, gy)
    grid = np.column_stack([xx.ravel(), yy.ravel()])
    density = np.exp(kde.score_samples(grid)).reshape(xx.shape)

    flat = density.ravel()
    order = np.argsort(flat)[::-1]
    cumulative = np.cumsum(flat[order])
    cumulative /= cumulative[-1]
    target = min(max(float(level), 0.50), 0.99)
    index = int(np.searchsorted(cumulative, target, side="left"))
    threshold = float(flat[order[min(index, len(order) - 1)]])

    fig, ax = plt.subplots()
    try:
        contour = ax.contour(xx, yy, density, levels=[threshold])
        polygons: list[np.ndarray] = []
        for path in contour.get_paths():
            vertices = path.vertices
            if len(vertices) >= 3:
                polygons.append(vertices * scale + mean)
    finally:
        plt.close(fig)
    if not polygons:
        raise ValueError("Не удалось построить KDE-контур")
    polygons.sort(key=lambda value: len(value), reverse=True)
    return tuple(polygons)


def compute_group_envelope(
    dataframe: pd.DataFrame,
    x: str,
    y: str,
    *,
    method: EnvelopeMethod = "confidence_ellipse",
    level: float = 0.90,
) -> EnvelopeResult:
    points = _xy(dataframe, x, y)
    if len(points) < 3:
        raise ValueError("Недостаточно валидных точек для поля группы")
    center = np.median(points, axis=0)
    if method == "convex_hull":
        polygons = (convex_hull(points),)
        effective_level = 1.0
        metadata = {"definition": "convex hull of included points"}
    elif method == "confidence_ellipse":
        effective_level = min(_CHI2_DF2, key=lambda value: abs(value - float(level)))
        polygons = (confidence_ellipse(points, effective_level),)
        metadata = {"distribution_assumption": "bivariate normal", "chi2_df": 2}
    elif method == "kde":
        effective_level = min(max(float(level), 0.50), 0.99)
        polygons = _kde_polygons(points, effective_level)
        metadata = {"kernel": "gaussian", "probability_mass": effective_level}
    else:
        raise ValueError(f"Неизвестный метод поля: {method}")
    return EnvelopeResult(
        polygons=polygons,
        method=method,
        level=float(effective_level),
        n=int(len(points)),
        center_x=float(center[0]),
        center_y=float(center[1]),
        metadata=metadata,
    )
