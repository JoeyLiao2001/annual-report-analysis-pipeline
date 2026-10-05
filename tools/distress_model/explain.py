"""SHAP explainability for the CDEW model (Task 5).

Global importance (mean |SHAP| per feature), local explanations, and
summary figures are generated from the held-out test split.

Usage:
    python explain.py --eval-dir <output/_cdew> [--model xgboost]
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

os.environ.setdefault("WINDIR", os.environ.get("SystemRoot", r"C:\Windows"))

import joblib
import numpy as np
import pandas as pd


def _explainer(model, X_sample):
    import shap

    if hasattr(model, "coef_"):
        return shap.LinearExplainer(model, X_sample)
    return shap.TreeExplainer(model)


def _shap_values(explainer, X):
    import shap

    sv = explainer.shap_values(X)
    if isinstance(sv, list):
        sv = sv[1] if len(sv) == 2 else sv[0]
    if hasattr(sv, "values"):
        sv = sv.values
    return np.asarray(sv)


def global_explanation(model, X_sample, feature_names) -> pd.DataFrame:
    """Mean absolute SHAP value per feature, sorted descending."""
    X = np.asarray(X_sample, dtype=float)
    explainer = _explainer(model, X)
    sv = _shap_values(explainer, X)
    mean_abs = np.abs(sv).mean(axis=0)
    df = pd.DataFrame(
        {"feature": list(feature_names), "mean_abs_shap": mean_abs}
    ).sort_values("mean_abs_shap", ascending=False, ignore_index=True)
    return df


def local_explanation(model, X_row) -> pd.DataFrame:
    """Per-feature SHAP values for a single row, sorted by |SHAP|."""
    X = np.asarray(X_row, dtype=float).reshape(1, -1)
    explainer = _explainer(model, X)
    sv = _shap_values(explainer, X)[0]
    df = pd.DataFrame({"feature": list(range(len(sv))), "shap": sv})
    df["feature"] = df["feature"].astype(str)
    return df.sort_values("shap", key=lambda s: s.abs(), ascending=False, ignore_index=True)


def main() -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import shap

    parser = argparse.ArgumentParser(description="SHAP explainability (Task 5)")
    parser.add_argument("--eval-dir", required=True)
    parser.add_argument("--model", default="xgboost")
    parser.add_argument("--n-sample", type=int, default=500)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    eval_dir = Path(args.eval_dir) / "evaluation"
    figures_dir = Path(args.eval_dir) / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)

    model = joblib.load(Path(args.eval_dir) / "models" / f"{args.model}.joblib")
    X_test = pd.read_csv(eval_dir / "X_test.csv")
    rng = np.random.default_rng(args.seed)
    n = min(args.n_sample, len(X_test))
    sample = X_test.sample(n=n, random_state=args.seed)
    feature_names = list(X_test.columns)

    explainer = _explainer(model, sample.to_numpy(dtype=float))
    sv = _shap_values(explainer, sample.to_numpy(dtype=float))

    global_df = global_explanation(model, sample, feature_names)
    global_df.to_csv(figures_dir / "shap_summary.csv", index=False)

    local_df = local_explanation(model, X_test.iloc[0].to_numpy(dtype=float))
    local_df["feature"] = [feature_names[int(i)] for i in local_df["feature"]]
    local_df.to_csv(figures_dir / "local_example.csv", index=False)

    shap.summary_plot(sv, sample, feature_names=feature_names, show=False)
    plt.savefig(figures_dir / "shap_summary.png", dpi=150, bbox_inches="tight")
    plt.close()

    shap.summary_plot(
        sv, sample, feature_names=feature_names, plot_type="dot", show=False
    )
    plt.savefig(figures_dir / "shap_beeswarm.png", dpi=150, bbox_inches="tight")
    plt.close()

    print("Top 10 global drivers:")
    print(global_df.head(10).to_string(index=False))
    print(f"Saved figures to {figures_dir}")


if __name__ == "__main__":
    main()
