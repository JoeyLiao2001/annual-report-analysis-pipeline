"""Batch CDEW inference for all pipeline companies (Task 10).

Scores every company (distress_score.json) and augments showcase reports.
Then writes the 12-row paper-ready summary (markdown + HTML).

Usage:
    python batch_infer.py --companies DemoEV DemoBattery DemoConstruct ... --showcases DemoEV DemoBattery DemoMotor
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from run_cdew import run_cdew

ROOT = Path(__file__).resolve().parents[2]
SHOWCASE_INDUSTRY = {
    "DemoEV": "Industrials",
    "DemoBattery": "Industrials",
    "DemoMotor": "Industrials",
}


def _industry_for(company: str, vdir: Path) -> str:
    flags = vdir / "cross_year" / "industry_flags.json"
    if flags.exists():
        industry = json.loads(flags.read_text(encoding="utf-8")).get("industry")
        if industry:
            return industry
    return SHOWCASE_INDUSTRY.get(company, "Industrials")


def _percentile(value: float, bench: dict) -> float:
    knots = [10, 25, 50, 75, 90]
    xs = [float(bench[f"p{k}"]) for k in knots]
    if value <= xs[0]:
        return 0.0
    if value >= xs[-1]:
        return 100.0
    for i in range(len(knots) - 1):
        if xs[i] <= value <= xs[i + 1]:
            span = xs[i + 1] - xs[i]
            frac = (value - xs[i]) / span if span else 0.0
            return knots[i] + frac * (knots[i + 1] - knots[i])
    return 50.0


def build_summary(companies: list[str], version: str, root: Path) -> None:
    """Write summary.md and summary.html from the 12 distress scores."""
    eval_dir = root / "output" / "_cdew" / "evaluation"
    benchmarks = json.loads(
        (root / "reference" / "industry_benchmarks.json").read_text(encoding="utf-8")
    )["industries"]
    full = json.loads((eval_dir / "model_comparison.json").read_text(encoding="utf-8"))
    aligned = json.loads(
        (eval_dir / "model_comparison_aligned.json").read_text(encoding="utf-8")
    )
    policy = json.loads((eval_dir / "threshold_policy.json").read_text(encoding="utf-8"))

    rows = []
    for company in companies:
        vdir = root / "output" / company / version
        score_path = vdir / "cross_year" / "distress_score.json"
        score = json.loads(score_path.read_text(encoding="utf-8"))
        years = sorted(vdir.glob("Y*/finance/ratios.json"))
        latest = json.loads(years[-1].read_text(encoding="utf-8"))
        industry = _industry_for(company, vdir)
        bench = benchmarks[industry]["benchmarks"]
        gm_pct = _percentile(latest["gross_margin_pct"], bench["gross_margin_pct"])
        dso_pct = _percentile(latest["dso_days"], bench["dso_days"])
        ccc_pct = _percentile(latest["ccc_days"], bench["ccc_days"])
        driver = (score.get("top_drivers") or [{}])[0].get("feature", "-")
        rows.append(
            {
                "company": company,
                "year": score.get("fiscal_year"),
                "prob": score.get("distress_probability"),
                "health": score.get("health_score"),
                "grade": score.get("grade"),
                "top_driver": driver,
                "gm_pct": gm_pct,
                "dso_pct": dso_pct,
                "ccc_pct": ccc_pct,
                "industry": industry,
            }
        )

    md = [
        "# CDEW 12-Company Summary",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        f"Model: aligned XGBoost (25 features) | PR-AUC {aligned['test_metrics']['xgboost']['pr_auc']:.3f}, "
        f"AUC {aligned['test_metrics']['xgboost']['auc']:.3f}, Brier {aligned['test_metrics']['xgboost']['brier']:.3f} "
        f"| Full 64-feature XGBoost: PR-AUC {full['test_metrics']['xgboost']['pr_auc']:.3f}",
        "",
        f"Operating threshold: {policy['threshold']:.4f} (FN:FP = {policy['fn_cost']:.0f}:{policy['fp_cost']:.0f}); "
        f"test recall {policy['test_recall']:.3f}, precision {policy['test_precision']:.3f}, "
        f"FP per 1,000 {policy['test_fp_per_1000']:.1f}",
        "",
        "| Company | Year | Probability | Health | Grade | Top driver | GM Pct | DSO Pct | CCC Pct |",
        "|---------|------|-------------|--------|-------|------------|--------|---------|---------|",
    ]
    for r in rows:
        md.append(
            f"| {r['company']} | {r['year']} | {r['prob']*100:.2f}% | {r['health']} | "
            f"{r['grade']} | {r['top_driver']} | P{int(round(r['gm_pct']))} | "
            f"P{int(round(r['dso_pct']))} | P{int(round(r['ccc_pct']))} |"
        )
    md += [
        "",
        "Percentiles use the company industry benchmark (DemoEV/DemoBattery/DemoMotor: Industrials; "
        "others default to Industrials unless industry_flags.json exists).",
        "",
        "Showcase augmented reports:",
    ]
    for c in ("DemoEV", "DemoBattery", "DemoMotor"):
        md.append(
            f"- `output/_cdew/reports/{c}_{version}_3Y_Report_CDEW.html`"
        )
    (eval_dir / "summary.md").write_text("\n".join(md), encoding="utf-8")

    html_rows = []
    for r in rows:
        strip = (
            f'<span style="display:inline-block;width:{max(2, int(round(r["gm_pct"])))}px;'
            f'height:8px;background:#26a69a;border-radius:2px;"></span>'
        )
        html_rows.append(
            "<tr>"
            f"<td>{r['company']}</td><td>{r['year']}</td>"
            f"<td>{r['prob']*100:.2f}%</td><td>{r['health']}</td>"
            f"<td>{r['grade']}</td><td>{r['top_driver']}</td>"
            f"<td>P{int(round(r['gm_pct']))} {strip}</td>"
            f"<td>P{int(round(r['dso_pct']))}</td>"
            f"<td>P{int(round(r['ccc_pct']))}</td>"
            "</tr>"
        )
    html = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><title>CDEW 12-Company Summary</title>
<style>body{{font-family:Segoe UI,Arial,sans-serif;margin:32px;color:#152235}}
table{{border-collapse:collapse;width:100%;margin-top:16px}}th,td{{border:1px solid #d7dee6;padding:8px 10px;text-align:left}}
th{{background:#152235;color:#fff}}tr:nth-child(even){{background:#f6f8fa}}</style></head>
<body><h1>CDEW 12-Company Summary</h1>
<p>Generated {datetime.now(timezone.utc).isoformat()} | Aligned XGBoost PR-AUC {aligned['test_metrics']['xgboost']['pr_auc']:.3f} |
AUC {aligned['test_metrics']['xgboost']['auc']:.3f} | Brier {aligned['test_metrics']['xgboost']['brier']:.3f}</p>
<p>Threshold {policy['threshold']:.4f} (FN:FP {policy['fn_cost']:.0f}:{policy['fp_cost']:.0f}) |
recall {policy['test_recall']:.3f} | precision {policy['test_precision']:.3f}</p>
<table><thead><tr><th>Company</th><th>Year</th><th>Probability</th><th>Health</th><th>Grade</th>
<th>Top driver</th><th>GM Pct</th><th>DSO Pct</th><th>CCC Pct</th></tr></thead>
<tbody>{''.join(html_rows)}</tbody></table>
<p><a href="summary.md">summary.md</a></p></body></html>"""
    (eval_dir / "summary.html").write_text(html, encoding="utf-8")
    print(f"Summary written: {eval_dir / 'summary.md'} and summary.html")


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch CDEW inference (Task 10)")
    parser.add_argument("--companies", nargs="+", required=True)
    parser.add_argument("--showcases", nargs="+", default=["DemoEV", "DemoBattery", "DemoMotor"])
    parser.add_argument("--version", default="v1")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--no-summary", action="store_true")
    args = parser.parse_args()

    root = Path(args.root)
    for company in args.companies:
        result = run_cdew(
            company,
            version=args.version,
            root=root,
            force=args.force,
            augment=company in args.showcases,
        )
        print(
            f"{company}: score_written={result['score_written']} "
            f"score_skipped={result['score_skipped']} "
            f"report_written={result['report_written']}"
        )
    if not args.no_summary:
        build_summary(args.companies, args.version, root)


if __name__ == "__main__":
    main()
