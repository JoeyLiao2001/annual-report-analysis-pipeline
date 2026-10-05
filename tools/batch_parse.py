"""
Batch PDF parser — run overnight, independent of Claude Code.

Usage (run in plain PowerShell/CMD, NOT in Claude Code):
    python tools/batch_parse.py

Logs progress to input/parsed/_batch_log.txt
Auto-skips already-parsed files (checkpoint resume).
"""

import sys
import time
from pathlib import Path
from datetime import datetime

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))
from tools.parse_pdf import parse_pdf

PDF_DIR = Path(__file__).parent.parent / "input" / "pdfs"
LOG_FILE = Path(__file__).parent.parent / "input" / "parsed" / "_batch_log.txt"


def main():
    pdfs = sorted(PDF_DIR.glob("*.pdf"))
    total = len(pdfs)

    with open(LOG_FILE, "a", encoding="utf-8") as log:
        log.write(f"\n{'='*60}\n")
        log.write(f"BATCH START: {datetime.now()} | {total} PDFs\n")
        log.write(f"{'='*60}\n")

    print(f"Batch parse: {total} PDFs")
    print(f"Log: {LOG_FILE}")
    print()

    ok = 0
    skip = 0
    fail = 0
    t_start = time.time()

    for i, pdf_path in enumerate(pdfs):
        name = pdf_path.stem
        out_path = pdf_path.parent.parent / "parsed" / f"{name}_final.html"

        if out_path.exists():
            print(f"[{i+1}/{total}] SKIP {name} (already parsed)")
            with open(LOG_FILE, "a", encoding="utf-8") as log:
                log.write(f"SKIP {name}\n")
            skip += 1
            continue

        print(f"[{i+1}/{total}] {name} ... ", end="", flush=True)
        t0 = time.time()

        try:
            parse_pdf(str(pdf_path), str(out_path))
            elapsed = time.time() - t0
            print(f"OK ({elapsed:.0f}s)")
            with open(LOG_FILE, "a", encoding="utf-8") as log:
                log.write(f"OK   {name} ({elapsed:.0f}s)\n")
            ok += 1
        except Exception as e:
            elapsed = time.time() - t0
            print(f"FAIL ({elapsed:.0f}s): {e}")
            with open(LOG_FILE, "a", encoding="utf-8") as log:
                log.write(f"FAIL {name}: {e}\n")
            fail += 1

    total_time = time.time() - t_start
    summary = (
        f"\n{'='*60}\n"
        f"BATCH DONE: {datetime.now()}\n"
        f"Total: {total} | OK: {ok} | Skip: {skip} | Fail: {fail}\n"
        f"Time: {total_time/60:.0f} min\n"
        f"{'='*60}\n"
    )
    print(summary)
    with open(LOG_FILE, "a", encoding="utf-8") as log:
        log.write(summary)


if __name__ == "__main__":
    main()
