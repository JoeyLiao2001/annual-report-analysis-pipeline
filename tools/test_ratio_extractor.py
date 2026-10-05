"""Unit tests for the UCI-aligned ratio calculator (Task 6)."""

import unittest

from ratio_extractor import FEASIBILITY, compute_uci_aligned


class TestRatioExtractor(unittest.TestCase):
    def test_gross_margin_ratio(self):
        items = {"revenue": 100.0, "cogs": 70.0, "total_assets": 200.0}
        out = compute_uci_aligned(items)
        # Official UCI dictionary: X19 = gross profit / sales (raw ratio,
        # not percent). Plan sample expected 30.0 (percent); official scale
        # is used so the aligned features match the UCI training data.
        self.assertAlmostEqual(out.get("X19"), 0.3, places=4)

    def test_current_ratio(self):
        items = {"current_assets": 150.0, "current_liabilities": 50.0}
        out = compute_uci_aligned(items)
        self.assertAlmostEqual(out.get("X4"), 3.0, places=4)

    def test_missing_items_omitted(self):
        out = compute_uci_aligned({"revenue": 100.0})
        self.assertNotIn("X1", out)  # needs net profit and total assets
        self.assertNotIn("X19", out)  # needs COGS

    def test_full_set_covers_at_least_10_columns(self):
        items = {
            "revenue": 100.0, "cogs": 70.0, "taxes_surcharges": 2.0,
            "selling_expense": 3.0, "admin_expense": 4.0, "rnd_expense": 5.0,
            "finance_expense": 1.0, "operating_profit": 15.0, "net_profit": 10.0,
            "interest_expense": 0.5, "total_assets": 200.0, "current_assets": 80.0,
            "fixed_assets": 100.0, "total_liabilities": 120.0,
            "current_liabilities": 50.0, "long_term_liabilities": 70.0,
            "equity": 80.0, "share_capital": 20.0, "surplus_reserve": 5.0,
            "undistributed_profit": 15.0, "cash": 10.0,
            "trading_financial_assets": 5.0, "receivables": 20.0,
            "inventory": 25.0, "depreciation_fixed": 6.0,
            "amortization_intangible": 1.0,
        }
        out = compute_uci_aligned(items)
        self.assertGreaterEqual(len(out), 10)

    def test_zero_denominator_omitted(self):
        items = {"net_profit": 10.0, "total_assets": 0.0}
        out = compute_uci_aligned(items)
        self.assertNotIn("X1", out)

    def test_feasibility_covers_64_columns(self):
        self.assertEqual(len(FEASIBILITY), 64)
        self.assertIn("X1", FEASIBILITY)
        self.assertIn("X64", FEASIBILITY)


if __name__ == "__main__":
    unittest.main()
