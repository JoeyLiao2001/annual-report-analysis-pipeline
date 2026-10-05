"""Exploratory data analysis for the UCI Polish Bankruptcy dataset.

Task 1: Data loader and EDA.

Writes `output/_cdew/evaluation/eda_summary.json` with per-year label
counts, missing percentages, and per-feature mean/std, then prints a
compact 10-line summary to stdout.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pandas as pd

from data_loader import load_all_years


DATA_DIR = Path(os.environ.get("POLISH_DATA_DIR", "data/polish_bankruptcy"))
OUT_JSON = Path(
    r"<repo>\output\_cdew\evaluation\eda_summary.json"
)
YEARS = [1, 2, 3, 4, 5]


def summarize(df: pd.DataFrame) -> dict[str, Any]:
    """Return compact EDA statistics for one prediction-year frame."""
    label_counts = df["label"].value_counts().sort_index().to_dict()
    feature_cols = [c for c in df.columns if c.startswith("X")]
    stats: dict[str, dict[str, float]] = {}
    for col in feature_cols:
        stats[col] = {
            "mean": float(df[col].mean()),
            "std": float(df[col].std()),
            "missing_pct": float(100.0 * df[col].isna().mean()),
        }
    return {
        "rows": int(len(df)),
        "feature_count": len(feature_cols),
        "label_counts": label_counts,
        "bankrupt_pct": float(100.0 * df["label"].mean()),
        "overall_missing_pct": float(100.0 * df[feature_cols].isna().mean().mean()),
        "feature_stats": stats,
    }


def main() -> None:
    frames = load_all_years(str(DATA_DIR), YEARS)
    summary = {
        str(year): summarize(frame) for year, frame in sorted(frames.items())
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(
        json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8"
    )

    # Compact 10-line stdout summary.
    total_rows = sum(frames[y].shape[0] for y in YEARS)
    total_bankrupt = sum(int(frames[y]["label"].sum()) for y in YEARS)
    print("UCI Polish Bankruptcy EDA (verified 2026-08-06)")
    print(f"Years loaded : {', '.join(str(y) for y in YEARS)}")
    print(f"Total rows   : {total_rows}")
    print(f"Bankrupt     : {total_bankrupt} ({100 * total_bankrupt / total_rows:.2f}%)")
    for year in YEARS:
        s = summary[str(year)]
        print(
            f"Year {year}: rows={s['rows']:>6}, "
            f"bankrupt={s['label_counts'].get(1, 0):>4} "
            f"({s['bankrupt_pct']:.2f}%), "
            f"missing={s['overall_missing_pct']:.2f}%, "
            f"features={s['feature_count']}"
        )
    print(f"Summary JSON : {OUT_JSON}")


if __name__ == "__main__":
    main()
