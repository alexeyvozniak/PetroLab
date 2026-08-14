from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from petrolab.group_envelopes import compute_group_envelope, confidence_ellipse, convex_hull


class GroupEnvelopeTests(unittest.TestCase):
    def test_convex_hull_closes_polygon_and_contains_extremes(self):
        points = np.array([[0, 0], [1, 0], [1, 1], [0, 1], [0.5, 0.5]], dtype=float)
        hull = convex_hull(points)
        self.assertTrue(np.allclose(hull[0], hull[-1]))
        self.assertEqual(len(hull), 5)
        self.assertEqual(
            {tuple(row) for row in hull[:-1]},
            {(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)},
        )

    def test_confidence_ellipse_is_centered_on_mean(self):
        rng = np.random.default_rng(42)
        points = rng.multivariate_normal([4.0, -2.0], [[2.0, 0.4], [0.4, 1.0]], size=500)
        ellipse = confidence_ellipse(points, 0.90)
        center = ellipse.mean(axis=0)
        self.assertTrue(np.allclose(center, points.mean(axis=0), atol=0.08))

    def test_compute_group_envelope_metadata_and_kde(self):
        rng = np.random.default_rng(7)
        values = rng.normal(size=(80, 2))
        frame = pd.DataFrame({"X": values[:, 0], "Y": values[:, 1]})
        ellipse = compute_group_envelope(frame, "X", "Y", method="confidence_ellipse", level=0.95)
        self.assertEqual(ellipse.method, "confidence_ellipse")
        self.assertEqual(ellipse.level, 0.95)
        self.assertEqual(ellipse.n, 80)
        self.assertEqual(len(ellipse.polygons), 1)

        kde = compute_group_envelope(frame, "X", "Y", method="kde", level=0.90)
        self.assertEqual(kde.method, "kde")
        self.assertEqual(kde.level, 0.90)
        self.assertEqual(kde.n, 80)
        self.assertTrue(bool(kde.polygons))
        self.assertTrue(all(poly.shape[1] == 2 for poly in kde.polygons))


if __name__ == "__main__":
    unittest.main()
