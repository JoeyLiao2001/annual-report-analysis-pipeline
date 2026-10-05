"""Deterministic preprocessing for the CDEW model (Task 2).

Winsorization (P1/P99), median imputation, and z-scoring are fitted on the
training split only to prevent leakage. transform() applies the stored
train statistics to any new data, so validation/test/company features are
always scaled with training parameters.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


def fit_transform(
    X_train: pd.DataFrame, y_train: pd.Series
) -> tuple[pd.DataFrame, dict[str, dict[str, float]]]:
    """Fit preprocessing parameters on training data and return scaled data.

    Parameters
    ----------
    X_train : pandas DataFrame with numeric columns.
    y_train : ignored by the transformation; kept for interface symmetry
        with the downstream training pipeline.

    Returns
    -------
    (X_scaled, params): the transformed frame and a JSON-serializable dict
    of per-column statistics.
    """
    params: dict[str, dict[str, float]] = {}
    Xt = X_train.copy()
    for col in Xt.columns:
        vals = Xt[col].to_numpy(dtype=np.float64)
        lo = float(np.nanquantile(vals, 0.01))
        hi = float(np.nanquantile(vals, 0.99))
        clipped = np.clip(vals, lo, hi)
        median = float(np.nanmedian(clipped))
        mean = float(np.nanmean(clipped))
        std = float(np.nanstd(clipped))
        if not np.isfinite(std) or std == 0.0:
            # Degenerate column: no scale information, use std=1 so z-scores
            # reduce to mean-centering and the transform stays well-defined.
            std = 1.0
        params[col] = {"lo": lo, "hi": hi, "median": median, "mean": mean, "std": std}
        imputed = np.where(np.isnan(clipped), median, clipped)
        Xt[col] = (imputed - mean) / std
    return Xt, params


def transform(X: pd.DataFrame, params: dict[str, dict[str, float]]) -> pd.DataFrame:
    """Apply fitted preprocessing parameters to new data."""
    Xt = X.copy()
    for col, p in params.items():
        if col not in Xt.columns:
            continue
        vals = Xt[col].to_numpy(dtype=np.float64)
        clipped = np.clip(vals, p["lo"], p["hi"])
        imputed = np.where(np.isnan(clipped), p["median"], clipped)
        Xt[col] = (imputed - p["mean"]) / p["std"]
    return Xt


def save_params(params: dict[str, Any], path: str) -> None:
    """Persist fitted parameters as JSON."""
    Path(path).write_text(json.dumps(params, indent=2), encoding="utf-8")


def load_params(path: str) -> dict[str, Any]:
    """Load fitted parameters from JSON."""
    return json.loads(Path(path).read_text(encoding="utf-8"))
