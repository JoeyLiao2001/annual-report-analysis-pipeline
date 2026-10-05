"""Standalone CDEW report augmenter (Task 8).

Reads an original pipeline HTML report (read-only), inserts a CDEW analytics
section (score panel + industry percentile grid + top drivers) immediately
before Section 3, removes superseded old content (DEDUP_RULES), enhances the
Executive Summary Key Metrics table, and writes a NEW augmented report.
The original file is never modified.

Usage:
    python render_cdew_report.py --company DemoEV --version v1
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from percentile_charts import build_percentile_grid, build_score_panel, percentiles_for

ROOT = Path(__file__).resolve().parents[2]
COMPANY_INDUSTRY = {
    "DemoEV": "Industrials",
    "DemoBattery": "Industrials",
    "DemoMotor": "Industrials",
}

SECTION3_PATTERNS = [
    re.compile(r'<h2[^>]*id="s3"[^>]*>'),
    re.compile(r"<h2[^>]*>3\.\s*Strategy", re.IGNORECASE),
]

HEADING_S1 = re.compile(r'(<h2[^>]*id="s1"[^>]*>[^<]*</h2>)')
KEY_METRICS_HEADING = re.compile(
    r'(<h3[^>]*>.*?Key Metrics.*?</h3>|<div class="card-title">.*?Key Metrics.*?</div>)',
    re.IGNORECASE | re.DOTALL,
)

# Rules removing old content superseded by the CDEW section (new copy only).
DEDUP_RULES: list[dict] = [
    {
        "name": "DemoEV Risk Verdict (h3+p)",
        "note": "Superseded by the CDEW score panel and percentile grid.",
        "pattern": re.compile(r"<h3>Risk Verdict</h3>\s*<p>.*?</p>", re.DOTALL),
        "replacement": "",
    },
    {
        "name": "DemoBattery Risk Verdict (verdict div)",
        "note": "Superseded by the CDEW score panel and percentile grid.",
        "pattern": re.compile(
            r'<div class="verdict"[^>]*>\s*<strong>Risk Verdict:</strong>.*?</div>',
            re.DOTALL,
        ),
        "replacement": "",
    },
    {
        "name": "GWM Risk Verdict (card)",
        "note": "Superseded by the CDEW score panel and percentile grid.",
        "pattern": re.compile(
            r'<div class="card-title">Risk Verdict</div>.*?</div>', re.DOTALL
        ),
        "replacement": "",
    },
    {
        "name": "DemoEV standalone industry-context paragraph",
        "note": "Industry position is now shown by the percentile grid.",
        "pattern": re.compile(r"<p>Industry context is essential\..*?</p>", re.DOTALL),
        "replacement": "",
    },
]


def _b64(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode("ascii")


def _metrics_bundle(company: str, version: str, root: Path) -> dict:
    """Compute the seven grid metrics + trends from verified pipeline files."""
    vdir = root / "output" / company / version
    years = sorted(
        (p.parent.parent.name, p)
        for p in vdir.glob("Y*/finance/ratios.json")
    )
    if len(years) < 2:
        raise SystemExit(f"{company}: need at least 2 years of ratios.json")
    latest_year, latest_ratios_path = years[-1]
    prev_year, prev_ratios_path = years[-2]
    latest = json.loads(latest_ratios_path.read_text(encoding="utf-8"))
    prev = json.loads(prev_ratios_path.read_text(encoding="utf-8"))

    rev_latest = float(latest["revenue"])
    rev_prev = float(prev["revenue"])
    # The verified finance.json unit changed across years (thousands vs RMB);
    # normalize both to the same unit before computing growth.
    if rev_latest / rev_prev > 10.0:
        rev_prev = rev_prev * 1000.0
    elif rev_prev / rev_latest > 10.0:
        rev_latest = rev_latest * 1000.0
    revenue_growth_pct = (rev_latest / rev_prev - 1.0) * 100.0

    metrics = {
        "gross_margin_pct": float(latest["gross_margin_pct"]),
        "dso_days": float(latest["dso_days"]),
        "dio_days": float(latest["dio_days"]),
        "dpo_days": float(latest["dpo_days"]),
        "ccc_days": float(latest["ccc_days"]),
        "revenue_growth_pct": revenue_growth_pct,
    }

    # Debt/equity: UCI aligned X2/X10, else raw line items, else strategy gear.
    uci = None
    uci_path = vdir / latest_year / "ratios" / "uci_aligned.json"
    if uci_path.exists():
        uci = json.loads(uci_path.read_text(encoding="utf-8"))["columns"]
    if uci and "X2" in uci and "X10" in uci and uci["X10"] != 0:
        metrics["debt_to_equity"] = uci["X2"] / uci["X10"]
    else:
        raw_path = vdir / latest_year / "ratios" / "raw_line_items.json"
        if raw_path.exists():
            raw = json.loads(raw_path.read_text(encoding="utf-8"))
            items = {it["name"]: float(it["value"]) for it in raw["line_items"]}
            if items.get("equity"):
                metrics["debt_to_equity"] = (
                    items.get("total_liabilities", 0.0) / items["equity"]
                )
            else:
                strategy_path = vdir / latest_year / "strategy" / "strategy.json"
                if strategy_path.exists():
                    st = json.loads(strategy_path.read_text(encoding="utf-8"))
                    g = st.get("gearing_ratio_pct")
                    if g is None:
                        kfm = st.get("key_financial_metrics") or {}
                        g = kfm.get("gearing_ratio_pct")
                    if g is not None:
                        metrics["debt_to_equity"] = float(g) / 100.0
    if "debt_to_equity" not in metrics:
        raise SystemExit(f"{company}: cannot compute debt/equity")

    trend_rules = {
        "gross_margin_pct": True,
        "dso_days": False,
        "dio_days": False,
        "dpo_days": True,
        "ccc_days": False,
        "revenue_growth_pct": True,
        "debt_to_equity": False,
    }
    trends = {}
    prev_metrics = {
        "gross_margin_pct": float(prev["gross_margin_pct"]),
        "dso_days": float(prev["dso_days"]),
        "dio_days": float(prev["dio_days"]),
        "dpo_days": float(prev["dpo_days"]),
        "ccc_days": float(prev["ccc_days"]),
    }
    if len(years) >= 3:
        prevprev = json.loads(years[-3][1].read_text(encoding="utf-8"))
        rev_prevprev = float(prevprev["revenue"])
        if rev_prev / rev_prevprev > 10.0:
            rev_prevprev = rev_prevprev * 1000.0
        elif rev_prevprev / rev_prev > 10.0:
            rev_prev = rev_prev * 1000.0
        prev_metrics["revenue_growth_pct"] = (
            (rev_prev / rev_prevprev - 1.0) * 100.0
        )
    if uci and "X2" in uci and "X10" in uci:
        prev_uci_path = vdir / prev_year / "ratios" / "uci_aligned.json"
        if prev_uci_path.exists():
            prev_uci = json.loads(prev_uci_path.read_text(encoding="utf-8"))["columns"]
            if "X2" in prev_uci and "X10" in prev_uci and prev_uci["X10"] != 0:
                prev_metrics["debt_to_equity"] = prev_uci["X2"] / prev_uci["X10"]
    for key, good_high in trend_rules.items():
        if key not in prev_metrics:
            continue
        delta = metrics[key] - prev_metrics[key]
        if abs(delta) < 1e-9:
            trends[key] = "stable"
        else:
            improving = delta > 0 if good_high else delta < 0
            trends[key] = "improving" if improving else "deteriorating"

    return {
        "company": company,
        "version": version,
        "fiscal_year": int(latest_year[1:]),
        "industry": COMPANY_INDUSTRY.get(company, "Industrials"),
        "metrics": metrics,
        "trends": trends,
        "created_utc": datetime.now(timezone.utc).isoformat(),
    }


def _build_block(
    score: dict, metrics_path: Path, industry: str, figures_dir: Path
) -> str:
    bundle = json.loads(metrics_path.read_text(encoding="utf-8"))
    company = bundle["company"]
    score_png = figures_dir / f"{company}_score.png"
    grid_png = figures_dir / f"{company}_percentiles.png"
    build_score_panel(score, str(score_png))
    benchmarks = json.loads(
        (ROOT / "reference" / "industry_benchmarks.json").read_text(encoding="utf-8")
    )
    bench = benchmarks["industries"][industry]["benchmarks"]
    build_percentile_grid(
        bundle["metrics"], bench, str(grid_png), trends=bundle.get("trends")
    )

    drivers = score.get("top_drivers") or []
    driver_rows = "".join(
        f"<tr><td>{d['feature']}</td><td>{d['shap']:.4f}</td></tr>"
        for d in drivers
    ) or "<tr><td colspan='2'>Not available</td></tr>"
    proba = score.get("distress_probability", 0.0) or 0.0
    return f"""
<section id="cdew-analytics" style="margin: 28px 0; padding: 20px; border: 1px solid #d7dee6; border-radius: 10px; background: #f8fafc;">
  <h2 style="color:#152235; margin-top:0;">CDEW Analytics: Counterparty Distress Early-Warning</h2>
  <p style="font-size:14px; color:#43515f;">Machine-scored distress probability
  ({proba*100:.1f}%) from 25 financial-ratio features aligned to the UCI Polish
  Bankruptcy training set; industry percentiles from {industry} benchmarks
  (P10-P90). This is a quantitative early-warning signal for review, not a
  company-risk ground truth.</p>
  <div style="display:flex; flex-wrap:wrap; gap:16px; align-items:center;">
    <img src="data:image/png;base64,{_b64(score_png)}" alt="CDEW score panel" style="max-width:360px;"/>
    <img src="data:image/png;base64,{_b64(grid_png)}" alt="Industry percentile grid" style="max-width:720px;"/>
  </div>
  <h3 style="color:#152235;">Top Drivers (SHAP)</h3>
  <table style="border-collapse:collapse; width:100%; max-width:560px;">
    <thead><tr><th style="text-align:left; border-bottom:1px solid #d7dee6;">Feature</th><th style="text-align:left; border-bottom:1px solid #d7dee6;">SHAP value</th></tr></thead>
    <tbody>{driver_rows}</tbody>
  </table>
</section>
"""


def _dedup(html: str) -> str:
    """Apply DEDUP_RULES to the new copy only."""
    for rule in DEDUP_RULES:
        html = rule["pattern"].sub(rule["replacement"], html)
    return html


def _label_to_metric(label: str) -> str | None:
    lowered = label.lower()
    if "gross margin" in lowered:
        return "gross_margin_pct"
    if "revenue growth" in lowered:
        return "revenue_growth_pct"
    if "ccc" in lowered:
        return "ccc_days"
    if "dso" in lowered:
        return "dso_days"
    if "dio" in lowered:
        return "dio_days"
    if "dpo" in lowered:
        return "dpo_days"
    if "gearing" in lowered or "debt" in lowered:
        return "debt_to_equity"
    return None


def enhance_digest(
    html: str, score: dict, percentiles: dict, adapter: str = ""
) -> str:
    """Append an Industry Pct column and inject the CDEW chip (new copy)."""
    chip = (
        f'<span class="cdew-chip" style="display:inline-block; margin:0 0 10px 12px; '
        f'padding:4px 12px; border-radius:999px; background:#152235; color:#fff; '
        f'font-size:13px; font-weight:600;">CDEW {score.get("health_score", "?")} '
        f'/ {score.get("grade", "?")}</span>'
    )
    html = HEADING_S1.sub(r"\1\n" + chip, html, count=1)

    m = KEY_METRICS_HEADING.search(html)
    if not m:
        return html
    table_start = html.find("<table", m.end())
    if table_start == -1:
        return html
    table_end = html.find("</table>", table_start) + len("</table>")
    table = html[table_start:table_end]

    header_end = table.find("</tr>", table.find("<thead>")) if "<thead>" in table else -1
    if header_end == -1:
        header_end = table.find("</tr>")
    num_style = ' class="num"' if 'class="num"' in table else ""
    table = table[:header_end] + f"<th{num_style}>Industry Pct</th>" + table[header_end:]

    body = table.find("<tbody>")
    if body == -1:
        return html[:table_start] + table + html[table_end:]
    end = table.find("</tbody>", body)
    tbody = table[body:end]
    rows = list(re.finditer(r"<tr>(.*?)</tr>", tbody, re.DOTALL))
    out_rows = []
    for row in rows:
        cells = list(re.finditer(r"<td[^>]*>(.*?)</td>", row.group(1), re.DOTALL))
        label = re.sub(r"<[^>]+>", "", cells[0].group(1)).strip() if cells else ""
        metric = _label_to_metric(label)
        pct = percentiles.get(metric) if metric else None
        value = f"P{int(round(pct))}" if pct is not None else "\u2014"
        cell = f"<td{num_style}>{value}</td>"
        out_rows.append(row.group(0)[:-len("</tr>")] + cell + "</tr>")
    new_tbody = tbody
    for row, out in zip(rows, out_rows):
        new_tbody = new_tbody.replace(row.group(0), out, 1)
    table = table[:body] + new_tbody + table[end:]
    return html[:table_start] + table + html[table_end:]


def augment_report(
    report_html_path: str,
    score_path: str,
    ratios_path: str,
    benchmarks_path: str,
    out_path: str,
) -> str:
    """Insert the CDEW section into a copy of the report."""
    original = Path(report_html_path)
    html = original.read_text(encoding="utf-8")
    before = hashlib.sha256(original.read_bytes()).hexdigest()
    score = json.loads(Path(score_path).read_text(encoding="utf-8"))
    bundle = json.loads(Path(ratios_path).read_text(encoding="utf-8"))
    figures_dir = Path(ratios_path).parent
    block = _build_block(score, Path(ratios_path), bundle["industry"], figures_dir)
    benchmarks = json.loads(
        (ROOT / "reference" / "industry_benchmarks.json").read_text(encoding="utf-8")
    )["industries"][bundle["industry"]]["benchmarks"]
    percentiles = percentiles_for(bundle["metrics"], benchmarks)

    anchor = None
    for pattern in SECTION3_PATTERNS:
        m = pattern.search(html)
        if m:
            anchor = m.start()
            break
    if anchor is None:
        anchor = html.find("</body>")
        if anchor == -1:
            raise SystemExit("Cannot find Section 3 or </body> in report")

    new_html = html[:anchor] + block + "\n" + html[anchor:]
    new_html = _dedup(new_html)
    new_html = enhance_digest(new_html, score, percentiles, adapter=bundle.get("company", ""))
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(new_html, encoding="utf-8")
    after = hashlib.sha256(original.read_bytes()).hexdigest()
    if before != after:
        raise RuntimeError("Original report was modified during augmentation!")
    return str(out)


def main() -> None:
    parser = argparse.ArgumentParser(description="CDEW report augmenter (Task 8)")
    parser.add_argument("--company", required=True)
    parser.add_argument("--version", default="v1")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--industry", default=None,
                        help="Override the industry benchmark mapping")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    root = Path(args.root)
    vdir = root / "output" / args.company / args.version

    score_path = vdir / "cross_year" / "distress_score.json"
    if not score_path.exists():
        raise SystemExit(f"Missing {score_path}; run infer.py first")
    score = json.loads(score_path.read_text(encoding="utf-8"))
    industry = args.industry or COMPANY_INDUSTRY.get(args.company, "Industrials")
    if args.company == "DemoEV":
        flags_path = vdir / "cross_year" / "industry_flags.json"
        if flags_path.exists():
            industry = json.loads(flags_path.read_text(encoding="utf-8")).get(
                "industry", industry
            )

    figures_dir = root / "output" / "_cdew" / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)
    bundle = _metrics_bundle(args.company, args.version, root)
    bundle["industry"] = industry
    metrics_path = figures_dir / f"{args.company}_metrics.json"
    metrics_path.write_text(json.dumps(bundle, indent=2), encoding="utf-8")

    report_html = vdir / f"{args.company}_3Y_Report.html"
    out_html = (
        root / "output" / "_cdew" / "reports"
        / f"{args.company}_{args.version}_3Y_Report_CDEW.html"
    )
    if out_html.exists() and not args.force:
        print(f"Exists (skip): {out_html}")
        return

    out = augment_report(
        str(report_html), str(score_path), str(metrics_path), str(industry), str(out_html)
    )
    print(f"Augmented report written: {out}")


if __name__ == "__main__":
    main()
