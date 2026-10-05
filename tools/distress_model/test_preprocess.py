"""Unit tests for CDEW preprocessing (Task 2)."""

import pathlib
import tempfile
import unittest

import numpy as np
import pandas as pd

from preprocess import fit_transform, load_params, save_params, transform


class TestPreprocess(unittest.TestCase):
    def test_no_nan_after_fit(self):
        X = pd.DataFrame({"a": [1, 2, np.nan, 100], "b": [0.1, 0.2, 0.3, 0.4]})
        Xt, params = fit_transform(X, pd.Series([0, 1, 0, 1]))
        self.assertFalse(Xt.isna().any().any())
        self.assertIn("a", params)

    def test_transform_uses_train_stats(self):
        X = pd.DataFrame({"a": [1, 2, 3, 4], "b": [1, 2, 3, 4]})
        Xt, params = fit_transform(X, pd.Series([0, 1, 0, 1]))
        Xt2 = transform(X, params)
        self.assertTrue(np.allclose(Xt.values, Xt2.values))

    def test_holdout_scaled_with_train_stats(self):
        X = pd.DataFrame({"a": [1, 2, 3, 4], "b": [1, 2, 3, 4]})
        Xt, params = fit_transform(X, pd.Series([0, 1, 0, 1]))
        holdout = pd.DataFrame({"a": [2.0], "b": [2.0]})
        H = transform(holdout, params)
        # Identical raw values must map to identical z-scores (train stats only).
        self.assertAlmostEqual(float(H["a"].iloc[0]), float(Xt["a"].iloc[1]), places=6)

    def test_params_roundtrip(self):
        X = pd.DataFrame({"a": [1, 2, np.nan, 100], "b": [0.1, 0.2, 0.3, 0.4]})
        _, params = fit_transform(X, pd.Series([0, 1, 0, 1]))
        with tempfile.TemporaryDirectory() as d:
            p = pathlib.Path(d) / "params.json"
            save_params(params, str(p))
            loaded = load_params(str(p))
        self.assertEqual(set(loaded.keys()), set(params.keys()))
        self.assertAlmostEqual(loaded["a"]["mean"], params["a"]["mean"], places=12)

    def test_degenerate_column_does_not_divide_by_zero(self):
        X = pd.DataFrame({"a": [5.0, 5.0, 5.0, 5.0], "b": [1.0, 2.0, 3.0, 4.0]})
        Xt, params = fit_transform(X, pd.Series([0, 1, 0, 1]))
        self.assertTrue(np.isfinite(Xt["a"].to_numpy()).all())
        self.assertEqual(params["a"]["std"], 1.0)


if __name__ == "__main__":
    unittest.main()
