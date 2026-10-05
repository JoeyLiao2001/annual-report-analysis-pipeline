"""Deterministic UCI-aligned ratio calculator (Task 6).

Computes every UCI Polish Bankruptcy column (X1..X64) whose numerator and
denominator line items are present in the shadow-extracted raw line items.
Columns with missing inputs or a zero denominator are omitted (never
zero-filled). Raw line items are extracted by the `extract-ratios` agent;
this script performs arithmetic only.

Usage:
    python ratio_extractor.py --company DemoEV --version v1 --year 2025 [--write]
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DICT_PATH = ROOT / "tools" / "distress_model" / "uci_feature_dict.json"

_DICT = json.loads(DICT_PATH.read_text(encoding="utf-8"))
FEASIBILITY: dict[str, list[str]] = {
    key: list(meta["requires"]) for key, meta in _DICT.items() if key.startswith("X")
}


def _derive(items: dict[str, float]) -> dict[str, float]:
    """Add computed intermediate keys used by the UCI formulas."""
    d = dict(items)
    if "gross_profit" not in d and "revenue" in d and "cogs" in d:
        d["gross_profit"] = d["revenue"] - d["cogs"]
    op_keys = [
        "cogs", "taxes_surcharges", "selling_expense", "admin_expense",
        "rnd_expense", "finance_expense",
    ]
    if "operating_expenses" not in d and all(k in d for k in op_keys):
        d["operating_expenses"] = sum(d[k] for k in op_keys)
    if "retained_earnings" not in d and "surplus_reserve" in d and "undistributed_profit" in d:
        d["retained_earnings"] = d["surplus_reserve"] + d["undistributed_profit"]
    if "cash_and_short_term" not in d and "cash" in d:
        d["cash_and_short_term"] = d["cash"] + d.get("trading_financial_assets", 0.0)
    if "working_capital" not in d and "current_assets" in d and "current_liabilities" in d:
        d["working_capital"] = d["current_assets"] - d["current_liabilities"]
    if "constant_capital" not in d and "equity" in d and "long_term_liabilities" in d:
        d["constant_capital"] = d["equity"] + d["long_term_liabilities"]
    dep_keys = [
        "depreciation_fixed", "depreciation_right_of_use",
        "depreciation_investment_property", "amortization_intangible",
        "amortization_long_term_deferred",
    ]
    if "depreciation" not in d and any(k in d for k in dep_keys):
        d["depreciation"] = sum(d.get(k, 0.0) for k in dep_keys)
    if "ebit" not in d and "operating_profit" in d:
        d["ebit"] = d["operating_profit"] + d.get("interest_expense", 0.0)
    return d


def _div(num, den):
    if den is None or den == 0.0:
        return None
    return num / den


def _f(d: dict[str, float], key: str):
    return d.get(key)


def _formulas(d: dict[str, float]) -> dict[str, float]:
    out: dict[str, float] = {}
    g = lambda k: d.get(k)  # noqa: E731 - short local accessor

    def put(x: str, num, den):
        if num is None or den is None:
            return
        v = _div(num, den)
        if v is not None:
            out[x] = v

    put("X1", g("net_profit"), g("total_assets"))
    put("X2", g("total_liabilities"), g("total_assets"))
    put("X3", g("working_capital"), g("total_assets"))
    put("X4", g("current_assets"), g("current_liabilities"))
    num5 = None
    if (g("cash_and_short_term") is not None and g("receivables") is not None
            and g("current_liabilities") is not None):
        num5 = g("cash_and_short_term") + g("receivables") - g("current_liabilities")
    den5 = None
    if g("operating_expenses") is not None and g("depreciation") is not None:
        den5 = g("operating_expenses") - g("depreciation")
    if num5 is not None and den5 is not None and den5 != 0:
        out["X5"] = num5 * 365.0 / den5
    put("X6", g("retained_earnings"), g("total_assets"))
    put("X7", g("ebit"), g("total_assets"))
    put("X8", g("equity"), g("total_liabilities"))
    put("X9", g("revenue"), g("total_assets"))
    put("X10", g("equity"), g("total_assets"))
    if g("gross_profit") is not None and g("finance_expense") is not None and g("total_assets") is not None:
        put("X11", g("gross_profit") + g("finance_expense"), g("total_assets"))
    put("X12", g("gross_profit"), g("current_liabilities"))
    if g("gross_profit") is not None and g("depreciation") is not None and g("revenue") is not None:
        put("X13", g("gross_profit") + g("depreciation"), g("revenue"))
    if g("gross_profit") is not None and g("interest_expense") is not None and g("total_assets") is not None:
        put("X14", g("gross_profit") + g("interest_expense"), g("total_assets"))
    if g("total_liabilities") is not None and g("gross_profit") is not None and g("depreciation") is not None:
        put("X15", g("total_liabilities") * 365.0, g("gross_profit") + g("depreciation"))
    if g("gross_profit") is not None and g("depreciation") is not None and g("total_liabilities") is not None:
        put("X16", g("gross_profit") + g("depreciation"), g("total_liabilities"))
    put("X17", g("total_assets"), g("total_liabilities"))
    put("X18", g("gross_profit"), g("total_assets"))
    put("X19", g("gross_profit"), g("revenue"))
    put("X20", None if g("inventory") is None else g("inventory") * 365.0, g("revenue"))
    put("X21", g("revenue"), g("revenue_prior_year"))
    put("X22", g("operating_profit"), g("total_assets"))
    put("X23", g("net_profit"), g("revenue"))
    # X24 requires a 3-year gross profit series; omitted from single-year payloads.
    if g("equity") is not None and g("share_capital") is not None and g("total_assets") is not None:
        put("X25", g("equity") - g("share_capital"), g("total_assets"))
    if g("net_profit") is not None and g("depreciation") is not None and g("total_liabilities") is not None:
        put("X26", g("net_profit") + g("depreciation"), g("total_liabilities"))
    put("X27", g("operating_profit"), g("finance_expense"))
    put("X28", g("working_capital"), g("fixed_assets"))
    if g("total_assets") is not None and g("total_assets") > 0:
        out["X29"] = math.log(g("total_assets"))
    if g("total_liabilities") is not None and g("cash") is not None and g("revenue") is not None:
        put("X30", g("total_liabilities") - g("cash"), g("revenue"))
    if g("gross_profit") is not None and g("interest_expense") is not None and g("revenue") is not None:
        put("X31", g("gross_profit") + g("interest_expense"), g("revenue"))
    put("X32", None if g("current_liabilities") is None else g("current_liabilities") * 365.0, g("cogs"))
    put("X33", g("operating_expenses"), g("current_liabilities"))
    put("X34", g("operating_expenses"), g("total_liabilities"))
    put("X35", g("gross_profit"), g("total_assets"))
    put("X36", g("revenue"), g("total_assets"))
    if g("current_assets") is not None and g("inventory") is not None and g("long_term_liabilities") is not None:
        put("X37", g("current_assets") - g("inventory"), g("long_term_liabilities"))
    put("X38", g("constant_capital"), g("total_assets"))
    put("X39", g("gross_profit"), g("revenue"))
    if g("current_assets") is not None and g("inventory") is not None and g("receivables") is not None and g("current_liabilities") is not None:
        put("X40", g("current_assets") - g("inventory") - g("receivables"), g("current_liabilities"))
    if g("total_liabilities") is not None and g("operating_profit") is not None and g("depreciation") is not None:
        put("X41", g("total_liabilities"), (g("operating_profit") + g("depreciation")) * (12.0 / 365.0))
    put("X42", g("operating_profit"), g("revenue"))
    if g("receivables") is not None and g("inventory") is not None and g("revenue") is not None and g("cogs") is not None:
        put("X43", g("receivables") * 365.0 / g("revenue") + g("inventory") * 365.0 / g("cogs"), 1.0)
    put("X44", None if g("receivables") is None else g("receivables") * 365.0, g("revenue"))
    put("X45", g("net_profit"), g("inventory"))
    if g("current_assets") is not None and g("inventory") is not None and g("current_liabilities") is not None:
        put("X46", g("current_assets") - g("inventory"), g("current_liabilities"))
    put("X47", None if g("inventory") is None else g("inventory") * 365.0, g("cogs"))
    if g("operating_profit") is not None and g("depreciation") is not None and g("total_assets") is not None:
        put("X48", g("operating_profit") - g("depreciation"), g("total_assets"))
    if g("operating_profit") is not None and g("depreciation") is not None and g("revenue") is not None:
        put("X49", g("operating_profit") - g("depreciation"), g("revenue"))
    put("X50", g("current_assets"), g("total_liabilities"))
    put("X51", g("current_liabilities"), g("total_assets"))
    put("X52", None if g("current_liabilities") is None else g("current_liabilities") * 365.0, g("cogs"))
    put("X53", g("equity"), g("fixed_assets"))
    put("X54", g("constant_capital"), g("fixed_assets"))
    if g("working_capital") is not None:
        out["X55"] = g("working_capital")
    put("X56", g("gross_profit"), g("revenue"))
    if (g("current_assets") is not None and g("inventory") is not None
            and g("current_liabilities") is not None and g("revenue") is not None
            and g("gross_profit") is not None and g("depreciation") is not None):
        put("X57", g("current_assets") - g("inventory") - g("current_liabilities"),
            g("revenue") - g("gross_profit") - g("depreciation"))
    put("X58", g("operating_expenses"), g("revenue"))
    put("X59", g("long_term_liabilities"), g("equity"))
    put("X60", g("revenue"), g("inventory"))
    put("X61", g("revenue"), g("receivables"))
    put("X62", None if g("current_liabilities") is None else g("current_liabilities") * 365.0, g("revenue"))
    put("X63", g("revenue"), g("current_liabilities"))
    put("X64", g("revenue"), g("fixed_assets"))
    return {k: float(v) for k, v in out.items()}


def compute_uci_aligned(line_items: dict[str, float]) -> dict[str, float]:
    """Compute every UCI column computable from the supplied line items."""
    derived = _derive(line_items)
    return _formulas(derived)


def main() -> None:
    parser = argparse.ArgumentParser(description="UCI-aligned ratio calculator (Task 6)")
    parser.add_argument("--company", required=True)
    parser.add_argument("--version", default="v1")
    parser.add_argument("--year", required=True)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--root", default=str(ROOT))
    args = parser.parse_args()

    ratios_dir = Path(args.root) / "output" / args.company / args.version / f"Y{args.year}" / "ratios"
    raw_path = ratios_dir / "raw_line_items.json"
    if not raw_path.exists():
        raise SystemExit(f"Missing {raw_path}")
    payload = json.loads(raw_path.read_text(encoding="utf-8"))
    items = {it["name"]: float(it["value"]) for it in payload["line_items"]}
    aligned = compute_uci_aligned(items)
    result = {
        "company": payload.get("company", args.company),
        "version": payload.get("version", args.version),
        "fiscal_year": payload.get("fiscal_year", int(args.year)),
        "n_computable": len(aligned),
        "columns": {k: round(v, 8) for k, v in sorted(aligned.items())},
        "created_utc": datetime.now(timezone.utc).isoformat(),
    }
    if args.write:
        (ratios_dir / "uci_aligned.json").write_text(
            json.dumps(result, indent=2), encoding="utf-8"
        )
    print(f"{args.company} Y{args.year}: {len(aligned)} computable UCI columns")
    print(", ".join(sorted(aligned.keys())))


if __name__ == "__main__":
    main()
