from __future__ import annotations

import numpy as np
import pandas as pd

from petrolab.group_envelopes import compute_group_envelope, confidence_ellipse, convex_hull


def test_convex_hull_closes_polygon_and_contains_extremes():
    points = np.array([[0, 0], [1, 0], [1, 1], [0, 1], [0.5, 0.5]], dtype=float)
    hull = convex_hull(points)
    assert np.allclose(hull[0], hull[-1])
    assert len(hull) == 5
    assert {tuple(row) for row in hull[:-1]} == {(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)}


def test_confidence_ellipse_is_centered_on_mean():
    rng = np.random.default_rng(42)
    points = rng.multivariate_normal([4.0, -2.0], [[2.0, 0.4], [0.4, 1.0]], size=500)
    ellipse = confidence_ellipse(points, 0.90)
    center = ellipse.mean(axis=0)
    assert np.allclose(center, points.mean(axis=0), atol=0.08)


def test_compute_group_envelope_metadata_and_kde():
    rng = np.random.default_rng(7)
    values = rng.normal(size=(80, 2))
    frame = pd.DataFrame({"X": values[:, 0], "Y": values[:, 1]})
    ellipse = compute_group_envelope(frame, "X", "Y", method="confidence_ellipse", level=0.95)
    assert ellipse.method == "confidence_ellipse"
    assert ellipse.level == 0.95
    assert ellipse.n == 80
    assert len(ellipse.polygons) == 1

    kde = compute_group_envelope(frame, "X", "Y", method="kde", level=0.90)
    assert kde.method == "kde"
    assert kde.level == 0.90
    assert kde.n == 80
    assert kde.polygons
    assert all(poly.shape[1] == 2 for poly in kde.polygons)
