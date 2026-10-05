"""Data loader for the UCI Polish Companies Bankruptcy dataset.

Task 1: Data loader and EDA.

Dataset format (verified 2026-08-06):
- The UCI archive (id 365) contains WEKA ARFF files, not CSVs:
  1year.arff .. 5year.arff.
- Each ARFF declares 64 numeric attributes named Attr1..Attr64 plus a
  nominal target attribute `class` with values {0, 1}.
- `class == 1` means the company went bankrupt within the forecasting
  period; `class == 0` means it did not.
- Per the official UCI dataset page, the outcome horizon depends on the
  file: 1year.arff -> bankruptcy status after 5 years, 2year.arff -> 4
  years, 3year.arff -> 3 years, 4year.arff -> 2 years, 5year.arff -> 1
  year. See output/_cdew/evaluation/label_notes.md for the full record.

This loader normalizes the schema to X1..X64 + label for the rest of the
pipeline (preprocess, train, explain, infer).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
from scipy.io import arff


def _normalize_arff_frame(raw: Any) -> pd.DataFrame:
    """Convert the scipy ARFF record array into the pipeline schema."""
    df = pd.DataFrame.from_records(raw)
    # scipy returns the nominal `class` column as bytes (b'0' / b'1').
    if "class" in df.columns and "label" not in df.columns:
        df = df.rename(columns={"class": "label"})
    if df["label"].dtype == object:
        df["label"] = df["label"].map(
            lambda v: int(v) if isinstance(v, bytes) else int(v)
        )
    # Normalize feature names Attr1..Attr64 -> X1..X64.
    rename = {f"Attr{i}": f"X{i}" for i in range(1, 65)}
    df = df.rename(columns=rename)
    return df


def load_year(path: str) -> pd.DataFrame:
    """Load one prediction-year ARFF file into a pandas DataFrame.

    Returns a frame with columns X1..X64 and an integer `label`
    (1 = bankrupt within the forecasting period, 0 = otherwise).
    """
    data, _meta = arff.loadarff(str(Path(path)))
    return _normalize_arff_frame(data)


def load_all_years(dir_path: str, years: list[int]) -> dict[int, pd.DataFrame]:
    """Load several prediction years as {year: DataFrame}.

    File naming convention in this dataset: {year}year.arff
    (e.g. 1year.arff, 2year.arff, ...).
    """
    root = Path(dir_path)
    return {y: load_year(str(root / f"{y}year.arff")) for y in years}
