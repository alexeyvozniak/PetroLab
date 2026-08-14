from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from petrolab.statistics import prepare_matrix, run_clustering


class DensityClusteringTests(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(42)
        a = rng.normal(loc=(-3.0, -3.0), scale=0.18, size=(20, 2))
        b = rng.normal(loc=(3.0, 3.0), scale=0.18, size=(20, 2))
        noise = np.array([[0.0, 6.0]])
        self.frame = pd.DataFrame(np.vstack([a, b, noise]), columns=["x", "y"])
        self.prepared = prepare_matrix(self.frame, ["x", "y"], scaler="standard")

    def test_dbscan_finds_density_groups_and_noise(self):
        result = run_clustering(self.prepared, method="dbscan", eps=0.35, min_samples=4)
        labels = set(int(value) for value in result.labels)
        self.assertIn(-1, labels)
        self.assertGreaterEqual(len({value for value in labels if value >= 0}), 2)
        self.assertEqual(result.method, "DBSCAN")

    def test_hdbscan_does_not_require_number_of_clusters(self):
        result = run_clustering(self.prepared, method="hdbscan", min_cluster_size=5, min_samples=3)
        clusters = {int(value) for value in result.labels if int(value) >= 0}
        self.assertGreaterEqual(len(clusters), 2)
        self.assertEqual(result.method, "HDBSCAN")
        self.assertIsNone(result.centers)


if __name__ == "__main__":
    unittest.main()
