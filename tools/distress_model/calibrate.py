"""Calibration and threshold economics for the CDEW model (Task 4).

The operating threshold minimizes the expected cost on validation data with
an FN:FP cost ratio of 10:1 (a missed distressed counterparty costs ten
times as much as a false alarm). Reliability tables quantify calibration on
the held-out test split.

Usage:
    python calibrate.py --eval-dir <output/_cdew> [--model xgboost]
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import precision_score, recall_score


def cost_curve(
    y_true, proba, fn_cost: float = 10.0, fp_cost: float = 1.0
) -> pd.DataFrame:
    """Expected-cost curve over candidate thresholds."""
    y = np.asarray(y_true, dtype=int)
    p = np.asarray(proba, dtype=float)
    n = len(y)
    n_pos = int((y == 1).sum())
    n_neg = n - n_pos
    thresholds = np.unique(np.concatenate([p, [0.0, 1.0]]))
    rows = []
    for t in thresholds:
        pred = (p >= t).astype(int)
        fp = int(((pred == 1) & (y == 0)).sum())
        fn = int(((pred == 0) & (y == 1)).sum())
        fp_rate = fp / n_neg if n_neg else 0.0
        fn_rate = fn / n_pos if n_pos else 0.0
        expected_cost = (
            fn_rate * fn_cost * n_pos + fp_rate * fp_cost * n_neg
        ) / n * 1000.0
        rows.append(
            {
                "threshold": float(t),
                "fp_rate": float(fp_rate),
                "fn_rate": float(fn_rate),
                "expected_cost_per_1000": float(expected_cost),
            }
        )
    return pd.DataFrame(rows).sort_values("threshold").reset_index(drop=True)


def pick_threshold(
    y_val, proba_val, fn_cost: float = 10.0, fp_cost: float = 1.0
) -> float:
    """Threshold minimizing expected cost on validation data."""
    curve = cost_curve(y_val, proba_val, fn_cost=fn_cost, fp_cost=fp_cost)
    return float(curve.loc[curve["expected_cost_per_1000"].idxmin(), "threshold"])


def reliability_table(y_true, proba, bins: int = 10) -> pd.DataFrame:
    """Equal-width reliability table: predicted vs actual positive rate."""
    y = np.asarray(y_true, dtype=int)
    p = np.asarray(proba, dtype=float)
    edges = np.linspace(0.0, 1.0, bins + 1)
    bin_idx = np.digitize(p, edges[1:-1])
    rows = []
    for i in range(bins):
        mask = bin_idx == i
        count = int(mask.sum())
        mean_pred = float(p[mask].mean()) if count else float("nan")
        mean_actual = float(y[mask].mean()) if count else float("nan")
        rows.append(
            {
                "bin": f"({edges[i]:.2f}, {edges[i + 1]:.2f}]",
                "mean_pred": mean_pred,
                "mean_actual": mean_actual,
                "count": count,
            }
        )
    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Calibration and threshold policy (Task 4)")
    parser.add_argument("--eval-dir", required=True)
    parser.add_argument("--model", default="xgboost")
    parser.add_argument("--fn-cost", type=float, default=10.0)
    parser.add_argument("--fp-cost", type=float, default=1.0)
    args = parser.parse_args()

    eval_dir = Path(args.eval_dir) / "evaluation"
    val = pd.read_csv(eval_dir / "val_predictions.csv")
    test = pd.read_csv(eval_dir / "test_predictions.csv")
    if args.model not in val.columns or args.model not in test.columns:
        raise SystemExit(f"Model column '{args.model}' missing from predictions")

    threshold = pick_threshold(
        val["label"], val[args.model], fn_cost=args.fn_cost, fp_cost=args.fp_cost
    )
    val_curve = cost_curve(
        val["label"], val[args.model], fn_cost=args.fn_cost, fp_cost=args.fp_cost
    )
    val_expected_cost = float(
        val_curve.loc[val_curve["threshold"] == threshold, "expected_cost_per_1000"].iloc[0]
    )

    test_pred = (test[args.model] >= threshold).astype(int)
    test_recall = float(recall_score(test["label"], test_pred, zero_division=0))
    test_precision = float(precision_score(test["label"], test_pred, zero_division=0))
    test_fp = int(((test_pred == 1) & (test["label"] == 0)).sum())
    test_fp_per_1000 = test_fp / len(test) * 1000.0

    rel = reliability_table(test["label"], test[args.model], bins=10)
    rel.to_csv(eval_dir / "reliability.csv", index=False)
    val_curve.to_csv(eval_dir / "cost_curve.csv", index=False)

    policy = {
        "model": args.model,
        "fn_cost": args.fn_cost,
        "fp_cost": args.fp_cost,
        "threshold": threshold,
        "val_expected_cost": val_expected_cost,
        "test_recall": test_recall,
        "test_precision": test_precision,
        "test_fp_per_1000": test_fp_per_1000,
        "created_utc": datetime.now(timezone.utc).isoformat(),
    }
    (eval_dir / "threshold_policy.json").write_text(
        json.dumps(policy, indent=2), encoding="utf-8"
    )
    print(json.dumps(policy, indent=2))


if __name__ == "__main__":
    main()
