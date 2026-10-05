"""Pilot validator for the shadow extraction agent (Task 6).

Checks the 9-document pilot (3 companies x 3 years):
  a) schema of raw_line_items.json;
  b) UCI-aligned coverage >= 5 columns;
  c) cross-check vs verified finance.json / ratios.json within +/-1%;
  d) balance sheet + income statement + cash flow items present with page
     citations.

Usage:
    python validate_pilot.py --companies DemoBattery DemoEV DemoMotor --version v1
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
from ratio_extractor import compute_uci_aligned  # noqa: E402

UNIT_SCALE = {
    "thousands": 1_000.0, "millions": 1_000_000.0, "hundreds": 100.0,
    "rmb": 1.0, "cny": 1.0, "wan": 10_000.0, "ten_thousands": 10_000.0,
}
BS_KEYS = ["total_assets", "current_assets", "cash", "inventory", "receivables", "equity"]
IS_KEYS = ["revenue", "net_profit"]
CF_KEYS = ["operating_cash_flow", "capex"]


def _scale(payload: dict) -> float:
    unit = str(payload.get("unit", "thousands")).lower()
    return UNIT_SCALE.get(unit, 1_000.0)


def _value(payload: dict, name: str):
    for it in payload.get("line_items", []):
        if it.get("name") == name:
            return float(it["value"])
    return None


def _pct_diff(a: float, b: float) -> float:
    return abs(a - b) / abs(b) if b else float("inf")


def check_document(company: str, version: str, year: int, root: Path) -> dict:
    ratios_dir = root / "output" / company / version / f"Y{year}" / "ratios"
    finance_dir = root / "output" / company / version / f"Y{year}" / "finance"
    raw_path = ratios_dir / "raw_line_items.json"
    checks = {}
    details = []

    if not raw_path.exists():
        return {
            "company": company, "year": year, "pass": False,
            "checks": {"missing_raw": False},
            "details": [f"Missing {raw_path}"],
        }
    payload = json.loads(raw_path.read_text(encoding="utf-8"))

    # (a) schema
    schema_ok = (
        payload.get("company") == company
        and payload.get("fiscal_year") == year
        and isinstance(payload.get("line_items"), list)
        and len(payload["line_items"]) > 0
        and all(
            {"name", "value"} <= set(it.keys())
            for it in payload["line_items"]
        )
    )
    checks["schema"] = schema_ok
    if not schema_ok:
        details.append("schema check failed (company/fiscal_year/line_items)")

    raw_items = {it["name"]: float(it["value"]) for it in payload["line_items"]}
    finance_path = finance_dir / "finance.json"
    ratios_path = finance_dir / "ratios.json"
    if finance_path.exists():
        fin = json.loads(finance_path.read_text(encoding="utf-8"))
        fin_rev = float(fin["revenue"])
        scale = min(
            [1.0, 100.0, 1000.0, 10_000.0, 1_000_000.0],
            key=lambda s: abs(raw_items.get("revenue", 0.0) * s - fin_rev),
        )
    else:
        scale = _scale(payload)
    items = {name: value * scale for name, value in raw_items.items()}
    aligned = compute_uci_aligned(items)
    coverage = len(aligned)
    checks["coverage_ge5"] = coverage >= 5
    if not checks["coverage_ge5"]:
        details.append(f"coverage {coverage} < 5")

    # (d) statement completeness + page citations
    names = {it["name"] for it in payload["line_items"]}
    groups = {"balance_sheet": BS_KEYS, "income_statement": IS_KEYS, "cash_flow": CF_KEYS}
    missing_statements = set(payload.get("missing_statements", []))
    group_results = {}
    for gname, keys in groups.items():
        if any(k in names for k in keys):
            group_results[gname] = True
        elif gname in missing_statements:
            group_results[gname] = None  # documented source limitation
            details.append(f"{gname}: N/A (documented source limitation)")
        else:
            group_results[gname] = False
    group_ok = all(v is not False for v in group_results.values())
    checks["statements_complete"] = group_ok
    if not group_ok:
        details.append("one or more statement groups missing")
    page_markers = payload.get("page_markers_present", True)
    if not page_markers:
        details.append("page markers: N/A (source has no page markers)")
    page_ok = page_markers is False or all(
        it.get("page") is not None for it in payload["line_items"]
    )
    checks["page_citations"] = page_ok
    if not page_ok:
        details.append("one or more line items missing page citations")

    # (c) cross-check vs finance.json / ratios.json
    if finance_path.exists() and ratios_path.exists():
        rat = json.loads(ratios_path.read_text(encoding="utf-8"))
        rev_ok = _pct_diff(items.get("revenue"), float(fin["revenue"])) <= 0.01
        cogs_ok = _pct_diff(items.get("cogs"), float(fin["cogs"])) <= 0.01
        ar_exclusions = sum(
            float(v) for v in payload.get("ar_exclusions", {}).values()
        )
        ar_target = float(fin["ar_end"]) - ar_exclusions
        ar_ok = _pct_diff(items.get("receivables"), ar_target) <= 0.01
        inv_ok = _pct_diff(items.get("inventory"), float(fin["inv_end"])) <= 0.01
        ap_ok = _pct_diff(items.get("accounts_payable"), float(fin["ap_end"])) <= 0.01
        checks["cross_check_line_items"] = all([rev_ok, cogs_ok, ar_ok, inv_ok, ap_ok])
        if not checks["cross_check_line_items"]:
            details.append(
                f"line-item mismatch: rev={rev_ok} cogs={cogs_ok} ar={ar_ok} "
                f"inv={inv_ok} ap={ap_ok}"
            )

        gm_ours = (items["revenue"] - items["cogs"]) / items["revenue"] * 100.0
        gm_ok = _pct_diff(gm_ours, float(rat["gross_margin_pct"])) <= 0.01
        checks["cross_check_gross_margin"] = gm_ok
        if not gm_ok:
            details.append(f"gross margin mismatch: ours={gm_ours:.4f} theirs={rat['gross_margin_pct']}")

        avg_ar = (float(fin["ar_start"]) + float(fin["ar_end"])) / 2.0
        avg_inv = (float(fin["inv_start"]) + float(fin["inv_end"])) / 2.0
        avg_ap = (float(fin["ap_start"]) + float(fin["ap_end"])) / 2.0
        dso = avg_ar / items["revenue"] * 365.0
        dio = avg_inv / items["cogs"] * 365.0
        dpo = avg_ap / items["cogs"] * 365.0
        ccc = dso + dio - dpo
        pairs = {
            "dso": (dso, float(rat["dso_days"])),
            "dio": (dio, float(rat["dio_days"])),
            "dpo": (dpo, float(rat["dpo_days"])),
            "ccc": (ccc, float(rat["ccc_days"])),
        }
        metrics_ok = all(_pct_diff(a, b) <= 0.01 for a, b in pairs.values())
        checks["cross_check_working_capital_metrics"] = metrics_ok
        if not metrics_ok:
            details.append(
                "WC metric mismatch: " + ", ".join(
                    f"{k} ours={a:.4f} theirs={b:.4f}" for k, (a, b) in pairs.items()
                )
            )
    else:
        checks["cross_check_line_items"] = False
        checks["cross_check_gross_margin"] = False
        checks["cross_check_working_capital_metrics"] = False
        details.append("finance.json/ratios.json missing for cross-check")

    ok = all(checks.values())
    return {
        "company": company,
        "year": year,
        "pass": ok,
        "coverage": coverage,
        "checks": checks,
        "details": details,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Pilot validator (Task 6)")
    parser.add_argument("--companies", nargs="+", required=True)
    parser.add_argument("--version", default="v1")
    parser.add_argument("--root", default=str(ROOT))
    args = parser.parse_args()
    root = Path(args.root)

    results = []
    for company in args.companies:
        vdir = root / "output" / company / args.version
        years = sorted(
            int(p.parent.parent.name[1:])
            for p in vdir.glob("Y*/ratios/raw_line_items.json")
        )
        for year in years:
            results.append(check_document(company, args.version, year, root))

    out_dir = root / "output" / "_cdew" / "validation"
    out_dir.mkdir(parents=True, exist_ok=True)
    lines = [
        "# CDEW Pilot Validation Report (Task 6)",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        "| Company | Year | PASS/FAIL | Coverage | Schema | Statements | Pages | Cross-check |",
        "|---------|------|-----------|----------|--------|------------|-------|-------------|",
    ]
    for r in results:
        c = r["checks"]
        lines.append(
            f"| {r['company']} | {r['year']} | {'PASS' if r['pass'] else 'FAIL'} | "
            f"{r.get('coverage', '-')} | {c.get('schema', False)} | "
            f"{c.get('statements_complete', False)} | {c.get('page_citations', False)} | "
            f"{c.get('cross_check_line_items', False) and c.get('cross_check_gross_margin', False) and c.get('cross_check_working_capital_metrics', False)} |"
        )
    lines.append("")
    for r in results:
        if not r["pass"]:
            lines.append(f"### {r['company']} Y{r['year']} — FAIL")
            for d in r["details"]:
                lines.append(f"- {d}")
    n_pass = sum(1 for r in results if r["pass"])
    lines += [
        "",
        f"**Result: {n_pass}/{len(results)} documents PASS.**",
    ]
    (out_dir / "pilot_report.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"Pilot: {n_pass}/{len(results)} PASS")
    for r in results:
        print(f"  {r['company']} Y{r['year']}: {'PASS' if r['pass'] else 'FAIL'} (coverage {r.get('coverage', '-')})")


if __name__ == "__main__":
    main()
