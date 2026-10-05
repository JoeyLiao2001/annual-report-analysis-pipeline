"""Unit tests for data_loader.py (Task 1: Data loader and EDA).

Follows the implementation plan's TDD flow: these tests are written first,
expected to fail until data_loader.py is implemented.
"""

import os
import pathlib
import unittest

from data_loader import load_all_years, load_year


DATA = pathlib.Path(os.environ.get("POLISH_DATA_DIR", "data/polish_bankruptcy"))


class TestLoader(unittest.TestCase):
    """Tests for the UCI Polish Bankruptcy ARFF loader."""

    def test_load_year_shape(self):
        df = load_year(str(DATA / "1year.arff"))
        self.assertIn("label", df.columns)
        self.assertGreaterEqual(len(df.columns), 65)

    def test_load_all_years(self):
        d = load_all_years(str(DATA), [1, 2, 3])
        self.assertEqual(set(d.keys()), {1, 2, 3})

    def test_label_values_are_binary(self):
        df = load_year(str(DATA / "5year.arff"))
        self.assertEqual(set(df["label"].unique()), {0, 1})

    def test_feature_names_are_x1_to_x64(self):
        df = load_year(str(DATA / "1year.arff"))
        features = [c for c in df.columns if c.startswith("X")]
        self.assertEqual(len(features), 64)
        self.assertEqual(features[0], "X1")
        self.assertEqual(features[-1], "X64")


if __name__ == "__main__":
    unittest.main()
