"""CDEW model training and comparison (Task 3).

Trains three classifiers (logistic regression, random forest, XGBoost) on
the pooled UCI Polish Bankruptcy data with a per-year stratified
train/validation/test split (60/20/20, fixed seed). All preprocessing is
fitted on the training split only. The trained models, preprocessing
parameters, predictions, and a comparison JSON (test metrics + bootstrap
95% CIs) are written under the output directory.

Usage:
    python train.py --train-dir <dir> --out <out> [--features full|aligned]
                    [--feature-cols <json list path>] [--seed 42]
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

from data_loader import load_all_years
from preprocess import fit_transform, transform

FEATURE_COLS = [f"X{i}" for i in range(1, 65)]


def _infer_cols(X, feature_cols):
    """Resolve feature columns from an explicit list or the input shape."""
    if feature_cols is not None:
        return feature_cols
    if isinstance(X, pd.DataFrame):
        return list(X.columns)
    return [f"f{i}" for i in range(X.shape[1])]


def load_pooled(train_dir: str, years: list[int] | None = None) -> pd.DataFrame:
    """Load all prediction-year ARFF frames and pool them with a year column."""
    years = years or [1, 2, 3, 4, 5]
    frames = load_all_years(train_dir, years)
    pooled = pd.concat(
        [frames[y].assign(year=y) for y in sorted(frames)], ignore_index=True
    )
    return pooled


def split_pooled(
    df: pd.DataFrame, val_size: float = 0.2, test_size: float = 0.2, seed: int = 42
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Per-year stratified split, then pool each split across years."""
    tr, va, te = [], [], []
    for year, frame in df.groupby("year"):
        y = frame["label"].astype(int)
        rest, test = train_test_split(
            frame, test_size=test_size, stratify=y, random_state=seed
        )
        y_rest = rest["label"].astype(int)
        train, val = train_test_split(
            rest,
            test_size=val_size / (1.0 - test_size),
            stratify=y_rest,
            random_state=seed,
        )
        tr.append(train)
        va.append(val)
        te.append(test)
    return (
        pd.concat(tr, ignore_index=True),
        pd.concat(va, ignore_index=True),
        pd.concat(te, ignore_index=True),
    )


def evaluate(model, X, y) -> dict[str, float]:
    """PR-AUC, ROC-AUC, and Brier score for the positive class (1)."""
    proba = model.predict_proba(X)[:, 1]
    return {
        "pr_auc": float(average_precision_score(y, proba)),
        "auc": float(roc_auc_score(y, proba)),
        "brier": float(brier_score_loss(y, proba)),
    }


def train_all(
    X_train,
    y_train,
    X_val,
    y_val,
    seed: int = 42,
    feature_cols: list[str] | None = None,
) -> dict[str, dict]:
    """Train the three-model family and return fitted models plus val metrics.

    X_train/X_val may be numpy arrays or DataFrames; the training pipeline
    standardizes them with train-only statistics.
    """
    cols = _infer_cols(X_train, feature_cols)
    Xtr_df = pd.DataFrame(X_train, columns=cols)
    cols_val = _infer_cols(X_val, feature_cols)
    if cols_val != cols:
        raise ValueError("Train and validation feature columns differ")
    Xva_df = pd.DataFrame(X_val, columns=cols)
    Xtr, params = fit_transform(Xtr_df, pd.Series(y_train))
    Xva = transform(Xva_df, params)

    ytr = np.asarray(y_train)
    yva = np.asarray(y_val)
    n_neg = int((ytr == 0).sum())
    n_pos = int((ytr == 1).sum())
    scale_pos_weight = n_neg / n_pos if n_pos > 0 else 1.0

    models: dict[str, dict] = {}

    logreg = LogisticRegression(
        max_iter=2000, class_weight="balanced", random_state=seed
    )
    logreg.fit(Xtr, ytr)
    models["logreg"] = {
        "model": logreg,
        "backend": "sklearn",
        **evaluate(logreg, Xva, yva),
    }

    rf = RandomForestClassifier(
        n_estimators=300,
        class_weight="balanced",
        n_jobs=-1,
        random_state=seed,
    )
    rf.fit(Xtr, ytr)
    models["random_forest"] = {
        "model": rf,
        "backend": "sklearn",
        **evaluate(rf, Xva, yva),
    }

    try:
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
        backend = "xgboost"
    except ImportError:
        import lightgbm as lgb

        booster = lgb.LGBMClassifier(
            n_estimators=1000,
            learning_rate=0.05,
            num_leaves=31,
            scale_pos_weight=scale_pos_weight,
            class_weight="balanced",
            random_state=seed,
        )
        backend = "lightgbm"
    booster.fit(Xtr, ytr, eval_set=[(Xva, yva)], verbose=False)
    models["xgboost"] = {
        "model": booster,
        "backend": backend,
        **evaluate(booster, Xva, yva),
    }
    return models


def bootstrap_ci(
    X_test, y_test, models: dict[str, dict], n: int = 200, seed: int = 42
) -> dict:
    """Bootstrap 95% CIs for PR-AUC/AUC/Brier on the test split."""
    rng = np.random.default_rng(seed)
    cols = _infer_cols(X_test, None)
    X = pd.DataFrame(X_test, columns=cols)
    y = np.asarray(y_test)
    m = len(y)
    per_model: dict[str, dict[str, list[float]]] = {
        name: {"pr_auc": [], "auc": [], "brier": []} for name in models
    }
    for _ in range(n):
        idx = rng.integers(0, m, m)
        for name, entry in models.items():
            proba = entry["model"].predict_proba(X.iloc[idx])[:, 1]
            per_model[name]["pr_auc"].append(average_precision_score(y[idx], proba))
            per_model[name]["auc"].append(roc_auc_score(y[idx], proba))
            per_model[name]["brier"].append(brier_score_loss(y[idx], proba))
    result = {}
    for name, metrics in per_model.items():
        result[name] = {}
        for metric, values in metrics.items():
            arr = np.asarray(values)
            result[name][metric] = {
                "mean": float(arr.mean()),
                "ci_low": float(np.percentile(arr, 2.5)),
                "ci_high": float(np.percentile(arr, 97.5)),
            }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Train CDEW models (Task 3)")
    parser.add_argument("--train-dir", required=True, help="Directory with 1year..5year.arff")
    parser.add_argument("--out", required=True, help="Output directory (output/_cdew)")
    parser.add_argument("--features", choices=["full", "aligned"], default="full")
    parser.add_argument("--feature-cols", default=None, help="JSON list of X columns for aligned mode")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    out = Path(args.out)
    models_dir = out / "models"
    eval_dir = out / "evaluation"
    models_dir.mkdir(parents=True, exist_ok=True)
    eval_dir.mkdir(parents=True, exist_ok=True)

    pooled = load_pooled(args.train_dir)
    train_df, val_df, test_df = split_pooled(pooled, seed=args.seed)

    if args.features == "aligned":
        if not args.feature_cols:
            raise SystemExit("--features aligned requires --feature-cols")
        feature_cols = json.loads(Path(args.feature_cols).read_text(encoding="utf-8"))
        missing = [c for c in feature_cols if c not in FEATURE_COLS]
        if missing:
            raise SystemExit(f"Unknown feature columns: {missing}")
    else:
        feature_cols = FEATURE_COLS

    X_train = train_df[feature_cols]
    y_train = train_df["label"].astype(int)
    X_val = val_df[feature_cols]
    y_val = val_df["label"].astype(int)
    X_test = test_df[feature_cols]
    y_test = test_df["label"].astype(int)

    models = train_all(X_train, y_train, X_val, y_val, seed=args.seed, feature_cols=feature_cols)

    # Preprocessing params (same fit as inside train_all; deterministic).
    _, params = fit_transform(X_train, y_train)
    X_test_scaled = transform(X_test, params)
    X_val_scaled = transform(X_val, params)

    test_metrics = {name: evaluate(entry["model"], X_test_scaled, y_test)
                    for name, entry in models.items()}
    cis = bootstrap_ci(X_test_scaled, y_test, models, n=200, seed=args.seed)

    prefix = "aligned_" if args.features == "aligned" else ""
    for name, entry in models.items():
        joblib.dump(entry["model"], models_dir / f"{prefix}{name}.joblib")
    joblib.dump(params, models_dir / f"{prefix}preprocess_params.joblib")
    (models_dir / f"{prefix}preprocess_params.json").write_text(
        json.dumps(params, indent=2), encoding="utf-8"
    )

    for split, X, y in (("val", X_val_scaled, y_val), ("test", X_test_scaled, y_test)):
        X.to_csv(eval_dir / f"{prefix}X_{split}.csv", index=False)
        y.to_csv(eval_dir / f"{prefix}y_{split}.csv", index=False, header=["label"])
        preds = pd.DataFrame({"label": y.to_numpy()})
        for name, entry in models.items():
            preds[name] = entry["model"].predict_proba(X)[:, 1]
        preds.to_csv(eval_dir / f"{prefix}{split}_predictions.csv", index=False)

    comparison = {
        "features": args.features,
        "feature_cols": feature_cols,
        "seed": args.seed,
        "n_train": int(len(X_train)),
        "n_val": int(len(X_val)),
        "n_test": int(len(X_test)),
        "test_metrics": test_metrics,
        "bootstrap_ci": cis,
        "created_utc": datetime.now(timezone.utc).isoformat(),
    }
    (eval_dir / f"model_comparison_{args.features}.json").write_text(
        json.dumps(comparison, indent=2), encoding="utf-8"
    )

    print(f"features={args.features} n_train={len(X_train)} n_val={len(X_val)} n_test={len(X_test)}")
    for name, m in test_metrics.items():
        ci = cis[name]
        print(
            f"{name}: PR-AUC={m['pr_auc']:.4f} "
            f"(95% CI {ci['pr_auc']['ci_low']:.4f}-{ci['pr_auc']['ci_high']:.4f}), "
            f"AUC={m['auc']:.4f}, Brier={m['brier']:.4f}"
        )
    print(f"Saved: {models_dir}/*.joblib, {eval_dir}/model_comparison.json")


if __name__ == "__main__":
    main()
