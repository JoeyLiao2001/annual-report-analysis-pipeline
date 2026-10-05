"""Unit tests for the one-command CDEW orchestrator (Task 9)."""

import json
import pathlib
import tempfile
import unittest

from run_cdew import run_cdew

ROOT = pathlib.Path(r"<repo>")
MODEL = ROOT / "output" / "_cdew" / "models" / "aligned_xgboost.joblib"
PREPROCESS = ROOT / "output" / "_cdew" / "models" / "aligned_preprocess_params.joblib"
FEATURE_COLS = ROOT / "output" / "_cdew" / "evaluation" / "aligned_feature_cols.json"
POLICY = ROOT / "output" / "_cdew" / "evaluation" / "threshold_policy.json"


def _build_fixture(d: pathlib.Path) -> pathlib.Path:
    vdir = d / "output" / "FIXTURE" / "v1"
    for year in (2024, 2025):
        fdir = vdir / f"Y{year}" / "finance"
        fdir.mkdir(parents=True, exist_ok=True)
        (fdir / "ratios.json").write_text(
            json.dumps(
                {
                    "revenue": 1000.0,
                    "cogs": 800.0,
                    "gross_margin_pct": 20.0,
                    "dso_days": 30.0,
                    "dio_days": 40.0,
                    "dpo_days": 50.0,
                    "ccc_days": 20.0,
                }
            ),
            encoding="utf-8",
        )
    rdir = vdir / "Y2025" / "ratios"
    rdir.mkdir(parents=True, exist_ok=True)
    (rdir / "uci_aligned.json").write_text(
        json.dumps({"fiscal_year": 2025, "columns": {"X2": 0.5, "X10": 0.5}}),
        encoding="utf-8",
    )
    (rdir / "raw_line_items.json").write_text(
        json.dumps(
            {
                "line_items": [
                    {"name": "total_liabilities", "value": 100.0, "page": 1},
                    {"name": "equity", "value": 100.0, "page": 1},
                ]
            }
        ),
        encoding="utf-8",
    )
    (vdir / "FIXTURE_3Y_Report.html").write_text(
        '<html><body><h2 id="s1">1. Executive Summary</h2>'
        '<h2 id="s3">3. Strategy &amp; Commercial Alignment</h2>'
        "</body></html>",
        encoding="utf-8",
    )
    return d


class TestRunCdew(unittest.TestCase):
    def test_idempotent_second_run(self):
        with tempfile.TemporaryDirectory() as td:
            d = _build_fixture(pathlib.Path(td))
            first = run_cdew(
                "FIXTURE",
                version="v1",
                root=d,
                model=str(MODEL),
                preprocess=str(PREPROCESS),
                feature_cols=str(FEATURE_COLS),
                threshold_policy=str(POLICY),
            )
            self.assertTrue(first["score_written"])
            self.assertTrue(first["report_written"])

            score_path = d / "output" / "FIXTURE" / "v1" / "cross_year" / "distress_score.json"
            report_path = d / "output" / "_cdew" / "reports" / "FIXTURE_v1_3Y_Report_CDEW.html"
            score_before = score_path.read_bytes()
            report_before = report_path.read_text(encoding="utf-8")
            self.assertEqual(report_before.count('id="cdew-analytics"'), 1)

            second = run_cdew(
                "FIXTURE",
                version="v1",
                root=d,
                model=str(MODEL),
                preprocess=str(PREPROCESS),
                feature_cols=str(FEATURE_COLS),
                threshold_policy=str(POLICY),
            )
            self.assertFalse(second["score_written"])
            self.assertFalse(second["report_written"])
            self.assertEqual(score_path.read_bytes(), score_before)
            report_after = report_path.read_text(encoding="utf-8")
            self.assertEqual(report_after, report_before)
            self.assertEqual(report_after.count('id="cdew-analytics"'), 1)


if __name__ == "__main__":
    unittest.main()
