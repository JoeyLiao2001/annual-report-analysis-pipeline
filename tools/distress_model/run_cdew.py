"""One-command CDEW orchestrator (Task 9).

Chains inference (distress_score.json) and report augmentation
(_CDEW.html) for one company. Idempotent: existing outputs are skipped
unless --force is given.

Usage:
    python run_cdew.py --company DemoEV --version v1
    python run_cdew.py --company DemoEV --version v1 --force
    python run_cdew.py --company DemoEV --version v1 --score-only
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools" / "distress_model"


def run_cdew(
    company: str,
    version: str = "v1",
    root: Path | str | None = None,
    force: bool = False,
    augment: bool = True,
    model: str | None = None,
    preprocess: str | None = None,
    feature_cols: str | None = None,
    threshold_policy: str | None = None,
) -> dict:
    """Score a company and (optionally) augment its report; idempotent."""
    root = Path(root) if root else ROOT
    vdir = root / "output" / company / version
    score_path = vdir / "cross_year" / "distress_score.json"
    report_path = (
        root / "output" / "_cdew" / "reports"
        / f"{company}_{version}_3Y_Report_CDEW.html"
    )
    result = {
        "company": company,
        "version": version,
        "score_written": False,
        "score_skipped": False,
        "report_written": False,
        "report_skipped": False,
        "created_utc": datetime.now(timezone.utc).isoformat(),
    }

    if score_path.exists() and not force:
        result["score_skipped"] = True
    else:
        cmd = [
            sys.executable, str(TOOLS / "infer.py"),
            "--company", company, "--version", version,
            "--root", str(root),
        ]
        for opt, value in (
            ("--model", model), ("--preprocess", preprocess),
            ("--feature-cols", feature_cols),
            ("--threshold-policy", threshold_policy),
        ):
            if value:
                cmd += [opt, value]
        subprocess.run(cmd, check=True, cwd=str(TOOLS))
        result["score_written"] = True

    if augment:
        if report_path.exists() and not force:
            result["report_skipped"] = True
        else:
            subprocess.run(
                [
                    sys.executable, str(TOOLS / "render_cdew_report.py"),
                    "--company", company, "--version", version,
                    "--root", str(root),
                ],
                check=True,
                cwd=str(TOOLS),
            )
            result["report_written"] = True
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="CDEW orchestrator (Task 9)")
    parser.add_argument("--company", required=True)
    parser.add_argument("--version", default="v1")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--score-only", action="store_true")
    parser.add_argument("--model", default=None)
    parser.add_argument("--preprocess", default=None)
    parser.add_argument("--feature-cols", default=None)
    parser.add_argument("--threshold-policy", default=None)
    args = parser.parse_args()

    result = run_cdew(
        args.company,
        version=args.version,
        root=args.root,
        force=args.force,
        augment=not args.score_only,
        model=args.model,
        preprocess=args.preprocess,
        feature_cols=args.feature_cols,
        threshold_policy=args.threshold_policy,
    )
    print(json_dump := __import__("json").dumps(result, indent=2))


if __name__ == "__main__":
    main()
