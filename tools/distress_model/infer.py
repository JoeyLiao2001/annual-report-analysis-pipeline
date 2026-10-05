"""Per-company CDEW inference (Task 7).

Loads the aligned XGBoost model, applies the fitted preprocessing
parameters, and produces the distress_score.json schema for one company.

Usage:
    python infer.py --company DemoEV --version v1
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from preprocess import transform

ROOT = Path(__file__).resolve().parents[2]
EVAL_DIR = ROOT / "output" / "_cdew" / "evaluation"


def grade_for_probability(p: float) -> str:
    """Map a distress probability to the four-grade scale."""
    if p < 0.05:
        return "LOW"
    if p < 0.15:
        return "MEDIUM"
    if p < 0.30:
        return "HIGH"
    return "CRITICAL"


def _load_params(path: Path):
    if path.suffix.lower() == ".json":
        return json.loads(path.read_text(encoding="utf-8"))
    return joblib.load(path)


def _local_drivers(model, X_row: pd.DataFrame, feature_cols: list[str]) -> list[dict]:
    """Top SHAP drivers for one row; returns [] if SHAP is unavailable."""
    try:
        import shap

        explainer = shap.TreeExplainer(model)
        sv = explainer.shap_values(X_row)
        if isinstance(sv, list):
            sv = sv[1] if len(sv) == 2 else sv[0]
        if hasattr(sv, "values"):
            sv = sv.values
        values = np.asarray(sv)[0]
        ranked = sorted(
            zip(feature_cols, values), key=lambda kv: abs(kv[1]), reverse=True
        )
        return [{"feature": col, "shap": float(v)} for col, v in ranked[:3]]
    except Exception:
        return []


def score_company(
    model,
    preprocess_params,
    ratios: dict[str, float],
    industry_flags: dict | None = None,
    feature_cols: list[str] | None = None,
    threshold_policy: dict | None = None,
) -> dict:
    """Produce the distress_score.json schema for one company/year."""
    if model is None or preprocess_params is None:
        return {
            "company": None,
            "version": None,
            "fiscal_year": None,
            "distress_probability": None,
            "health_score": None,
            "grade": None,
            "top_drivers": [],
            "threshold_policy": threshold_policy or {
                "threshold": 0.0, "fn_cost": 10.0, "fp_cost": 1.0,
            },
        }
    cols = feature_cols or list(preprocess_params.keys())
    row = pd.DataFrame(
        [{col: ratios.get(col, np.nan) for col in cols}], columns=cols
    )
    X = transform(row, preprocess_params)
    proba = float(model.predict_proba(X)[:, 1][0])
    drivers = _local_drivers(model, X, cols)
    return {
        "company": None,
        "version": None,
        "fiscal_year": None,
        "distress_probability": proba,
        "health_score": int(round(100.0 * (1.0 - proba))),
        "grade": grade_for_probability(proba),
        "top_drivers": drivers,
        "threshold_policy": threshold_policy or {
            "threshold": 0.0, "fn_cost": 10.0, "fp_cost": 1.0,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Per-company CDEW inference (Task 7)")
    parser.add_argument("--company", required=True)
    parser.add_argument("--version", default="v1")
    parser.add_argument("--company-dir", default=None)
    parser.add_argument("--model", default=str(ROOT / "output" / "_cdew" / "models" / "aligned_xgboost.joblib"))
    parser.add_argument("--preprocess", default=str(ROOT / "output" / "_cdew" / "models" / "aligned_preprocess_params.joblib"))
    parser.add_argument("--feature-cols", default=str(EVAL_DIR / "aligned_feature_cols.json"))
    parser.add_argument("--threshold-policy", default=str(EVAL_DIR / "threshold_policy.json"))
    parser.add_argument("--output", default=None)
    parser.add_argument("--root", default=str(ROOT))
    args = parser.parse_args()

    root = Path(args.root)
    company_dir = Path(args.company_dir) if args.company_dir else (
        root / "output" / args.company / args.version
    )
    aligned_files = sorted(company_dir.glob("Y*/ratios/uci_aligned.json"))
    if not aligned_files:
        raise SystemExit(f"No uci_aligned.json found under {company_dir}")
    latest = aligned_files[-1]
    payload = json.loads(latest.read_text(encoding="utf-8"))
    ratios = {k: float(v) for k, v in payload["columns"].items()}
    feature_cols = json.loads(Path(args.feature_cols).read_text(encoding="utf-8"))
    model = joblib.load(args.model)
    params = _load_params(Path(args.preprocess))
    policy_path = Path(args.threshold_policy)
    policy = (
        json.loads(policy_path.read_text(encoding="utf-8"))
        if policy_path.exists()
        else None
    )

    result = score_company(
        model,
        params,
        ratios,
        feature_cols=feature_cols,
        threshold_policy=policy,
    )
    result["company"] = args.company
    result["version"] = args.version
    result["fiscal_year"] = payload.get("fiscal_year")
    result["model"] = str(Path(args.model).name)
    result["created_utc"] = datetime.now(timezone.utc).isoformat()

    out_path = Path(args.output) if args.output else (
        company_dir / "cross_year" / "distress_score.json"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    print(f"Written: {out_path}")


if __name__ == "__main__":
    main()
