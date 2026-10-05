"""GRE/TOEFL-style percentile panels for the CDEW report (Task 8).

Renders a 7-panel percentile grid (gross margin, DSO, DIO, DPO, CCC,
revenue growth, D/E) against industry benchmarks (P10/P25/P50/P75/P90) and a
compact score panel (health score, grade, distress probability).
"""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("WINDIR", os.environ.get("SystemRoot", r"C:\Windows"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

KNOTS = [10, 25, 50, 75, 90]


def percentile_of(value: float, benchmark: dict) -> float:
    """Linear interpolation of a value against P10..P90 benchmark knots."""
    xs = [float(benchmark[f"p{k}"]) for k in KNOTS]
    if value <= xs[0]:
        return 0.0
    if value >= xs[-1]:
        return 100.0
    for i in range(len(KNOTS) - 1):
        if xs[i] <= value <= xs[i + 1]:
            span = xs[i + 1] - xs[i]
            frac = (value - xs[i]) / span if span else 0.0
            return KNOTS[i] + frac * (KNOTS[i + 1] - KNOTS[i])
    return 50.0


def _favorable(good_when_high: bool, percentile: float) -> bool:
    return percentile >= 50.0 if good_when_high else percentile <= 50.0


def _color(good_when_high: bool, percentile: float, trend: str) -> str:
    """Position x trend -> green/amber/red."""
    score = 1
    score += 1 if _favorable(good_when_high, percentile) else -1
    if trend == "improving":
        score += 1
    elif trend == "deteriorating":
        score -= 1
    score = max(0, min(2, score))
    return ["#d9534f", "#f0ad4e", "#28a745"][score]


def _trend_arrow(trend: str) -> str:
    return {"improving": "\u25b2", "deteriorating": "\u25bc"}.get(trend, "\u25b6")


def percentiles_for(metrics: dict[str, float], benchmarks: dict[str, dict]) -> dict[str, float]:
    """Compute all seven percentiles without drawing."""
    return {
        key: percentile_of(metrics[key], benchmarks[key])
        for key in (
            "gross_margin_pct", "dso_days", "dio_days", "dpo_days",
            "ccc_days", "revenue_growth_pct", "debt_to_equity",
        )
    }


def build_percentile_grid(
    ratios: dict[str, float],
    benchmarks: dict[str, dict],
    out_png: str,
    trends: dict[str, str] | None = None,
) -> dict[str, float]:
    """Draw the 7-panel percentile grid; returns computed percentiles."""
    trends = trends or {}
    metrics = [
        ("gross_margin_pct", "Gross Margin", True),
        ("dso_days", "DSO (days)", False),
        ("dio_days", "DIO (days)", False),
        ("dpo_days", "DPO (days)", True),
        ("ccc_days", "CCC (days)", False),
        ("revenue_growth_pct", "Revenue Growth %", True),
        ("debt_to_equity", "Debt / Equity", False),
    ]
    percentiles = {}
    fig, axes = plt.subplots(4, 2, figsize=(13.5, 11.0))
    flat = [ax for row in axes for ax in row]
    for ax, (key, label, good_high) in zip(flat, metrics):
        bench = benchmarks[key]
        value = ratios[key]
        pct = percentile_of(value, bench)
        percentiles[key] = pct
        color = _color(good_high, pct, trends.get(key, "stable"))
        arrow = _trend_arrow(trends.get(key, "stable"))

        lo = float(bench["p10"]) - (float(bench["p90"]) - float(bench["p10"])) * 0.15
        hi = float(bench["p90"]) + (float(bench["p90"]) - float(bench["p10"])) * 0.15
        if hi == lo:
            hi = lo + 1.0
        ax.set_xlim(lo, hi)
        for k, pos in zip(KNOTS, [bench[f"p{k}"] for k in KNOTS]):
            ax.axvline(pos, color="#b0b8c4", linewidth=0.9, alpha=0.8)
            ax.text(pos, 0.72, f"P{k}", ha="center", va="center", fontsize=7.5,
                    color="#5a6a7a")

        marker_x = min(max(value, lo), hi)
        ax.plot(marker_x, 0.42, marker="o", markersize=11, color=color, zorder=5)
        ax.text(marker_x, 0.12, f"{value:,.1f}", ha="center", fontsize=9,
                fontweight="bold", color=color)
        ax.text(hi, 0.88, f"P{int(round(pct))}", ha="right", fontsize=12,
                fontweight="bold", color=color)
        ax.text(hi, 0.12, arrow, ha="right", fontsize=11, color=color)
        ax.set_title(label, fontsize=10.5, loc="left", color="#152235")
        ax.set_yticks([])
        ax.set_ylim(0, 1)
        for spine in ("top", "right", "left"):
            ax.spines[spine].set_visible(False)
        ax.spines["bottom"].set_color("#9aa7b5")
    flat[-1].axis("off")
    fig.suptitle("Industry Percentile Benchmarks (P10-P90)", fontsize=14,
                 fontweight="bold", color="#152235", y=0.98)
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    Path(out_png).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return percentiles


def build_score_panel(score: dict, out_png: str) -> None:
    """Score panel: health score 0-100, grade, distress probability."""
    health = score.get("health_score", 0) or 0
    proba = score.get("distress_probability", 0.0) or 0.0
    grade = score.get("grade", "N/A") or "N/A"
    fig, ax = plt.subplots(figsize=(6.2, 3.1))
    ax.text(0.5, 0.78, str(health), ha="center", fontsize=54,
            fontweight="bold", color="#152235")
    ax.text(0.5, 0.47, f"CDEW Health Score  /  {grade}", ha="center",
            fontsize=13, color="#5a6a7a")
    ax.text(0.5, 0.27, f"Distress probability {proba*100:.1f}%",
            ha="center", fontsize=11, color="#5a6a7a")
    ax.barh(0.12, proba, color="#d9534f", height=0.07)
    ax.barh(0.12, 1.0, color="#e6eaef", height=0.07)
    ax.set_xlim(0, 1)
    ax.set_yticks([])
    ax.set_xticks([])
    for spine in ax.spines.values():
        spine.set_visible(False)
    fig.tight_layout()
    Path(out_png).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=150, bbox_inches="tight")
    plt.close(fig)
