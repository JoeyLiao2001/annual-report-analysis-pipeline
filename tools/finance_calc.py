"""Standalone financial ratio calculator for Wholesale Banking Agent Pipeline.

Ports the computation logic from 03_Code_Calc.py into a pure function
that takes a pre-parsed dict of raw metrics and returns computed ratios.
"""

from __future__ import annotations

from typing import Any


def _val(data: dict, key: str, default=-999.0) -> float:
    """Extract a numeric value, handling both old flat format and new {value, page} format."""
    v = data.get(key, default)
    if isinstance(v, dict):
        return float(v.get("value", default))
    return float(v)


def calculate_ratios(finance_json: dict) -> dict[str, Any]:
    """Compute financial ratios from raw extracted metrics.

    Input: {"revenue": float | {"value": float, "page": int}, ...}

    Returns: {"revenue": float, "cogs": float, "gross_margin_pct": float,
              "dso_days": float, "dio_days": float, "dpo_days": float,
              "ccc_days": float, "is_negative_wc": bool}

    Uses -999.0 sentinel for missing values (if any metric is -999.0,
    derived metrics become -999.0).
    """
    revenue = _val(finance_json, "revenue")
    cogs = _val(finance_json, "cogs")
    ar_start = _val(finance_json, "ar_start")
    ar_end = _val(finance_json, "ar_end")
    inv_start = _val(finance_json, "inv_start")
    inv_end = _val(finance_json, "inv_end")
    ap_start = _val(finance_json, "ap_start")
    ap_end = _val(finance_json, "ap_end")

    result: dict[str, Any] = {}

    # Always pass through raw revenue and cogs
    result["revenue"] = revenue
    result["cogs"] = cogs

    # Negative working capital check (AP > AR + Inventory at period end)
    if ap_end != -999.0 and ar_end != -999.0 and inv_end != -999.0:
        result["is_negative_wc"] = ap_end > (ar_end + inv_end)
    else:
        result["is_negative_wc"] = False

    # Gross margin
    if revenue > 0 and cogs != -999.0 and cogs >= 0:
        gross_profit = revenue - cogs
        result["gross_margin_pct"] = round((gross_profit / revenue) * 100, 2)
    else:
        result["gross_margin_pct"] = -999.0

    # DSO
    if revenue > 0 and ar_start != -999.0 and ar_end != -999.0:
        avg_ar = (ar_start + ar_end) / 2.0
        result["dso_days"] = round((avg_ar / revenue) * 365.0, 2)
    else:
        result["dso_days"] = -999.0

    # DIO
    if cogs > 0 and inv_start != -999.0 and inv_end != -999.0:
        avg_inv = (inv_start + inv_end) / 2.0
        result["dio_days"] = round((avg_inv / cogs) * 365.0, 2)
    else:
        result["dio_days"] = -999.0

    # DPO
    if cogs > 0 and ap_start != -999.0 and ap_end != -999.0:
        avg_ap = (ap_start + ap_end) / 2.0
        result["dpo_days"] = round((avg_ap / cogs) * 365.0, 2)
    else:
        result["dpo_days"] = -999.0

    # CCC
    if result["dso_days"] != -999.0 and result["dio_days"] != -999.0 and result["dpo_days"] != -999.0:
        result["ccc_days"] = round(result["dso_days"] + result["dio_days"] - result["dpo_days"], 2)
    else:
        result["ccc_days"] = -999.0

    return result


if __name__ == "__main__":
    sample = {
        "revenue": 1000,
        "cogs": 600,
        "ar_start": 100,
        "ar_end": 120,
        "inv_start": 80,
        "inv_end": 90,
        "ap_start": 50,
        "ap_end": 60,
    }
    result = calculate_ratios(sample)
    for k, v in result.items():
        print(f"  {k}: {v}")
