"""Unit tests for CDEW model training and evaluation (Task 3)."""

import unittest

import numpy as np

from train import bootstrap_ci, evaluate, train_all


def _synthetic(n=200, k=8, seed=0):
    rng = np.random.default_rng(seed)
    X = rng.normal(size=(n, k))
    y = (X[:, 0] + X[:, 1] > 0).astype(int)
    return X, y


class TestTrain(unittest.TestCase):
    def test_train_all_returns_metrics(self):
        X, y = _synthetic()
        res = train_all(X[:150], y[:150], X[150:], y[150:])
        self.assertEqual(set(res.keys()), {"logreg", "random_forest", "xgboost"})
        for v in res.values():
            self.assertTrue(0 <= v["pr_auc"] <= 1)
            self.assertTrue(0 <= v["auc"] <= 1)
            self.assertTrue(v["brier"] >= 0)

    def test_evaluate_metric_bounds(self):
        X, y = _synthetic(n=100, k=4)
        from sklearn.linear_model import LogisticRegression

        model = LogisticRegression().fit(X[:80], y[:80])
        m = evaluate(model, X[80:], y[80:])
        self.assertIn("pr_auc", m)
        self.assertIn("auc", m)
        self.assertIn("brier", m)

    def test_bootstrap_ci_shape(self):
        X, y = _synthetic(n=120, k=4)
        from sklearn.linear_model import LogisticRegression

        model = LogisticRegression().fit(X[:90], y[:90])
        models = {"logreg": {"model": model}}
        cis = bootstrap_ci(X[90:], y[90:], models, n=10, seed=42)
        self.assertIn("logreg", cis)
        for metric in ("pr_auc", "auc", "brier"):
            self.assertIn(metric, cis["logreg"])
            self.assertLessEqual(cis["logreg"][metric]["ci_low"],
                                 cis["logreg"][metric]["ci_high"])


if __name__ == "__main__":
    unittest.main()
