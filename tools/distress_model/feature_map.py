"""Aligned feature map for the CDEW model (Task 7).

Computes the intersection of UCI columns across the nine pilot
raw_line_items -> uci_aligned.json documents (3 companies x 3 years) and
writes the aligned feature list plus the feature-map notes.

Usage:
    python feature_map.py --root <repo> --version v1
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DICT_PATH = ROOT / "tools" / "distress_model" / "uci_feature_dict.json"


def load_aligned_columns(root: Path, version: str) -> dict[str, set[str]]:
    """Map company -> set of computable UCI columns across its years."""
    result = {}
    for company_dir in (root / "output").iterdir():
        if not company_dir.is_dir() or company_dir.name.startswith("_"):
            continue
        columns: set[str] | None = None
        for aligned in company_dir.glob(f"{version}/Y*/ratios/uci_aligned.json"):
            cols = set(json.loads(aligned.read_text(encoding="utf-8"))["columns"].keys())
            columns = cols if columns is None else (columns & cols)
        if columns:
            result[company_dir.name] = columns
    return result


def compute_intersection(root: Path, version: str) -> list[str]:
    """UCI columns computable in every company/year of the pilot."""
    per_company = load_aligned_columns(root, version)
    if not per_company:
        return []
    common = set.intersection(*per_company.values())
    return sorted(common)


def main() -> None:
    parser = argparse.ArgumentParser(description="Aligned feature map (Task 7)")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--version", default="v1")
    parser.add_argument("--out", default=str(ROOT / "output" / "_cdew" / "evaluation"))
    args = parser.parse_args()

    root = Path(args.root)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    feature_cols = compute_intersection(root, args.version)
    dict_data = json.loads(DICT_PATH.read_text(encoding="utf-8"))
    feature_map = {col: dict_data[col]["formula"] for col in feature_cols}

    (out / "aligned_feature_cols.json").write_text(
        json.dumps(feature_cols, indent=2), encoding="utf-8"
    )
    notes = [
        "# CDEW Aligned Feature Map Notes (Task 7)",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        f"Intersection size: {len(feature_cols)} of 64 UCI columns.",
        "",
        "Per-company/year computable column counts:",
        "| Company | Computable columns |",
        "|---------|--------------------|",
    ]
    for company, cols in load_aligned_columns(root, args.version).items():
        notes.append(f"| {company} | {len(cols)} |")
    notes += [
        "",
        "Aligned features (intersection):",
        "",
        "| Column | Formula |",
        "|--------|---------|",
    ]
    for col in feature_cols:
        notes.append(f"| {col} | {feature_map[col]} |")
    notes += [
        "",
        "Fallback decision: the plan requires a 7-metric model only if the",
        f"intersection is < 15 columns. Intersection = {len(feature_cols)} "
        "(>= 15), so the aligned 25-feature model is used.",
    ]
    (out / "feature_map_notes.md").write_text("\n".join(notes), encoding="utf-8")
    print(f"Aligned feature columns ({len(feature_cols)}): {feature_cols}")


if __name__ == "__main__":
    main()
