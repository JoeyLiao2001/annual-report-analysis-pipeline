"""Train CDEW-style classifiers on the Taiwan Economic Journal dataset.

This is a NEW standalone script (project rule: only new files may be added
inside this repo). It mirrors train.py logic but loads the Taiwan TEJ CSV
(data.csv), which is a single pooled cross-section of 6,819 firm-years with
96 columns: 1 target (Bankrupt?) + 95 financial ratios. It:

  1. trains the same model family (logreg / random_forest / xgboost) on the
     full 95-feature set with a stratified 60/20/20 split;
  2. reports test PR-AUC / ROC-AUC / Brier plus bootstrap 95% CIs;
  3. also computes how many of the 25 CDEW-aligned features can be mapped to a
     Taiwan column (a feasibility note, reported as coverage, not as a model).

Usage:
    python train_taiwan.py --csv <data.csv> --out <output_dir> [--seed 42]
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.model_selection import train_test_split

from preprocess import fit_transform, transform

TARGET = "Bankrupt?"


# ---- aligned coverage: aligned X -> keyword(s) that must appear in a Taiwan column ----
# Conservative: only map when a Taiwan column name directly carries the construct.
ALIGNED_MAPPING: dict[str, list[str]] = {
    "X4": ["Current Ratio"],
    "X19": ["Gross Profit to Sales", "Operating Gross Margin"],
    "X39": ["Realized Sales Gross Margin"],
    "X42": ["Operating Profit Rate"],
    "X44": ["Average Collection Days"],
    "X46": ["Quick Assets/Current Liability"],
    "X56": ["Realized Sales Gross Margin"],
    "X60": ["Inventory Turnover Rate"],
    "X61": ["Accounts Receivable Turnover"],
    "X43": ["Average Collection Days"],  # + inventory days, partial
}


def load_taiwan(csv_path: str) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    if TARGET not in df.columns:
        raise SystemExit(f"Target column '{TARGET}' not found.")
    df = df.rename(columns={TARGET: "label"})
    df["label"] = df["label"].astype(int)
    return df


def split_stratified(
    df: pd.DataFrame, val_size: float = 0.2, test_size: float = 0.2, seed: int = 42
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    y = df["label"].astype(int)
    rest, test = train_test_split(df, test_size=test_size, stratify=y, random_state=seed)
    y_rest = rest["label"].astype(int)
    train, val = train_test_split(
        rest,
        test_size=val_size / (1.0 - test_size),
        stratify=y_rest,
        random_state=seed,
    )
    return train, val, test


def evaluate(model, X, y) -> dict[str, float]:
    proba = model.predict_proba(X)[:, 1]
    return {
        "pr_auc": float(average_precision_score(y, proba)),
        "auc": float(roc_auc_score(y, proba)),
        "brier": float(brier_score_loss(y, proba)),
    }


def train_all(Xtr_df, ytr, Xva_df, yva, seed: int = 42) -> dict[str, dict]:
    Xtr, params = fit_transform(Xtr_df, pd.Series(ytr))
    Xva = transform(Xva_df, params)
    ytr = np.asarray(ytr)
    yva = np.asarray(yva)
    n_neg = int((ytr == 0).sum())
    n_pos = int((ytr == 1).sum())
    scale_pos_weight = n_neg / n_pos if n_pos > 0 else 1.0

    models: dict[str, dict] = {}

    lr = LogisticRegression(max_iter=2000, class_weight="balanced", random_state=seed)
    lr.fit(Xtr, ytr)
    models["logreg"] = {"model": lr, "backend": "sklearn", **evaluate(lr, Xva, yva)}

    rf = RandomForestClassifier(n_estimators=300, class_weight="balanced", n_jobs=-1, random_state=seed)
    rf.fit(Xtr, ytr)
    models["random_forest"] = {"model": rf, "backend": "sklearn", **evaluate(rf, Xva, yva)}

    import xgboost as xgb

    booster = xgb.XGBClassifier(
        n_estimators=1000,
        learning_rate=0.05,
        max_depth=4,
        subsample=0.8,
        colsample_bytree=0.8,
        scale_pos_weight=scale_pos_weight,
        eval_metric="aucpr",
        early_stopping_rounds=30,
        n_jobs=1,
        random_state=seed,
    )
    booster.fit(Xtr, ytr, eval_set=[(Xva, yva)], verbose=False)
    models["xgboost"] = {"model": booster, "backend": "xgboost", **evaluate(booster, Xva, yva)}
    return models, params


def bootstrap_ci(X, y, models: dict[str, dict], n: int = 200, seed: int = 42) -> dict:
    rng = np.random.default_rng(seed)
    X = pd.DataFrame(X)
    y = np.asarray(y)
    m = len(y)
    per_model = {name: {"pr_auc": [], "auc": [], "brier": []} for name in models}
    for _ in range(n):
        idx = rng.integers(0, m, m)
        for name, entry in models.items():
            proba = entry["model"].predict_proba(X.iloc[idx])[:, 1]
            per_model[name]["pr_auc"].append(average_precision_score(y[idx], proba))
            per_model[name]["auc"].append(roc_auc_score(y[idx], proba))
            per_model[name]["brier"].append(brier_score_loss(y[idx], proba))
    return {
        name: {
            metric: {
                "mean": float(np.asarray(vals).mean()),
                "ci_low": float(np.percentile(vals, 2.5)),
                "ci_high": float(np.percentile(vals, 97.5)),
            }
            for metric, vals in mets.items()
        }
        for name, mets in per_model.items()
    }


ALL_ALIGNED = [
    "X12", "X19", "X20", "X21", "X23", "X27", "X32", "X33", "X39", "X4",
    "X40", "X42", "X43", "X44", "X45", "X46", "X47", "X52", "X55", "X56",
    "X58", "X60", "X61", "X62", "X63",
]


def aligned_coverage(df: pd.DataFrame) -> dict[str, str]:
    """Map all 25 aligned X -> matched Taiwan column (first keyword hit), else 'NOT MAPPED'."""
    taiwan_cols = [c for c in df.columns if c != "label"]
    coverage: dict[str, str] = {}
    for x in ALL_ALIGNED:
        kws = ALIGNED_MAPPING.get(x) or []
        hit = None
        for kw in kws:
            for c in taiwan_cols:
                if kw.lower() in c.lower():
                    hit = c
                    break
            if hit:
                break
        coverage[x] = hit if hit else "NOT MAPPED"
    return coverage


def main() -> None:
    parser = argparse.ArgumentParser(description="Train CDEW models on Taiwan TEJ data")
    parser.add_argument("--csv", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    df = load_taiwan(args.csv)
    feat_cols = [c for c in df.columns if c != "label"]

    train_df, val_df, test_df = split_stratified(df, seed=args.seed)
    Xtr, ytr = train_df[feat_cols], train_df["label"].astype(int)
    Xva, yva = val_df[feat_cols], val_df["label"].astype(int)
    Xte, yte = test_df[feat_cols], test_df["label"].astype(int)

    models, params = train_all(Xtr, ytr, Xva, yva, seed=args.seed)

    # Transform with train-fitted params (no refit on val/test).
    Xva_scaled = transform(Xva, params)
    Xte_scaled = transform(Xte, params)

    test_metrics = {name: evaluate(entry["model"], Xte_scaled, yte) for name, entry in models.items()}
    cis = bootstrap_ci(Xte_scaled, yte, models, n=200, seed=args.seed)

    for name, entry in models.items():
        joblib.dump(entry["model"], out / f"taiwan_{name}.joblib")

    preds = pd.DataFrame({"label": yte.to_numpy()})
    for name, entry in models.items():
        preds[name] = entry["model"].predict_proba(Xte_scaled)[:, 1]
    preds.to_csv(out / "taiwan_test_predictions.csv", index=False)
    (out / "taiwan_preprocess_params.json").write_text(json.dumps(params, indent=2), encoding="utf-8")

    coverage = aligned_coverage(df)
    mapped = {x: c for x, c in coverage.items() if c != "NOT MAPPED"}

    result = {
        "dataset": "Taiwan Economic Journal bankruptcy (UCI 572 / Kaggle fedesoriano)",
        "n_rows": int(len(df)),
        "n_features_all": len(feat_cols),
        "n_train": int(len(train_df)),
        "n_val": int(len(val_df)),
        "n_test": int(len(test_df)),
        "pos_rate": float((df["label"] == 1).mean()),
        "test_metrics": test_metrics,
        "bootstrap_ci": cis,
        "aligned_25_coverage": {
            "mapped_count": len(mapped),
            "of_25": 25,
            "mapped": mapped,
            "unmapped": [x for x, c in coverage.items() if c == "NOT MAPPED"],
            "note": (
                "Coverage is a feasibility check of which CDEW-aligned features can be "
                "reproduced from Taiwan TEJ columns. Several aligned features (e.g. X55 "
                "absolute working capital, X21 prior-year sales growth, X23 net margin, "
                "X27 op-profit/finance-expense, X32/X47/X52 which need cost-of-goods-sold) "
                "have no clean Taiwan column and are marked NOT MAPPED."
            ),
        },
        "created_utc": datetime.now(timezone.utc).isoformat(),
    }
    (out / "taiwan_model_comparison.json").write_text(json.dumps(result, indent=2), encoding="utf-8")

    print(f"n={len(df)} pos_rate={result['pos_rate']:.4f} n_train={len(train_df)} n_test={len(test_df)}")
    for name, m in test_metrics.items():
        ci = cis[name]
        print(
            f"{name}: PR-AUC={m['pr_auc']:.4f} ({ci['pr_auc']['ci_low']:.4f}-{ci['pr_auc']['ci_high']:.4f}), "
            f"AUC={m['auc']:.4f}, Brier={m['brier']:.4f}"
        )
    print(f"Aligned 25-feature coverage: {len(mapped)}/25 mapped -> {sorted(mapped.keys())}")
    print(f"Not mapped: {sorted(x for x, c in coverage.items() if c == 'NOT MAPPED')}")


if __name__ == "__main__":
    main()
