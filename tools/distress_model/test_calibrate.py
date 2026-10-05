"""Unit tests for CDEW calibration and threshold economics (Task 4)."""

import unittest

import numpy as np
import pandas as pd

from calibrate import cost_curve, pick_threshold, reliability_table


class TestCalibrate(unittest.TestCase):
    def test_threshold_between_0_1(self):
        y = np.array([0, 1, 0, 1, 0, 1, 0, 0, 1, 0])
        p = np.array([0.1, 0.9, 0.2, 0.8, 0.3, 0.7, 0.2, 0.1, 0.6, 0.4])
        t = pick_threshold(y, p)
        self.assertTrue(0 <= t <= 1)

    def test_reliability_shape(self):
        y = np.array([0, 1, 0, 1, 0, 1, 0, 0, 1, 0, 0, 1, 0, 1, 0, 1, 0, 0, 1, 0])
        p = np.linspace(0.01, 0.99, len(y))
        r = reliability_table(y, p, bins=5)
        self.assertEqual(len(r), 5)
        self.assertIn("bin", r.columns)
        self.assertIn("mean_pred", r.columns)
        self.assertIn("mean_actual", r.columns)
        self.assertIn("count", r.columns)

    def test_cost_curve_columns(self):
        y = np.array([0, 1, 0, 1, 0, 1, 0, 0, 1, 0])
        p = np.array([0.1, 0.9, 0.2, 0.8, 0.3, 0.7, 0.2, 0.1, 0.6, 0.4])
        c = cost_curve(y, p)
        self.assertIn("threshold", c.columns)
        self.assertIn("fp_rate", c.columns)
        self.assertIn("fn_rate", c.columns)
        self.assertIn("expected_cost_per_1000", c.columns)
        self.assertGreaterEqual(len(c), 10)

    def test_threshold_returns_float(self):
        rng = np.random.default_rng(0)
        y = rng.integers(0, 2, 100)
        p = rng.random(100)
        t = pick_threshold(y, p, fn_cost=10.0, fp_cost=1.0)
        self.assertIsInstance(t, float)


if __name__ == "__main__":
    unittest.main()
