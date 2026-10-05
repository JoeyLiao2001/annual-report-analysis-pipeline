#!/usr/bin/env python3
"""industry_benchmark.py — Industry financial benchmark comparison tool.

Deterministic (zero LLM tokens, zero network calls) Python tool that reads
3-year financial ratio data + Router industry classification + static benchmark data,
then computes industry-position flags.

Runs during every pipeline execution, AFTER contradiction_calc.py.

Usage:
    python tools/industry_benchmark.py <company> [version]

Output:
    output/{company}/{version}/cross_year/industry_flags.json

Algorithm:
    Pass A — Static Position (Y3 only): percentile bucketing vs industry benchmarks
    Pass B — Trend x Position Matrix: 3-year trajectory combined with static position
    Severity Downgrade: all severities reduced one tier (Damodaran US/EU bias)
      unless confirmed by contradiction_calc cross-reference
    Industry Mismatch Warning: if >=3 of 7 metrics outside P5-P95 range
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Optional, Union

# ═══════════════════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════════════════

ROOT = Path(__file__).resolve().parent.parent

METRIC_NAMES = [
    "gross_margin_pct",
    "dso_days",
    "dio_days",
    "dpo_days",
    "ccc_days",
    "revenue_growth_pct",
    "debt_to_equity",
]

METRIC_DIRECTION: dict[str, str] = {
    "gross_margin_pct": "higher_better",
    "dso_days": "lower_better",
    "dio_days": "lower_better",
    "dpo_days": "lower_better",
    "ccc_days": "lower_better",
    "revenue_growth_pct": "higher_better",
    "debt_to_equity": "lower_better",
}

METRIC_TO_CONTRADICTION_KEYWORD: dict[str, str] = {
    "gross_margin_pct": "margin",
    "dso_days": "DSO",
    "dio_days": "DIO",
    "dpo_days": "DPO",
    "ccc_days": "CCC",
    "revenue_growth_pct": "Revenue",
    "debt_to_equity": "debt",
}

# Static fallback when router provides no industry field.
# Based on actual pipeline runs and a Damodaran→bank-sector mapping.
COMPANY_INDUSTRY_MAP: dict[str, str] = {
    "DemoConstruct": "Construction and Infrastructure",
    "DemoEV": "Industrials",
    "DemoBattery": "Industrials",
    "DemoMotor": "Industrials",
    "DemoAppliance": "Consumer Goods and Healthcare",
    "DemoInfra": "Construction and Infrastructure",
    "DemoLogistics": "Industrials",
    "DemoHVAC": "Consumer Goods and Healthcare",
    "DemoFreight": "Industrials",
    "DemoChemicals": "Energy and Chemicals",
    "DemoElectronics": "Telecom Media and Technology",
    "DemoMetals": "Industrials",
}

POSITION_TREND_MATRIX: dict = {
    # (position, trend) -> (cell_label, combined_severity)
    ("above_peer", "improving"): ("STRONG_LEADER", "LOW"),
    ("above_peer", "stable"): ("ELEVATED", "LOW"),
    ("above_peer", "deteriorating"): ("WATCH_LOSS", "HIGH"),
    ("within_range", "improving"): ("CATCHING_UP", "LOW"),
    ("within_range", "stable"): ("NORMAL", None),
    ("within_range", "deteriorating"): ("FALLING_BEHIND", "MEDIUM"),
    ("below_peer", "improving"): ("RECOVERING", "LOW"),
    ("below_peer", "stable"): ("WEAKNESS", "HIGH"),
    ("below_peer", "deteriorating"): ("WEAKNESS", "HIGH"),
}

SEVERITY_DOWNGRADE: dict[str, Optional[str]] = {
    "HIGH": "MEDIUM",
    "MEDIUM": "LOW",
    "LOW": None,
}

BUCKET_LABELS: dict[str, str] = {
    "below_p10": "<P10",
    "p10_p25": "P10-P25",
    "p25_p75": "P25-P75",
    "p75_p90": "P75-P90",
    "above_p90": ">P90",
}

# ═══════════════════════════════════════════════════════
# Helper: extract value from {value, page} dict or plain
# ═══════════════════════════════════════════════════════


def _val(data: dict, key: str, default: float = -999.0) -> float:
    """Extract a numeric value, handling {value, page} dict and plain formats."""
    v = data.get(key, default)
    if isinstance(v, dict):
        return float(v.get("value", default))
    if v is None:
        return default
    return float(v)


# ═══════════════════════════════════════════════════════
# Pass A: Static Position (Y3 only)
# ═══════════════════════════════════════════════════════


def find_percentile_bucket(
    value: float, percentiles: dict[str, float]
) -> tuple[str, float]:
    """Determine which percentile bucket a value falls into.

    Args:
        value: The company's metric value.
        percentiles: Dict with p10, p25, p50, p75, p90.

    Returns:
        (bucket_label, approximate_percentile) where bucket_label is one of:
        below_p10, p10_p25, p25_p75, p75_p90, above_p90.
    """
    p10 = percentiles["p10"]
    p25 = percentiles["p25"]
    p50 = percentiles["p50"]
    p75 = percentiles["p75"]
    p90 = percentiles["p90"]

    if value < p10:
        # Interpolate between 0 and P10
        if p10 > 0:
            approx = max(0.0, min(9.0, 10.0 * value / p10))
        else:
            approx = 0.0
        return ("below_p10", round(approx, 1))

    elif value < p25:
        # Interpolate between P10 and P25
        if p25 > p10:
            approx = 10.0 + 15.0 * (value - p10) / (p25 - p10)
        else:
            approx = 17.5
        return ("p10_p25", round(approx, 1))

    elif value < p50:
        if p50 > p25:
            approx = 25.0 + 25.0 * (value - p25) / (p50 - p25)
        else:
            approx = 37.5
        return ("p25_p75", round(approx, 1))

    elif value < p75:
        if p75 > p50:
            approx = 50.0 + 25.0 * (value - p50) / (p75 - p50)
        else:
            approx = 62.5
        return ("p25_p75", round(approx, 1))

    elif value < p90:
        if p90 > p75:
            approx = 75.0 + 15.0 * (value - p75) / (p90 - p75)
        else:
            approx = 82.5
        return ("p75_p90", round(approx, 1))

    else:
        # value >= P90
        if p90 > p75:
            approx = 90.0 + 9.0 * (value - p90) / (p90 - p75)
        else:
            approx = 95.0
        approx = min(approx, 99.9)
        return ("above_p90", round(approx, 1))


def compute_static_position(
    bucket: str, metric: str
) -> tuple[str, Optional[str]]:
    """Convert percentile bucket to static category and severity.

    Bidirectional: both too-low AND too-high are flagged.

    Returns:
        (static_category, static_severity_raw)
    """
    direction = METRIC_DIRECTION.get(metric, "lower_better")

    if bucket == "below_p10":
        sev = "HIGH"
        if direction == "lower_better":
            # Lower is better, so below_p10 means exceptionally good (low)
            # But the task says BIDIRECTIONAL: both too low and too high flagged
            cat = "below_peer"
        else:
            # Higher is better, so below_p10 means bad
            cat = "below_peer"
        return (cat, sev)

    elif bucket == "p10_p25":
        sev = "MEDIUM"
        if direction == "lower_better":
            # Lower = good, P10-P25 is somewhat good
            cat = "below_peer"
        else:
            cat = "below_peer"
        return (cat, sev)

    elif bucket == "p25_p75":
        return ("within_range", None)

    elif bucket == "p75_p90":
        sev = "MEDIUM"
        if direction == "lower_better":
            # Lower = good, high = bad
            cat = "above_peer"
        else:
            # Higher = good, high = good
            cat = "above_peer"
        return (cat, sev)

    elif bucket == "above_p90":
        sev = "HIGH"
        if direction == "lower_better":
            cat = "above_peer"
        else:
            cat = "above_peer"
        return (cat, sev)

    return ("within_range", None)


# ═══════════════════════════════════════════════════════
# Pass B: Trend Computation
# ═══════════════════════════════════════════════════════


def compute_trend(
    y1: float, y2: float, y3: float, direction: str
) -> tuple[str, float, bool]:
    """Compute 3-year trend direction and severity.

    Args:
        y1, y2, y3: Metric values for years 1 through 3.
        direction: 'higher_better' or 'lower_better'.

    Returns:
        (trend_direction, pct_change_y1_to_y3, is_monotonic_upgrade)
        trend_direction is one of: 'improving', 'stable', 'deteriorating'.
    """
    # Y1 -> Y3 percentage change
    if y1 != 0 and y1 != -999.0:
        pct_change = round(((y3 - y1) / abs(y1)) * 100, 1)
    else:
        pct_change = 0.0

    abs_pct = abs(pct_change)

    # Check monotonicity over 3 years (>10% cumulative Y1->Y3)
    monotonic_increasing = (y3 >= y2 >= y1) and abs_pct > 10
    monotonic_decreasing = (y3 <= y2 <= y1) and abs_pct > 10

    # Determine direction
    if abs_pct < 5.0:
        direction_label = "stable"
        is_upgraded = False
    elif direction == "lower_better":
        # For DSO/DIO/DPO/CCC/D_E: decrease = improvement
        if pct_change < -5.0:
            direction_label = "improving"
        elif pct_change > 5.0:
            direction_label = "deteriorating"
        else:
            direction_label = "stable"
        is_upgraded = monotonic_decreasing
    elif direction == "higher_better":
        # For GM/Revenue Growth: increase = improvement
        if pct_change > 5.0:
            direction_label = "improving"
        elif pct_change < -5.0:
            direction_label = "deteriorating"
        else:
            direction_label = "stable"
        is_upgraded = monotonic_increasing
    else:
        direction_label = "stable"
        is_upgraded = False

    return (direction_label, pct_change, is_upgraded)


def compute_position_trend_cell(
    static_category: str, trend_direction: str
) -> tuple[str, Optional[str]]:
    """Look up position x trend matrix cell.

    Returns:
        (cell_label, combined_severity) where severity is HIGH/MEDIUM/LOW/None.
    """
    key = (static_category, trend_direction)
    return POSITION_TREND_MATRIX.get(key, ("UNKNOWN", None))


# ═══════════════════════════════════════════════════════
# Severity Downgrade Logic
# ═══════════════════════════════════════════════════════


def check_contradiction_calc_confirmation(
    metric: str, quant_flags: dict
) -> bool:
    """Check if a metric is confirmed by contradiction_calc.py output.

    Looks through all contradiction flags for a matching keyword.
    """
    keyword = METRIC_TO_CONTRADICTION_KEYWORD.get(metric, "")
    if not keyword:
        return False

    flags_str = quant_flags.get("contradiction_flags", "[]")
    if isinstance(flags_str, str):
        try:
            flags_list = json.loads(flags_str)
        except (json.JSONDecodeError, TypeError):
            return False
    elif isinstance(flags_str, list):
        flags_list = flags_str
    else:
        return False

    keyword_lower = keyword.lower()
    for flag in flags_list:
        if not isinstance(flag, dict):
            continue
        # Search in dimension, finding, and signal fields
        for field in ("dimension", "finding", "signal"):
            text = str(flag.get(field, ""))
            if keyword_lower in text.lower():
                return True

    return False


def apply_severity_downgrade(
    severity: Optional[str], confirmed: bool
) -> tuple[Optional[str], bool]:
    """Apply Damodaran source reliability severity downgrade.

    All severities downgraded one tier, UNLESS confirmed by contradiction_calc.

    Returns:
        (downgraded_severity, was_downgraded)
    """
    if severity is None:
        return (None, False)

    if confirmed:
        return (severity, False)

    downgraded = SEVERITY_DOWNGRADE.get(severity)
    return (downgraded, downgraded != severity)


# ═══════════════════════════════════════════════════════
# P5/P95 Extrapolation for Mismatch Detection
# ═══════════════════════════════════════════════════════


def extrapolate_p5_p95(percentiles: dict[str, float]) -> tuple[float, float]:
    """Estimate P5 and P95 by linear extrapolation from P10/P25/P75/P90."""
    p10 = percentiles["p10"]
    p25 = percentiles["p25"]
    p75 = percentiles["p75"]
    p90 = percentiles["p90"]

    # P5: extrapolate below P10 using P10-P25 slope
    if p25 > p10 and p10 > 0:
        p5 = max(0.0, p10 - 0.5 * (p25 - p10))
    else:
        p5 = p10 * 0.8 if p10 > 0 else 0.0

    # P95: extrapolate above P90 using P75-P90 slope
    if p90 > p75 and p90 > 0:
        p95 = p90 + 0.5 * (p90 - p75)
    else:
        p95 = p90 * 1.2 if p90 > 0 else p90 + p90 * 0.2

    return (round(p5, 2), round(p95, 2))


# ═══════════════════════════════════════════════════════
# Industry Detection Helpers
# ═══════════════════════════════════════════════════════


def detect_years(company: str, version: str) -> list[int]:
    """Auto-detect available fiscal years from output directory structure."""
    out_dir = ROOT / "output" / company / version
    if not out_dir.exists():
        return []

    years: list[int] = []
    for d in out_dir.iterdir():
        if d.is_dir() and d.name.startswith("Y"):
            try:
                y = int(d.name[1:])
                years.append(y)
            except ValueError:
                continue

    years.sort()
    return years


def load_ratios(company: str, version: str, year: int) -> dict[str, Any]:
    """Load ratios.json for a given year. Returns {} if missing or unparseable."""
    ratios_path = (
        ROOT / "output" / company / version / f"Y{year}" / "finance" / "ratios.json"
    )
    if not ratios_path.exists():
        return {}
    try:
        return json.loads(ratios_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def load_router_output(company: str, version: str, latest_year: int) -> dict[str, Any]:
    """Load router output, trying chapter_map.json first, then route.json."""
    router_dir = ROOT / "output" / company / version / f"Y{latest_year}" / "router"

    for filename in ("chapter_map.json", "route.json"):
        path = router_dir / filename
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue

    return {}


def load_quant_flags(company: str, version: str) -> dict[str, Any]:
    """Load contradiction_calc.py output (quant_flags.json). Returns {} if missing."""
    path = ROOT / "output" / company / version / "cross_year" / "quant_flags.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def load_benchmarks() -> dict[str, Any]:
    """Load Damodaran industry benchmark data. Returns {} if missing."""
    path = ROOT / "reference" / "industry_benchmarks.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def resolve_industry(
    company: str,
    router_output: dict[str, Any],
    company_version_dir: Path,
) -> tuple[str, str, str]:
    """Determine industry classification from multiple sources.

    Priority:
    1. Router output (chapter_map.json / route.json) with explicit industry field
    2. Company-to-industry static mapping
    3. Unknown fallback

    Returns:
        (industry_name, confidence, evidence_string)
    """
    # Try router output first
    if router_output:
        # Check for explicit industry field
        for key in ("industry", "industry_classification", "sector"):
            if key in router_output and router_output[key]:
                evidence = router_output.get(
                    "industry_evidence", "From router classification"
                )
                confidence = router_output.get("industry_confidence", "high")
                return (str(router_output[key]), str(confidence), str(evidence))

        # Check for industry in meta or nested structure
        meta = router_output.get("meta", {})
        if isinstance(meta, dict):
            for key in ("industry", "industry_classification", "sector"):
                if key in meta and meta[key]:
                    return (str(meta[key]), "high", "From router meta classification")

    # Fall back to static company-to-industry mapping
    if company in COMPANY_INDUSTRY_MAP:
        industry = COMPANY_INDUSTRY_MAP[company]
        return (industry, "medium", "Static company-to-industry mapping (no router classification available)")

    # Try strategy.json for industry keywords
    for d in sorted(company_version_dir.iterdir(), reverse=True):
        if not (d.is_dir() and d.name.startswith("Y")):
            continue
        strategy_path = d / "strategy" / "strategy.json"
        if strategy_path.exists():
            try:
                strategy_data = json.loads(strategy_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue

            # Search business description for industry keywords
            desc = str(strategy_data.get("core_business_drivers", ""))
            industry_keywords = {
                "Construction and Infrastructure": [
                    "construction", "infrastructure", "engineering", "building",
                ],
                "Consumer Goods and Healthcare": [
                    "consumer", "retail", "healthcare", "pharma", "food",
                    "beverage", "apparel",
                ],
                "Energy and Chemicals": [
                    "chemical", "energy", "oil", "gas", "power", "renewable",
                ],
                "Industrials": [
                    "auto", "vehicle", "manufacturing", "machinery", "mining",
                    "metal", "steel", "transport", "logistics",
                ],
                "Telecom Media and Technology": [
                    "software", "semiconductor", "telecom", "internet",
                    "electronics", "technology",
                ],
            }
            desc_lower = desc.lower()
            for ind, keywords in industry_keywords.items():
                matches = sum(1 for kw in keywords if kw in desc_lower)
                if matches >= 2:
                    return (ind, "low", f"Industry inferred from strategy keywords ({matches} matches)")

            break  # Only check Y3 (latest year)

    return ("Unknown", "low", "Unable to determine industry classification")


def compute_revenue_growth_pct(
    ratios_by_year: dict[int, dict[str, Any]]
) -> dict[int, float]:
    """Compute per-year revenue growth rates from ratios.json revenue data.

    Returns a dict mapping year -> YoY growth percentage. Y1 has no growth
    (no prior year). Y2 = (Y2-Y1)/Y1, Y3 = (Y3-Y2)/Y2.

    Also injects the 3-year total growth into the Y3 entry for Pass A position.
    The caller stores these into ratios_by_year for trend computation.
    """
    years = sorted(ratios_by_year.keys())
    growth_by_year: dict[int, float] = {}

    if len(years) < 2:
        return growth_by_year

    revenues: list[tuple[int, float]] = []
    for y in years:
        rev = ratios_by_year[y].get("revenue")
        if rev is not None:
            rev = _val({"v": rev}, "v")
            if rev > 0:
                revenues.append((y, rev))

    # Compute YoY growth rates
    for i in range(1, len(revenues)):
        prev_y, prev_rev = revenues[i - 1]
        curr_y, curr_rev = revenues[i]
        if prev_rev > 0:
            growth = round(((curr_rev - prev_rev) / prev_rev) * 100, 1)
            growth_by_year[curr_y] = growth

    return growth_by_year


def get_debt_to_equity(
    company: str, version: str, year: int
) -> Optional[float]:
    """Attempt to extract debt_to_equity from finance.json or ratios.json."""
    # Try ratios.json first
    ratios = load_ratios(company, version, year)
    if "debt_to_equity" in ratios:
        val = ratios["debt_to_equity"]
        if isinstance(val, (int, float)) and val != -999.0:
            return float(val)

    # Try finance.json
    fin_path = (
        ROOT / "output" / company / version / f"Y{year}" / "finance" / "finance.json"
    )
    if fin_path.exists():
        try:
            fin_data = json.loads(fin_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

        # Direct field
        for key in ("debt_to_equity", "d_e_ratio", "de_ratio"):
            if key in fin_data:
                val = _val(fin_data, key)
                if val != -999.0:
                    return val

        # Compute from components if available
        total_equity = _val(fin_data, "total_equity", -999.0)
        total_liabilities = _val(fin_data, "total_liabilities", -999.0)

        if total_equity > 0 and total_liabilities >= 0:
            return round(total_liabilities / total_equity, 4)

        # interest_bearing_debt / total_equity alternative
        ib_debt = _val(fin_data, "interest_bearing_debt", -999.0)
        if total_equity > 0 and ib_debt >= 0:
            return round(ib_debt / total_equity, 4)

    return None


# ═══════════════════════════════════════════════════════
# Description Generation
# ═══════════════════════════════════════════════════════


def build_flag_description(
    metric: str,
    y3_value: float,
    percentile: float,
    industry: str,
    percentiles: dict[str, float],
    trend: dict,
) -> str:
    """Build a human-readable description for a flag."""
    label = METRIC_TO_CONTRADICTION_KEYWORD.get(metric, metric)

    if metric in ("dso_days", "dio_days", "dpo_days", "ccc_days"):
        unit = "d"
    elif metric == "debt_to_equity":
        unit = "x"
    else:
        unit = "%"

    desc_parts = [f"{label} ({y3_value}{unit}) at P{int(percentile)} of {industry}"]

    # Trend description
    if trend and trend.get("pct_change", 0) != 0:
        pct = abs(trend["pct_change"])
        if trend.get("note"):
            # 2-point trend: describe the direction naturally
            y1_v = trend.get("y1", 0)
            if trend["pct_change"] < 0:
                desc_parts.append(
                    f"Down from {y1_v}{unit} to {y3_value}{unit} ({pct:.0f}% decline)"
                )
            else:
                desc_parts.append(
                    f"Up from {y1_v}{unit} to {y3_value}{unit} ({pct:.0f}% increase)"
                )
        else:
            # Standard 3-point trend
            if trend["pct_change"] > 0:
                desc_parts.append(f"Rising {pct:.0f}% over 3 years")
            else:
                desc_parts.append(f"Falling {pct:.0f}% over 3 years")

    return ". ".join(desc_parts) + "."


# ═══════════════════════════════════════════════════════
# Core Computation
# ═══════════════════════════════════════════════════════


def compute_industry_flags(
    company: str, version: str = "v1"
) -> dict[str, Any]:
    """Main entry point: compute all industry benchmark flags.

    Called by run_multi_year.py during pipeline execution.

    Returns:
        Dict with company, industry, flags, summary. Contains "error" key
        on failure (checked by caller).
    """
    out_dir = ROOT / "output" / company / version / "cross_year"
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. Detect years
    years = detect_years(company, version)
    if len(years) < 2:
        return {
            "error": f"Need at least 2 years of data, found {len(years)}",
            "company": company,
        }
    years = years[-3:]  # Take up to 3 most recent

    # 2. Load data for all years
    ratios_by_year: dict[int, dict[str, Any]] = {}
    for y in years:
        r = load_ratios(company, version, y)
        if r:
            ratios_by_year[y] = r

    if len(ratios_by_year) < 2:
        return {
            "error": f"Need at least 2 years with ratios.json data, found {len(ratios_by_year)}",
            "company": company,
        }

    # 3. Load benchmarks
    benchmarks_data = load_benchmarks()
    if not benchmarks_data:
        return {
            "error": "industry_benchmarks.json not found — benchmark step skipped",
            "company": company,
        }

    # 4. Load router output for industry classification
    y3 = years[-1]
    router_output = load_router_output(company, version, y3)
    company_version_dir = ROOT / "output" / company / version

    industry, confidence, evidence = resolve_industry(
        company, router_output, company_version_dir
    )

    # 5. Validate industry exists in benchmarks
    industries = benchmarks_data.get("industries", {})
    if industry not in industries:
        return {
            "error": f"Industry '{industry}' not found in benchmark data. Available: {list(industries.keys())}",
            "company": company,
            "industry": industry,
        }

    industry_benchmarks = industries[industry]["benchmarks"]
    meta = benchmarks_data.get("meta", {})
    source_reliability = meta.get("source_reliability", "moderate")

    # 6. Load quant_flags for cross-reference
    quant_flags = load_quant_flags(company, version)

    # 7. Compute per-year revenue_growth_pct from revenue data
    # Inject YoY growth into Y2, Y3 (Y1 has no prior year, so it stays missing)
    rev_growth_by_year = compute_revenue_growth_pct(ratios_by_year)
    for y, growth in rev_growth_by_year.items():
        if y in ratios_by_year:
            ratios_by_year[y]["revenue_growth_pct"] = growth

    # 8. Try to get debt_to_equity for each year
    for y in years:
        if y in ratios_by_year and "debt_to_equity" not in ratios_by_year[y]:
            d_e = get_debt_to_equity(company, version, y)
            if d_e is not None:
                ratios_by_year[y]["debt_to_equity"] = d_e

    # 9. Pass A: Static Position (Y3 only)
    y3_ratios = ratios_by_year.get(y3, {})
    flags: list[dict] = []
    mismatch_count = 0
    metrics_evaluated = 0

    for metric in METRIC_NAMES:
        if metric not in y3_ratios:
            # Try to get from earlier years
            found = False
            for y in reversed(years[:-1]):
                if y in ratios_by_year and metric in ratios_by_year[y]:
                    found = True
                    break
            if not found:
                continue

        y3_val = y3_ratios.get(metric)
        if y3_val is None:
            continue
        y3_val = _val({"v": y3_val}, "v")
        if y3_val == -999.0:
            continue

        benchmarks = industry_benchmarks.get(metric)
        if not benchmarks:
            continue

        metrics_evaluated += 1

        # Pass A: percentile bucketing
        bucket, approx_pct = find_percentile_bucket(y3_val, benchmarks)
        static_cat, static_sev_raw = compute_static_position(bucket, metric)

        # Mismatch check: outside P5-P95
        p5, p95 = extrapolate_p5_p95(benchmarks)
        if y3_val < p5 or y3_val > p95:
            mismatch_count += 1

        # Pass B: Trend (requires at least 2 data points)
        trend_values: dict[str, float] = {}
        trend_direction = "stable"
        pct_change = 0.0
        is_monotonic = False
        position_trend_cell = "NORMAL"
        combined_sev_raw: Optional[str] = None
        trend_points_available = 0  # 0, 2, or 3

        if len(years) >= 2:
            y1 = years[0]
            y2 = years[1]
            y1_val = ratios_by_year.get(y1, {}).get(metric)
            y2_val = ratios_by_year.get(y2, {}).get(metric)

            y1_num = -999.0
            y2_num = -999.0
            if y1_val is not None:
                y1_num = _val({"v": y1_val}, "v")
            if y2_val is not None:
                y2_num = _val({"v": y2_val}, "v")

            direction = METRIC_DIRECTION.get(metric, "lower_better")

            if y1_num != -999.0 and y2_num != -999.0 and y3_val != -999.0:
                # Full 3-data-point trend
                trend_direction, pct_change, is_monotonic = compute_trend(
                    y1_num, y2_num, y3_val, direction
                )
                trend_values = {
                    "y1": y1_num, "y2": y2_num, "y3": y3_val, "pct_change": pct_change,
                }
                trend_points_available = 3

            elif y2_num != -999.0 and y3_val != -999.0:
                # 2-data-point trend (e.g., revenue_growth_pct with no Y0)
                # Compute 2-point trend: Y2 -> Y3
                trend_direction, pct_change, is_monotonic = compute_trend(
                    y2_num, y2_num, y3_val, direction
                )
                # Recompute properly for 2 points
                if abs(y2_num) > 0.001:
                    pct_change_2pt = round(
                        ((y3_val - y2_num) / abs(y2_num)) * 100, 1
                    )
                else:
                    pct_change_2pt = 0.0

                # Direction from Y2->Y3 change
                abs_pct = abs(pct_change_2pt)
                if abs_pct < 5.0:
                    trend_direction = "stable"
                elif direction == "lower_better":
                    trend_direction = "improving" if pct_change_2pt < -5.0 else "deteriorating"
                else:
                    trend_direction = "improving" if pct_change_2pt > 5.0 else "deteriorating"

                is_monotonic = False  # Can't determine monotonicity with 2 points
                trend_values = {
                    "y1": y2_num,  # earliest known value
                    "y3": y3_val,
                    "pct_change": pct_change_2pt,
                    "note": "2-point trend (earliest known to latest)",
                }
                trend_points_available = 2

            if trend_points_available >= 2:
                position_trend_cell, combined_sev_raw = compute_position_trend_cell(
                    static_cat, trend_direction
                )

                # Upgrade trend severity for monotonic moves >10%
                if is_monotonic and combined_sev_raw:
                    if combined_sev_raw == "LOW" and trend_direction in (
                        "improving", "deteriorating",
                    ):
                        pass  # Keep as-is for positive signals
                    elif combined_sev_raw == "MEDIUM" and abs(pct_change) > 20:
                        combined_sev_raw = "HIGH"

        # Severity: use combined if available, otherwise static
        raw_severity = combined_sev_raw if combined_sev_raw else static_sev_raw

        # Contradiction calc cross-reference
        confirmed = check_contradiction_calc_confirmation(metric, quant_flags)

        # Apply severity downgrade
        final_severity, was_downgraded = apply_severity_downgrade(
            raw_severity, confirmed
        )

        # Build description
        description = build_flag_description(
            metric, y3_val, approx_pct, industry, benchmarks, trend_values
        )

        flag_entry: dict[str, Any] = {
            "metric": metric,
            "y3_value": y3_val,
            "percentile": approx_pct,
            "position_bucket": BUCKET_LABELS.get(bucket, bucket),
            "static_category": static_cat,
            "static_severity_raw": static_sev_raw,
        }

        if trend_values:
            flag_entry["trend_values"] = trend_values
            flag_entry["trend_direction"] = trend_direction
            flag_entry["position_trend_cell"] = position_trend_cell
            flag_entry["combined_severity_raw"] = combined_sev_raw

        flag_entry["combined_severity_final"] = final_severity
        flag_entry["downgraded"] = was_downgraded
        flag_entry["contradiction_calc_confirmed"] = confirmed
        flag_entry["description"] = description

        # Only include in flags list if there's something to flag (non-None severity)
        if final_severity is not None:
            flags.append(flag_entry)

    # 10. Mismatch warning
    mismatch_warning = mismatch_count >= 3
    mismatch_detail = None
    if mismatch_warning:
        mismatch_detail = (
            f"{mismatch_count} of {metrics_evaluated} metrics outside "
            f"P5-P95 range for '{industry}'. Company may be misclassified."
        )

    # 11. Summary
    high_count = sum(1 for f in flags if f.get("combined_severity_final") == "HIGH")
    med_count = sum(1 for f in flags if f.get("combined_severity_final") == "MEDIUM")
    low_count = sum(1 for f in flags if f.get("combined_severity_final") == "LOW")

    static_only = sum(
        1
        for f in flags
        if f.get("static_severity_raw") and not f.get("combined_severity_raw")
    )
    trend_only = sum(
        1
        for f in flags
        if not f.get("static_severity_raw") and f.get("combined_severity_raw")
    )
    combined = sum(
        1
        for f in flags
        if f.get("static_severity_raw") and f.get("combined_severity_raw")
    )
    positive_signals = sum(
        1 for f in flags if f.get("position_trend_cell") in ("STRONG_LEADER", "CATCHING_UP")
    )

    result: dict[str, Any] = {
        "company": company,
        "industry": industry,
        "industry_confidence": confidence,
        "industry_evidence": evidence,
        "source_reliability": source_reliability,
        "severity_downgraded": any(f.get("downgraded") for f in flags),
        "industry_mismatch_warning": mismatch_warning,
        "mismatch_detail": mismatch_detail,
        "flags": flags,
        "summary": {
            "total_flags": len(flags),
            "high": high_count,
            "medium": med_count,
            "low": low_count,
            "static_only": static_only,
            "trend_only": trend_only,
            "combined": combined,
            "positive_signals": positive_signals,
        },
    }

    return result


# ═══════════════════════════════════════════════════════
# CLI Entry Point
# ═══════════════════════════════════════════════════════


def main() -> None:
    """CLI entry point: python tools/industry_benchmark.py <company> [version]"""
    if len(sys.argv) < 2:
        print("Usage: python tools/industry_benchmark.py <company> [version]")
        print("  Default version: v1")
        print("Example: python tools/industry_benchmark.py DemoConstruct v3")
        sys.exit(1)

    company = sys.argv[1]
    version = sys.argv[2] if len(sys.argv) > 2 else "v1"

    out_dir = ROOT / "output" / company / version / "cross_year"
    out_dir.mkdir(parents=True, exist_ok=True)

    result = compute_industry_flags(company, version)

    out_path = out_dir / "industry_flags.json"
    out_path.write_text(
        json.dumps(result, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    if "error" in result:
        print(f"ERROR: {result['error']}")
        sys.exit(1)

    s = result.get("summary", {})
    print(f"Industry: {result['industry']} (confidence: {result['industry_confidence']})")
    print(f"Source reliability: {result['source_reliability']}")
    print(f"Flags: {s.get('total_flags', 0)} total")
    print(f"  HIGH:   {s.get('high', 0)}")
    print(f"  MEDIUM: {s.get('medium', 0)}")
    print(f"  LOW:    {s.get('low', 0)}")
    print(f"  Static only: {s.get('static_only', 0)}")
    print(f"  Trend only:  {s.get('trend_only', 0)}")
    print(f"  Combined:    {s.get('combined', 0)}")
    print(f"  Positive signals: {s.get('positive_signals', 0)}")

    if result.get("severity_downgraded"):
        print("\nSeverity downgraded: Yes (Damodaran US/EU bias)")
    if result.get("industry_mismatch_warning"):
        print(f"\nINDUSTRY MISMATCH WARNING: {result.get('mismatch_detail', '')}")

    print(f"\nOutput: {out_path}")


if __name__ == "__main__":
    main()
