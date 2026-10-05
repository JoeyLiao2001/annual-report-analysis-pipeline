"""Unit tests for the CDEW report augmenter (Task 8)."""

import hashlib
import json
import pathlib
import tempfile
import unittest

from render_cdew_report import DEDUP_RULES, augment_report, enhance_digest


def _write_metrics(d: pathlib.Path) -> pathlib.Path:
    p = d / "metrics.json"
    p.write_text(
        json.dumps(
            {
                "company": "TEST",
                "version": "v1",
                "fiscal_year": 2025,
                "industry": "Industrials",
                "metrics": {
                    "gross_margin_pct": 17.74,
                    "dso_days": 22.5,
                    "dio_days": 70.2,
                    "dpo_days": 118.2,
                    "ccc_days": -25.5,
                    "revenue_growth_pct": 3.5,
                    "debt_to_equity": 2.42,
                },
                "trends": {},
            }
        ),
        encoding="utf-8",
    )
    return p


class TestAugment(unittest.TestCase):
    def test_original_unchanged_and_new_created(self):
        with tempfile.TemporaryDirectory() as d:
            d = pathlib.Path(d)
            original = d / "report.html"
            original.write_text(
                "<html><body><h2>2. Financial Analysis</h2></body></html>",
                encoding="utf-8",
            )
            before = hashlib.sha256(original.read_bytes()).hexdigest()
            score = d / "score.json"
            score.write_text(
                json.dumps(
                    {
                        "health_score": 82,
                        "grade": "LOW",
                        "distress_probability": 0.18,
                        "top_drivers": [],
                    }
                ),
                encoding="utf-8",
            )
            metrics = _write_metrics(d)
            out = d / "report_CDEW.html"
            augment_report(
                str(original), str(score), str(metrics), "", str(out)
            )
            self.assertEqual(
                hashlib.sha256(original.read_bytes()).hexdigest(), before
            )
            text = out.read_text(encoding="utf-8")
            self.assertIn("82", text)
            self.assertIn("cdew-analytics", text)

    def test_dedup_rules_apply_to_new_copy_only(self):
        with tempfile.TemporaryDirectory() as d:
            d = pathlib.Path(d)
            original = d / "report.html"
            original.write_text(
                "<html><body><h2>2. Financial Analysis</h2>"
                "<h3>Risk Verdict</h3><p>Old verdict text.</p>"
                "</body></html>",
                encoding="utf-8",
            )
            before = hashlib.sha256(original.read_bytes()).hexdigest()
            score = d / "score.json"
            score.write_text(
                json.dumps(
                    {
                        "health_score": 82,
                        "grade": "LOW",
                        "distress_probability": 0.18,
                        "top_drivers": [],
                    }
                ),
                encoding="utf-8",
            )
            metrics = _write_metrics(d)
            out = d / "report_CDEW.html"
            augment_report(
                str(original), str(score), str(metrics), "", str(out)
            )
            self.assertEqual(
                hashlib.sha256(original.read_bytes()).hexdigest(), before
            )
            self.assertNotIn("Old verdict text.", out.read_text(encoding="utf-8"))

    def test_gwm_risk_verdict_rule(self):
        html = (
            '<div class="card"><div class="card-title">Risk Verdict</div>'
            "<p>Old GWM verdict.</p></div>"
        )
        rule = next(r for r in DEDUP_RULES if r["name"] == "GWM Risk Verdict (card)")
        self.assertNotIn("Old GWM verdict", rule["pattern"].sub("", html))

    def test_enhance_digest_adds_column_and_chip(self):
        html = (
            '<html><body><h2 id="s1">1. Executive Summary</h2>'
            "<h3>Key Metrics (FY2023-FY2025)</h3>"
            "<table><thead><tr><th>Metric</th><th>FY2023</th><th>FY2024</th><th>FY2025</th></tr></thead>"
            "<tbody>"
            "<tr><td>Gross Margin</td><td>20.21%</td><td>19.44%</td><td>17.74%</td></tr>"
            "<tr><td>DSO (Days)</td><td>30.5</td><td>32.9</td><td>22.5</td></tr>"
            "<tr><td>Net Profit (RMB B)</td><td>30.0</td><td>40.3</td><td>32.6</td></tr>"
            "</tbody></table></body></html>"
        )
        percentiles = {"gross_margin_pct": 22.0, "dso_days": 3.0}
        out = enhance_digest(
            html,
            {"health_score": 82, "grade": "LOW"},
            percentiles,
            adapter="DemoEV",
        )
        self.assertIn("Industry Pct", out)
        self.assertIn("P22", out)
        self.assertIn("P3", out)
        self.assertIn("CDEW 82 / LOW", out)
        # Net profit row has no benchmark -> em dash.
        self.assertIn("\u2014", out)

    def test_original_table_unchanged_by_enhance(self):
        original_table = (
            "<table><thead><tr><th>Metric</th><th>FY2023</th></tr></thead>"
            "<tbody><tr><td>Revenue</td><td>1.0</td></tr></tbody></table>"
        )
        html = (
            '<h2 id="s1">1. Executive Summary</h2>'
            "<h3>Key Metrics (FY2023-FY2025)</h3>" + original_table
        )
        out = enhance_digest(html, {"health_score": 50, "grade": "HIGH"}, {})
        self.assertIn("Revenue", out)
        self.assertIn("Industry Pct", out)


if __name__ == "__main__":
    unittest.main()
