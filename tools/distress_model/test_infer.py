"""Unit tests for CDEW per-company inference (Task 7)."""

import unittest

from infer import grade_for_probability, score_company


class TestInfer(unittest.TestCase):
    def test_schema_without_model(self):
        ratios = {"X4": 30.0, "X5": 0.5, "X8": 0.3}
        out = score_company(None, None, ratios)
        self.assertIn("health_score", out)
        self.assertIn("grade", out)
        self.assertIn("distress_probability", out)
        self.assertIn("top_drivers", out)
        self.assertIn("threshold_policy", out)

    def test_grade_cutoffs(self):
        self.assertEqual(grade_for_probability(0.04), "LOW")
        self.assertEqual(grade_for_probability(0.10), "MEDIUM")
        self.assertEqual(grade_for_probability(0.20), "HIGH")
        self.assertEqual(grade_for_probability(0.50), "CRITICAL")

    def test_grade_boundaries(self):
        self.assertEqual(grade_for_probability(0.05), "MEDIUM")
        self.assertEqual(grade_for_probability(0.15), "HIGH")
        self.assertEqual(grade_for_probability(0.30), "CRITICAL")


if __name__ == "__main__":
    unittest.main()
