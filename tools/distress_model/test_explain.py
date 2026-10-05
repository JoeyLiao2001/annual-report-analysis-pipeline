"""Unit tests for CDEW SHAP explainability (Task 5)."""

import unittest

import numpy as np
from sklearn.linear_model import LogisticRegression

from explain import global_explanation, local_explanation


class TestExplain(unittest.TestCase):
    def test_global_shape(self):
        X = np.random.default_rng(0).normal(size=(50, 4))
        m = LogisticRegression().fit(X, (X[:, 0] > 0).astype(int))
        g = global_explanation(m, X, ["a", "b", "c", "d"])
        self.assertEqual(len(g), 4)
        self.assertIn("feature", g.columns)
        self.assertIn("mean_abs_shap", g.columns)
        # Sorted descending by importance.
        self.assertTrue(
            (g["mean_abs_shap"].to_numpy() >= g["mean_abs_shap"].to_numpy()[::-1]).all()
            or np.allclose(np.sort(g["mean_abs_shap"].to_numpy())[::-1],
                           g["mean_abs_shap"].to_numpy())
        )

    def test_local_shape(self):
        X = np.random.default_rng(0).normal(size=(20, 3))
        m = LogisticRegression().fit(X, (X[:, 0] > 0).astype(int))
        loc = local_explanation(m, X[0])
        self.assertEqual(len(loc), 3)
        self.assertIn("feature", loc.columns)
        self.assertIn("shap", loc.columns)


if __name__ == "__main__":
    unittest.main()
