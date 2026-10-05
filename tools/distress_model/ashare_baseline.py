"""A-share 27-feature CDEW baseline (Stage 0 of the pipeline-quality plan).

Goal
----
Solidify the *cross-market starting baseline* named in the quality plan's Stage 0:
the A-share 27-feature, ST-labeled distress model.  This module makes that
baseline *re-runnable* and *verifiable*:

1. Reproduces the paper's published OOF metrics (ROC-AUC / PR-AUC / Brier)
   straight from the stored OOF prediction file, so "same command -> same
   numbers" holds without re-training.
2. Loads the saved model artifact (XGBClassifier + keyed median + StandardScaler)
   and scores a company from its 27 A-share features, emitting the pipeline's
   ``distress_score.json`` schema.
3. Emits a feature-alignment report that maps each of the 27 A-share features
   to what the current per-company pipeline actually extracts, so the
   Stage 2/3 "feature dictionary" and data-source gap is explicit.

Reproducibility caveat (recorded in ``baseline_meta.json``)
----------------------------------------------------------
The *original* training script (fold split, random seed, feature-selection
step) was not persisted in either repo.  Therefore the 5-fold CV metrics can
NOT be exactly re-derived from artifacts alone.  What IS reproducible is:
  * the saved model's deterministic preprocessing + prediction, and
  * the OOF metrics, which come from ``ashare_oof27.csv`` (already computed
    out-of-fold predictions).  Re-computing those metrics is deterministic.

Usage
-----
    # Reproduce the paper's OOF metrics (deterministic)
    python ashare_baseline.py metrics

    # Load the model artifact and print its metadata (feature keys, classes)
    python ashare_baseline.py meta

    # Score one company from a JSON dict of its 27 A-share features
    python ashare_baseline.py score --features company_features.json \
        --company DemoEV --fiscal-year 2025 --out out.json

    # Build the 27-feature -> pipeline-ratio alignment report
    python ashare_baseline.py alignment --out feature_alignment.json

    # Emit a one-shot baseline report (metrics + meta + corpus scores)
    python ashare_baseline.py report --out-dir <writable-dir>

    # Emit per-company A-share baseline score files into each company's cross_year/
    # (does NOT overwrite the live Polish-model distress_score.json)
    python ashare_baseline.py company-scores
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score


# The A-share baseline artifacts are self-hosted inside the repo at
# ASHARE_LOCAL_DIR so this module is re-runnable without any external path
# dependency.  The capstone "Final Report" path is kept only as a fallback for
# provenance / override; set --root or ASHARE_BASELINE_ROOT to point elsewhere.
DEFAULT_ASHARE_ROOT = Path(__file__).resolve().parents[2] / "output" / "ashare_baseline"
_LOCAL_DIR = Path(r"<repo>\output\ashare_baseline")

# The canonical 27-feature model + its OOF predictions + its feature/spec JSON.
MODEL_FILE = "ashare_st27_model.joblib"
OOF_FILE = "ashare_oof27.csv"
FEATURES_FILE = "ashare_final_v2.json"
PANEL_FILE = "ashare_panel_v3.csv"


# --------------------------------------------------------------------------- #
# Grade mapping
# --------------------------------------------------------------------------- #
# The saved A-share model is a **binary** ST / non-ST classifier (classes 0/1).
# The quality plan describes a three-state normal/medium/critical target, but the
# deployed artifact is binary.  Stage 0 keeps the pipeline's four-grade mapping
# so distress_score.json stays schema-compatible, and records this discrepancy
# as a known flaw rather than silently inventing a three-class model.


def grade_for_probability(p: float) -> str:
    """Map a distress probability to the pipeline's four-grade scale."""
    if p < 0.05:
        return "LOW"
    if p < 0.15:
        return "MEDIUM"
    if p < 0.30:
        return "HIGH"
    return "CRITICAL"


# --------------------------------------------------------------------------- #
# Path resolution
# --------------------------------------------------------------------------- #


def _resolve_root(explicit: str | os.PathLike | None) -> Path:
    env = os.environ.get("ASHARE_BASELINE_ROOT")
    root = Path(explicit) if explicit else (Path(env) if env else None)
    # Prefer a local repo copy if present so the harness is self-contained.
    if _LOCAL_DIR.joinpath(MODEL_FILE).exists():
        return _LOCAL_DIR
    if root is not None and root.joinpath(MODEL_FILE).exists():
        return root
    return DEFAULT_ASHARE_ROOT


def _model_dir(root: Path) -> Path:
    return root


def _candidate_roots(root: Path) -> list[Path]:
    """Candidate dirs for the A-share artifacts, best-first."""
    # The model + panel live in work/ashare_cn; the OOF predictions live in
    # work/poster/V2/assets/figures.  Search both plus any local copy.
    work = root.parent if root.name == "ashare_cn" else root
    return [
        root,
        work / "poster" / "V2" / "assets" / "figures",
        work / "PosterV2" / "assets" / "figures",
        _LOCAL_DIR,
    ]


def _find_file(names: list[str], roots: list[Path]) -> Path | None:
    for r in roots:
        for n in names:
            cand = r / n
            if cand.exists():
                return cand
    return None


# --------------------------------------------------------------------------- #
# Baseline model loading + scoring
# --------------------------------------------------------------------------- #


def load_baseline(root: Path | None = None) -> dict:
    """Load the saved baseline artifact into a dict of its components."""
    rroot = _resolve_root(root)
    path = rroot / MODEL_FILE
    if not path.exists():
        raise FileNotFoundError(
            f"A-share baseline model not found: {path}. "
            "Set ASHARE_BASELINE_ROOT or pass --root to the capstone ashare_cn dir."
        )
    bundle = joblib.load(path)
    if not isinstance(bundle, dict) or "model" not in bundle:
        raise ValueError(
            "Unexpected baseline artifact format; expected dict with keys "
            "'model','median','scaler','keys'."
        )
    return {
        "root": rroot,
        "model": bundle["model"],
        "median": bundle["median"],
        "scaler": bundle["scaler"],
        "keys": list(bundle["keys"]),
    }


def score_from_features(
    features: dict[str, float],
    baseline: dict,
    company: str | None = None,
    version: str | None = None,
    fiscal_year: int | None = None,
    threshold_policy: dict | None = None,
) -> dict:
    """Score one company from its A-share features -> distress_score.json schema.

    Missing features are median-imputed with the *training* medians (no-peek:
    the medians were fit on the training split and frozen in the artifact).
    """
    cols = baseline["keys"]
    row = pd.DataFrame(
        [{c: features.get(c, np.nan) for c in cols}], columns=cols, dtype=float
    )
    # Median impute (training medians, not recomputed on this row).
    med = baseline["median"]
    for c in cols:
        row[c] = row[c].fillna(float(med[c]))
    X = baseline["scaler"].transform(row)
    proba = float(baseline["model"].predict_proba(X)[:, 1][0])
    return {
        "company": company,
        "version": version,
        "fiscal_year": fiscal_year,
        "distress_probability": proba,
        "health_score": int(round(100.0 * (1.0 - proba))),
        "grade": grade_for_probability(proba),
        "top_drivers": [],  # SHAP drivers deferred: needs per-row explainer run.
        "threshold_policy": threshold_policy
        or {"model": "xgboost", "threshold": 0.5, "fn_cost": 10.0, "fp_cost": 1.0},
        "model": MODEL_FILE,
        "label_def": "current ST/*ST status (binary)",
    }


def _shap_drivers(baseline: dict, row: pd.DataFrame) -> list[dict]:
    """Top-3 SHAP drivers for one scaled row (best-effort; [] if unavailable)."""
    try:
        import shap  # noqa: F401  (heavy optional dependency)

        # Requires the pre-transform feature frame for meaningful SHAP values.
        raw = row[baseline["keys"]].copy()
        for c in baseline["keys"]:
            raw[c] = raw[c].fillna(float(baseline["median"][c]))
        explainer = shap.TreeExplainer(baseline["model"])
        sv = explainer.shap_values(raw)
        if isinstance(sv, list):
            sv = sv[1] if len(sv) == 2 else sv[0]
        if hasattr(sv, "values"):
            sv = sv.values
        vals = np.asarray(sv)[0]
        ranked = sorted(
            zip(baseline["keys"], vals), key=lambda kv: abs(kv[1]), reverse=True
        )
        return [{"feature": k, "shap": float(v)} for k, v in ranked[:3]]
    except Exception:  # noqa: BLE001 - SHAP is optional here
        return []


# --------------------------------------------------------------------------- #
# Deterministic metric reproduction
# --------------------------------------------------------------------------- #


def reproduce_metrics(root: Path | None = None) -> dict:
    """Recompute the paper's OOF metrics from the stored OOF prediction file.""" 
    rroot = _resolve_root(root)
    oof_csv = _find_file([OOF_FILE], _candidate_roots(rroot))
    if oof_csv is None:
        raise FileNotFoundError(
            f"OOF file '{OOF_FILE}' not found under the candidate roots: "
            f"{[str(r) for r in _candidate_roots(rroot)]}"
        )
    df = pd.read_csv(oof_csv)
    y = df["label"].astype(int)
    p = df["xgboost"].astype(float)
    return {
        "n": int(len(df)),
        "positive": int(int(y.sum())),
        "roc_auc": round(float(roc_auc_score(y, p)), 4),
        "pr_auc": round(float(average_precision_score(y, p)), 4),
        "brier": round(float(brier_score_loss(y, p)), 4),
        "model": MODEL_FILE,
        "source": str(oof_csv),
        "note": ("OOF metrics are reproduced from stored out-of-fold predictions "
                 "in ashare_oof27.csv; the original fold/seed script was not "
                 "persisted, so 5-fold CV cannot be re-derived exactly."),
    }


# --------------------------------------------------------------------------- #
# 27-feature schema + alignment (Stage 2/3 input)
# --------------------------------------------------------------------------- #


FEATURE_SPEC = [
    # (key, human label, group, pipeline-alignment, source/notes)
    ("f_roeAvg", "Return on equity (avg)", "profitability", "derivable", "ROE from net_profit/equity"),
    ("f_npMargin", "Net profit margin", "profitability", "aligned", "net_profit / revenue"),
    ("f_gpMargin", "Gross profit margin", "profitability", "aligned", "gross_margin in ratios.json"),
    ("f_netProfit", "Net profit (abs)", "profitability", "aligned", "net_profit in ratios.json"),
    ("f_epsTTM", "EPS (TTM)", "market", "missing", "needs share count / market data"),
    ("f_MBRevenue", "Main business revenue", "scale", "partial", "revenue in ratios.json"),
    ("f_totalShare", "Total shares", "market", "missing", "market data, not in ratios"),
    ("f_currentRatio", "Current ratio", "liquidity", "missing", "not extracted per company"),
    ("f_cashRatio", "Cash ratio", "liquidity", "missing", "not extracted per company"),
    ("f_YOYLiability", "YoY liability growth", "growth", "missing", "needs 2-yr liabilities"),
    ("f_liabilityToAsset", "Liabilities / assets", "solvency", "derivable", "D/E -> L/A = D/E/(1+D/E)"),
    ("f_assetToEquity", "Assets / equity", "solvency", "derivable", "1 + D/E"),
    ("f_CAToAsset", "Current assets / assets", "liquidity", "missing", "needs current-asset balance"),
    ("f_ebitToInterest", "EBIT / interest", "coverage", "missing", "needs interest expense"),
    ("f_CFOToOR", "CFO / operating revenue", "cashflow", "missing", "needs operating cash flow"),
    ("f_CFOToGr", "CFO / gross revenue", "cashflow", "missing", "needs operating cash flow"),
    ("f_NRTurnRatio", "Net-receivable turnover", "efficiency", "partial", "DSO relates inversely"),
    ("f_NRTurnDays", "Net-receivable turnover days", "efficiency", "aligned", "~ DSO in ratios.json"),
    ("f_INVTurnRatio", "Inventory turnover", "efficiency", "partial", "DIO relates inversely"),
    ("f_CATurnRatio", "Current-asset turnover", "efficiency", "partial", "revenue / current assets"),
    ("f_AssetTurnRatio", "Asset turnover", "efficiency", "derivable", "revenue / total_assets"),
    ("f_YOYEquity", "YoY equity growth", "growth", "missing", "needs 2-yr equity"),
    ("f_YOYAsset", "YoY asset growth", "growth", "missing", "needs 2-yr assets"),
    ("f_YOYNI", "YoY net income growth", "growth", "partial", "revenue_growth_pct proxy"),
    ("f_dupontPnitoni", "DuPont: NI/EBT", "dupont", "derivable", "tax-rate structure"),
    ("f_dupontTaxBurden", "DuPont: tax burden", "dupont", "derivable", "tax rate from P&L"),
    ("f_CFOToNP", "CFO / net profit", "cashflow", "missing", "needs operating cash flow"),
]


def alignment_report() -> list[dict]:
    """Emit the 27-feature -> pipeline-ratio alignment table."""
    return [
        {
            "feature": key,
            "label": label,
            "group": group,
            "pipeline_alignment": alignment,
            "source": source,
        }
        for key, label, group, alignment, source in FEATURE_SPEC
    ]


def alignment_summary(rows: list[dict]) -> dict:
    from collections import Counter

    c = Counter(r["pipeline_alignment"] for r in rows)
    return {
        "total": len(rows),
        "by_alignment": dict(c),
        "aligned_or_derivable": c["aligned"] + c["derivable"],
        "partial": c["partial"],
        "missing": c["missing"],
    }


# --------------------------------------------------------------------------- #
# Report
# --------------------------------------------------------------------------- #


def baseline_meta() -> dict:
    """Structural metadata about the baseline artifact (independent of loading)."""
    return {
        "baseline_name": "A-share 27-feature ST-labeled CDEW",
        "quality_plan_stage": "0",
        "model": "XGBClassifier (binary)",
        "classes": ["non_ST", "ST"],
        "label_def": (
            "1 if the stock's CURRENT name contains 'ST'/'*ST' at fetch time "
            "(baostock query_stock_basic). This is a CURRENT-STATUS label, NOT a "
            "historical reconstruction."
        ),
        "n_features": 27,
        "feature_keys": [f[0] for f in FEATURE_SPEC],
        "known_flaws": [
            "ST label is a current-name/status label, not a historical time-point label.",
            "Industry is NOT a classifier feature (paper: one-hot industry gave ROC-AUC "
            "0.896 vs 0.895, no gain); industry must drive the feature *subset*, not "
            "act as an input column.",
            "Case-control imbalance: panel is deliberately balanced (272 ST / 138 non-ST), "
            "not population prevalence; needs reweighting for real-world prevalence.",
            "Smallest sectors (Real Estate & Hospitality 7 firms, Construction & Infra 18) "
            "are too small for per-sector models; per-industry models are NOT feasible.",
            "The artifact is a BINARY classifier; the plan's 'three-state "
            "(normal/medium/critical)' is a thresholded interpretation, not a native "
            "three-class model.",
        ],
        "quality_plan_metric_claim": (
            "plan quotes '5-fold CV RF 0.909 / XGB 0.896; deployed XGB OOF "
            "ROC-AUC 0.895 / PR-AUC 0.924 / Brier 0.155'. Those CV numbers match "
            "the 40-feature v3 generation (v3_model.json); the 27-feature OOF here "
            "is ROC-AUC ~0.892 / PR-AUC ~0.922 / Brier ~0.134. Terminology in the "
            "plan conflates the 27-feature and 40-feature builds."
        ),
    }


def make_report(out_dir: Path) -> dict:
    """Write the one-shot baseline report (meta + metrics + corpus score ref)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    meta = baseline_meta()
    metrics = reproduce_metrics()
    alignment = alignment_report()
    summary = alignment_summary(alignment)
    # Corpus companies scored by the paper's own score file (sourced, not re-derived).
    paper_scores = _load_paper_corpus_scores()
    doc = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "baseline_meta": meta,
        "reproduced_metrics": metrics,
        "feature_alignment": {"rows": alignment, "summary": summary},
        "corpus_scores_source": paper_scores,
        "model_path_confirmation": {
            "infer_py_loads": "output/_cdew/models/aligned_xgboost.joblib",
            "that_is": "POLISH / UCI-aligned 25-feature binary model (OLD PATH)",
            "target_baseline": MODEL_FILE,
            "action": (
                "Confirmed: the repo CDEW inference chain still loads the POLISH "
                "model. It is marked as the OLD PATH. Switching infer.py/run_cdew.py "
                "to the A-share 27-feature model is deferred to Stage 2, per the "
                "quality plan."
            ),
        },
    }
    (out_dir / "baseline_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (out_dir / "baseline_metrics.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (out_dir / "feature_alignment.json").write_text(
        json.dumps(doc["feature_alignment"], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (out_dir / "baseline_report.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return doc


def _load_paper_corpus_scores() -> dict:
    """Map the 9 A-share corpus companies to the paper's published probabilities.

    These come from ``ashare_12scores.json`` in the capstone ashare_cn dir, which
    is the source the paper reports. They are sourced (not re-derived) because the
    per-company 27-feature rows were never persisted in the repo; this is recorded
    as the Stage 2/3 feature-alignment gap.
    """
    root = _resolve_root(None)
    p = root / "ashare_12scores.json"
    if not p.exists():
        return {"source": None, "note": "ashare_12scores.json not found", "scores": []}
    rows = json.loads(p.read_text(encoding="utf-8"))
    out = []
    for r in rows:
        prob = float(r.get("prob", 0.0))
        out.append(
            {
                "company": r.get("company"),
                "code": r.get("code"),
                "distress_probability": prob,
                "health_score": int(round(100.0 * (1.0 - prob))),
                "grade": grade_for_probability(prob),
                "paper_class": r.get("class"),
                "source": "paper ashare_12scores.json",
            }
        )
    return {"source": str(p), "scores": out}


def write_company_scores(root: Path | None = None, repo_root: Path | None = None) -> list[dict]:
    """Emit a per-company A-share baseline score file in the pipeline schema.

    For each A-share corpus company present in the paper's score file, write
    ``{Company}/v1/cross_year/distress_score.ashare_baseline.json``.  This does NOT
    overwrite the live ``distress_score.json`` (which reflects the Polish model on the
    OLD PATH).  The file is flagged ``source: paper`` because the per-company 27-feature
    rows are not yet stored; once Stage 2/3 backfills them, ``score`` can regenerate the
    same file from features.

    Returns the list of written file paths.
    """
    rroot = _resolve_root(root)
    repo = Path(repo_root) if repo_root else Path(r"<repo>")
    corpus = _load_paper_corpus_scores()
    written = []
    for s in corpus["scores"]:
        company = s.get("company")
        if not company:
            continue
        target = (
            repo / "output" / company / "v1" / "cross_year"
            / "distress_score.ashare_baseline.json"
        )
        payload = {
            "company": company,
            "version": "v1",
            "fiscal_year": None,
            "distress_probability": s["distress_probability"],
            "health_score": s["health_score"],
            "grade": s["grade"],
            "top_drivers": [],
            "threshold_policy": {"model": "xgboost", "threshold": 0.5,
                                 "fn_cost": 10.0, "fp_cost": 1.0},
            "model": MODEL_FILE,
            "label_def": "current ST/*ST status (binary)",
            "source": s["source"],
            "paper_class": s["paper_class"],
            "created_utc": datetime.now(timezone.utc).isoformat(),
        }
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                          encoding="utf-8")
        written.append(str(target))
    return written


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def main() -> None:
    parser = argparse.ArgumentParser(description="A-share 27-feature CDEW baseline")
    parser.add_argument("--root", default=None, help="capstone ashare_cn dir override")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("meta", help="print baseline metadata")

    sub.add_parser("metrics", help="reproduce OOF metrics")

    p_score = sub.add_parser("score", help="score a company from its 27 features")
    p_score.add_argument("--features", required=True, help="JSON/CSV of features")
    p_score.add_argument("--company", default=None)
    p_score.add_argument("--fiscal-year", type=int, default=None)
    p_score.add_argument("--out", default=None, help="write distress_score.json here")

    p_align = sub.add_parser("alignment", help="emit 27-feature alignment report")
    p_align.add_argument("--out", default=None)

    p_report = sub.add_parser("report", help="write one-shot baseline report")
    p_report.add_argument("--out-dir", required=True)

    sub.add_parser("company-scores",
                   help="emit per-company A-share baseline distress_score file")

    args = parser.parse_args()

    if args.cmd == "meta":
        print(json.dumps(baseline_meta(), ensure_ascii=False, indent=2))
    elif args.cmd == "metrics":
        print(json.dumps(reproduce_metrics(args.root), ensure_ascii=False, indent=2))
    elif args.cmd == "score":
        base = load_baseline(args.root)
        feats_path = Path(args.features)
        feats = json.loads(feats_path.read_text(encoding="utf-8"))
        result = score_from_features(
            feats,
            base,
            company=args.company,
            fiscal_year=args.fiscal_year,
        )
        if args.out:
            Path(args.out).write_text(
                json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            print(f"Written: {args.out}")
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.cmd == "alignment":
        rows = alignment_report()
        out = {"rows": rows, "summary": alignment_summary(rows)}
        if args.out:
            Path(args.out).write_text(
                json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            print(f"Written: {args.out}")
        print(json.dumps(out, ensure_ascii=False, indent=2))
    elif args.cmd == "report":
        doc = make_report(Path(args.out_dir))
        print(json.dumps(doc, ensure_ascii=False, indent=2))
    elif args.cmd == "company-scores":
        written = write_company_scores(args.root)
        print(json.dumps({"written": written}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
