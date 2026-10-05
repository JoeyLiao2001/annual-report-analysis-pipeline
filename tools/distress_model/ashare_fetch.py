"""A-share ST-labeled external-validity probe for CDEW (Task 13, optional).

Provider chain: AkShare primary -> baostock fallback. As of 2026-08-06 the
AkShare/East Money endpoints consistently drop connections, so baostock is
used. The sample aligns the five baostock summary ratios that map to the
UCI intersection feature set; the remaining features are NaN (median
imputed at evaluation). ST label = currently ST/*ST-listed as of the fetch
date (current-status label; historical reconstruction documented as a
limitation).

Usage:
    python ashare_fetch.py --n 300 --seed 42
    python ashare_fetch.py --evaluate
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score

ROOT = Path(__file__).resolve().parents[2]
ASHARE_DIR = ROOT / "output" / "_cdew" / "ashare"
EVAL_DIR = ROOT / "output" / "_cdew" / "evaluation"

FEATURE_KEYS = [
    "X4", "X12", "X19", "X20", "X21", "X23", "X27", "X32", "X33", "X39",
    "X40", "X42", "X43", "X44", "X45", "X46", "X47", "X52", "X55", "X56",
    "X58", "X60", "X61", "X62", "X63",
]


def fetch_sample(n: int = 300, seed: int = 42) -> pd.DataFrame:
    """Fetch an A-share sample with baostock summary ratios + ST label."""
    import baostock as bs

    bs.login()
    try:
        basic = []
        rs = bs.query_stock_basic()
        while rs.error_code == "0" and rs.next():
            basic.append(rs.get_row_data())
        basic_df = pd.DataFrame(
            basic,
            columns=["code", "code_name", "ipoDate", "outDate", "type", "status"],
        )
        stocks = basic_df[
            basic_df["code"].str.match(r"^(sh\.60|sh\.68|sz\.00|sz\.30)")
        ].copy()
        stocks["is_st"] = stocks["code_name"].str.contains("ST", case=False, na=False)

        st_codes = set(stocks.loc[stocks["is_st"], "code"])
        non_st = stocks.loc[~stocks["is_st"], "code"].tolist()
        rng = np.random.default_rng(seed)
        st_list = sorted(st_codes)
        st_sample = list(
            rng.choice(st_list, size=min(len(st_list), n // 2), replace=False)
        )
        need_non_st = max(0, n - len(st_sample))
        non_st_sample = list(rng.choice(non_st, size=min(need_non_st, len(non_st)), replace=False))
        sample_codes = sorted(st_sample + non_st_sample)
        print(f"ST codes: {len(st_sample)}; sampling {len(sample_codes)} total")

        rows = []
        for i, code in enumerate(sample_codes):
            try:
                profit = bs.query_profit_data(code=code, year=2024, quarter=4)
                profit_rows = []
                while profit.error_code == "0" and profit.next():
                    profit_rows.append(dict(zip(profit.fields, profit.get_row_data())))
                balance = bs.query_balance_data(code=code, year=2024, quarter=4)
                balance_rows = []
                while balance.error_code == "0" and balance.next():
                    balance_rows.append(dict(zip(balance.fields, balance.get_row_data())))
                if not profit_rows or not balance_rows:
                    continue
                p = profit_rows[0]
                b = balance_rows[0]
                row = {
                    "code": code,
                    "name": stocks.loc[stocks["code"] == code, "code_name"].iloc[0],
                    "label": int(code in st_codes),
                    "stat_date": b.get("statDate", ""),
                }
                for col in FEATURE_KEYS:
                    row[col] = np.nan
                try:
                    row["X4"] = float(b["currentRatio"])
                    row["X46"] = float(b["quickRatio"])
                    row["X19"] = float(p["gpMargin"]) / 100.0
                    row["X23"] = float(p["npMargin"]) / 100.0
                    row["X2"] = float(b["liabilityToAsset"]) / 100.0
                    row["X10"] = 1.0 - float(b["liabilityToAsset"]) / 100.0
                except (KeyError, TypeError, ValueError):
                    pass
                rows.append(row)
            except Exception as exc:  # noqa: BLE001 - per-stock resilience
                print(f"  {code} failed: {type(exc).__name__} {str(exc)[:80]}")
            if (i + 1) % 50 == 0:
                print(f"  fetched {i + 1}/{len(sample_codes)}")
            time.sleep(0.05)
        df = pd.DataFrame(rows)
        return df
    finally:
        bs.logout()


def evaluate_ashare(model_path: str, X_test: pd.DataFrame, y_test: pd.Series) -> dict:
    """Evaluate the aligned UCI model on the A-share sample."""
    params = joblib.load(ROOT / "output" / "_cdew" / "models" / "aligned_preprocess_params.joblib")
    model = joblib.load(model_path)
    X = X_test.copy()
    for col in params:
        if col not in X.columns:
            X[col] = np.nan
    X = X[list(params.keys())]
    for col in X.columns:
        X[col] = X[col].astype(float)
    # median impute missing with training medians (transform handles NaN via params)
    Xt = X.copy()
    for col in X.columns:
        Xt[col] = Xt[col].fillna(params[col]["median"])
    proba = model.predict_proba(Xt)[:, 1]
    return {
        "pr_auc": float(average_precision_score(y_test, proba)),
        "auc": float(roc_auc_score(y_test, proba)),
        "brier": float(brier_score_loss(y_test, proba)),
        "proba": proba,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="A-share probe (Task 13)")
    parser.add_argument("--n", type=int, default=300)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--evaluate", action="store_true")
    parser.add_argument("--root", default=str(ROOT))
    args = parser.parse_args()
    root = Path(args.root)
    ASHARE_DIR.mkdir(parents=True, exist_ok=True)

    if args.evaluate:
        sample = pd.read_csv(ASHARE_DIR / "ashare_sample.csv")
        model_path = root / "output" / "_cdew" / "models" / "aligned_xgboost.joblib"
        result = evaluate_ashare(str(model_path), sample[FEATURE_KEYS], sample["label"])
        baseline = json.loads(
            (EVAL_DIR / "model_comparison_aligned.json").read_text(encoding="utf-8")
        )["test_metrics"]["xgboost"]
        md = [
            "# A-Share External-Validity Probe (Task 13)",
            "",
            f"Generated: {datetime.now(timezone.utc).isoformat()}",
            f"Samples: {len(sample)} (ST: {int(sample['label'].sum())})",
            f"Feature alignment: {sum(sample[FEATURE_KEYS].notna().any().values)} of 25 "
            "intersection features obtainable from baostock summary indicators.",
            "",
            "| Metric | UCI aligned test | A-share probe |",
            "|--------|------------------|---------------|",
            f"| PR-AUC | {baseline['pr_auc']:.3f} | {result['pr_auc']:.3f} |",
            f"| ROC-AUC | {baseline['auc']:.3f} | {result['auc']:.3f} |",
            f"| Brier | {baseline['brier']:.3f} | {result['brier']:.3f} |",
            "",
            "Limitations: current ST-status label (no historical reconstruction), "
            "5/25 features aligned, single year (2024) of summary ratios, sample "
            "drawn with fixed seed from baostock.",
        ]
        (ASHARE_DIR / "ashare_evaluation.md").write_text("\n".join(md), encoding="utf-8")
        print("\n".join(md))
        return

    df = fetch_sample(n=args.n, seed=args.seed)
    df.to_csv(ASHARE_DIR / "ashare_sample.csv", index=False)
    print(f"Saved {len(df)} rows to {ASHARE_DIR / 'ashare_sample.csv'}")
    print(df[["code", "name", "label"]].head(10).to_string(index=False))


if __name__ == "__main__":
    main()
