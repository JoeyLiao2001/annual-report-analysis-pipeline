#!/usr/bin/env python3
"""
run_multi_year.py — Deterministic pre-processor for multi-year pipeline.

Runs ALL steps that don't require an LLM, leaving only the agent calls
for the Claude Code Workflow engine to execute.

Usage:
  python tools/run_multi_year.py <company> <year1> <year2> <year3> [--compress]

Steps (all deterministic, zero LLM tokens):
  1. Verify 3 years of HTML exist in input/parsed/
  2. (optional) Compress each year's HTML via headroom_compress.py
  3. Chapter detection + tag merge for each year
  4. Per-year finance_calc.py → ratios.json
  5. Cross-year contradiction_calc.py → quant_flags.json
  6. Cross-year industry_benchmark.py → industry_flags.json

Output:
  output/{company}/
    Y{year}/
      tagged/finance.md, strategy.md
      finance/ratios.json
    cross_year/
      quant_flags.json
      industry_flags.json
"""

import json
import subprocess
import sys
from pathlib import Path

# Fix: force UTF-8 on Windows terminals
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# Paths relative to this repo/ root
ROOT = Path(__file__).resolve().parent.parent
INPUT_PARSED = ROOT / "input" / "parsed"
OUTPUT = ROOT / "output"
TOOLS = ROOT / "tools"

def cmd(args, desc=""):
    """Run a command and return (success, output)."""
    print(f"  [{desc or args[0].split('/')[-1]}] {' '.join(map(str, args))}")
    result = subprocess.run(
        args, capture_output=True, text=True,
        cwd=str(ROOT)
    )
    if result.returncode != 0:
        print(f"    ERROR: {result.stderr.strip()[-200:]}")
        return False, result.stderr
    if result.stdout:
        # Print first 3 lines of output
        lines = result.stdout.strip().split('\n')
        for line in lines[:3]:
            print(f"    {line}")
        if len(lines) > 3:
            print(f"    ... ({len(lines)} lines total)")
    return True, result.stdout


def verify_inputs(company, years):
    """Check that all 3 years of HTML exist."""
    print(f"\n{'='*60}")
    print(f"Step 0: Verify HTML inputs for {company} ({years})")
    print(f"{'='*60}")

    all_ok = True
    for y in years:
        html_path = INPUT_PARSED / f"{company}{y}_final.html"
        if html_path.exists():
            size_kb = html_path.stat().st_size / 1024
            print(f"  ✅ {html_path.name} ({size_kb:.0f} KB)")
        else:
            print(f"  ❌ {html_path.name} NOT FOUND")
            # Try fuzzy match
            candidates = sorted(INPUT_PARSED.glob(f"*{company}*{y}*final.html"))
            if candidates:
                print(f"     Did you mean: {candidates[0].name}?")
            all_ok = False

    return all_ok


def compress_year(company, year):
    """Compress one year's HTML."""
    html_path = INPUT_PARSED / f"{company}{year}_final.html"
    out_dir = OUTPUT / company / f"Y{year}" / "compressed"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{company}{year}_compressed.txt"

    if out_path.exists():
        # Already compressed, check stats
        orig = html_path.stat().st_size
        comp = out_path.stat().st_size
        pct = round((1 - comp / orig) * 100, 1)
        print(f"  ⏭️  {out_path.name} exists ({pct}% reduction), skipping")
        return True

    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "headroom_compress", str(TOOLS / "headroom_compress.py")
    )
    hc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hc)

    stats = hc.compress_file(html_path, out_path, mode="fallback")
    print(f"  ✅ {stats['reduction_pct']}% reduction ({stats['original_bytes']:,} → {stats['compressed_bytes']:,} bytes)")
    return True


def detect_and_merge(company, year):
    """Run chapter_detector.py extract + merge for one year."""
    html_path = INPUT_PARSED / f"{company}{year}_final.html"
    route_path = OUTPUT / company / f"Y{year}" / "router" / "route.json"
    tagged_dir = OUTPUT / company / f"Y{year}" / "tagged"
    tagged_dir.mkdir(parents=True, exist_ok=True)

    # Use chapter_detector's Python API
    sys.path.insert(0, str(TOOLS))
    from chapter_detector import extract_headings, merge_chapters

    headings = extract_headings(str(html_path))
    print(f"    Extracted {len(headings)} heading candidates")

    if route_path.exists():
        route = json.loads(route_path.read_text(encoding='utf-8'))
        route_list = route.get("routing", route) if isinstance(route, dict) else route
    else:
        # Fallback: keyword-based routing from headings
        route_list = []
        for h in headings:
            title = h.get("title", "")
            tags = []
            if any(kw in title for kw in
                   ["财务", "利润", "资产", "负债", "现金", "审计", "附注",
                    "financial", "income", "balance", "audit", "notes"]):
                tags.append("finance")
            if any(kw in title for kw in
                   ["管理层", "经营", "业务", "风险", "行业", "战略", "发展",
                    "management", "business", "risk", "strategy", "outlook"]):
                tags.append("strategy")
            if any(kw in title for kw in
                   ["子公司", "关联", "担保", "分部", "entity", "subsidiary", "guarantee"]):
                tags.append("entities")
            if any(kw in title for kw in
                   ["重大", "事项", "并购", "诉讼", "event", "acquisition", "litigation"]):
                tags.append("events")
            if tags:
                route_list.append({"title": title, "page": h.get("page", 0), "tags": tags})

    merged = merge_chapters(route_list, str(html_path))

    for tag, content in merged.items():
        if content:
            out_path = tagged_dir / f"{tag}.md"
            out_path.write_text(content, encoding='utf-8')
            print(f"    {tag}.md: {len(content):,} chars")

    return len(merged.get("finance", "")) > 0 or len(merged.get("strategy", "")) > 0


def run_finance_calc(company, year):
    """Run finance_calc.py for one year."""
    finance_json = OUTPUT / company / f"Y{year}" / "finance" / "finance.json"
    ratios_json = OUTPUT / company / f"Y{year}" / "finance" / "ratios.json"

    if not finance_json.exists():
        print(f"    ⚠️  finance.json not found for Y{year}, skipping calc")
        return False

    fdata = json.loads(finance_json.read_text(encoding='utf-8'))

    sys.path.insert(0, str(TOOLS))
    from finance_calc import calculate

    ratios = calculate(fdata)
    ratios_json.parent.mkdir(parents=True, exist_ok=True)
    ratios_json.write_text(json.dumps(ratios, indent=2, ensure_ascii=False), encoding='utf-8')

    ccc = ratios.get("ccc_days")
    dso = ratios.get("dso_days")
    gm = ratios.get("gross_margin_pct")
    print(f"    DSO={dso:.0f}d  DPO={ratios.get('dpo_days',0):.0f}d  CCC={ccc:.0f}d  GM={gm:.1f}%")
    return True


def run_contradiction_calc(company, years):
    """Run cross-year contradiction_calc.py."""
    out_dir = OUTPUT / company / "cross_year"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "quant_flags.json"

    # Load 3 years of ratios
    year_data = {}
    for y in years:
        ratios_path = OUTPUT / company / f"Y{y}" / "finance" / "ratios.json"
        if ratios_path.exists():
            year_data[f"Y{y}"] = json.loads(ratios_path.read_text(encoding='utf-8'))
        else:
            print(f"    ⚠️  ratios.json missing for Y{y}")

    if len(year_data) < 2:
        print("    ❌ Need at least 2 years of data for cross-year analysis")
        return False

    sys.path.insert(0, str(TOOLS))
    from contradiction_calc import calculate_flags

    y1_data = json.dumps(year_data.get(f"Y{years[0]}", {}))
    y2_data = json.dumps(year_data.get(f"Y{years[1]}", {}))
    y3_data = json.dumps(year_data.get(f"Y{years[2]}", {}))

    result = calculate_flags(y1_data, y2_data, y3_data)

    out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')

    flags = json.loads(result["contradiction_flags"])
    print(f"    Overall: {result['overall_score']}")
    print(f"    Counts:  {result['summary_counts']}")
    print(f"    Flags:   {len(flags)}")
    return True


def run_industry_benchmark(company, years):
    """Run industry_benchmark.py to compute peer comparison flags.

    Requires: industry_benchmarks.json (reference data)
             ratios.json for all 3 years (from finance_calc)
             chapter_map.json with industry_classification (from Router LLM)
             quant_flags.json (from contradiction_calc, for cross-reference)
    """
    out_dir = OUTPUT / company / "cross_year"
    out_path = out_dir / "industry_flags.json"

    # Check prerequisites
    chapter_map_path = OUTPUT / company / f"Y{years[-1]}" / "router" / "chapter_map.json"
    if not chapter_map_path.exists():
        # Fall back to legacy route.json
        chapter_map_path = OUTPUT / company / f"Y{years[-1]}" / "router" / "route.json"
    if not chapter_map_path.exists():
        print("    ⚠️  No chapter_map.json or route.json found — Router must run first for industry classification")
        print("    ⏭️  Skipping industry benchmark (no industry label available)")
        return False

    benchmarks_path = ROOT / "reference" / "industry_benchmarks.json"
    if not benchmarks_path.exists():
        print("    ⚠️  industry_benchmarks.json not found — benchmark step skipped")
        print("    ⏭️  Skipping industry benchmark (no benchmark data)")
        return False

    # Check at least 2 years of ratios
    ratios_ok = 0
    for y in years:
        if (OUTPUT / company / f"Y{y}" / "finance" / "ratios.json").exists():
            ratios_ok += 1
    if ratios_ok < 2:
        print("    ⚠️  Need at least 2 years of ratio data")
        return False

    # Import and run
    sys.path.insert(0, str(TOOLS))
    from industry_benchmark import compute_industry_flags

    result = compute_industry_flags(company, "v1")

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(result, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    if "error" in result:
        print(f"    ⚠️  {result['error']}")
        return False

    s = result.get("summary", {})
    print(f"    Industry: {result.get('industry', '?')} (confidence: {result.get('industry_confidence', '?')})")
    print(f"    Flags: {s.get('total_flags', 0)} total ({s.get('high', 0)}H, {s.get('medium', 0)}M, {s.get('low', 0)}L)")
    if result.get("industry_mismatch_warning"):
        print(f"    ⚠️  Industry mismatch warning! Possible misclassification.")
    return True


def main():
    if len(sys.argv) < 4:
        print(__doc__)
        print("Example: python tools/run_multi_year.py 示例汽车 2022 2023 2024 --compress")
        sys.exit(1)

    company = sys.argv[1]
    years = [int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])]
    do_compress = "--compress" in sys.argv

    print(f"Multi-Year Deterministic Runner")
    print(f"  Company: {company}")
    print(f"  Years:   {years}")
    print(f"  Root:    {ROOT}")

    # Step 0: Verify inputs
    if not verify_inputs(company, years):
        print("\n❌ Missing HTML files. Check input/parsed/ directory.")
        sys.exit(1)

    # Step 1: Compress (optional)
    if do_compress:
        print(f"\n{'='*60}")
        print(f"Step 1: Compress HTML for all years")
        print(f"{'='*60}")
        for y in years:
            compress_year(company, y)

    # Step 2: Chapter detection + merge per year
    print(f"\n{'='*60}")
    print(f"Step 2: Chapter detection + tag merge per year")
    print(f"{'='*60}")
    for y in years:
        print(f"  Y{y}:")
        detect_and_merge(company, y)

    # Step 3: Finance calc per year (requires extract-finance to have run first)
    print(f"\n{'='*60}")
    print(f"Step 3: Per-year finance ratios (from existing finance.json)")
    print(f"{'='*60}")
    finance_ok = []
    for y in years:
        print(f"  Y{y}:")
        ok = run_finance_calc(company, y)
        finance_ok.append(ok)

    # Step 4: Cross-year contradiction
    print(f"\n{'='*60}")
    print(f"Step 4: Cross-year quantitative contradiction flags")
    print(f"{'='*60}")
    if any(finance_ok):
        run_contradiction_calc(company, years)
    else:
        print("  ⏭️  Skipping — no finance data available (run extract-finance agents first)")

    # Step 5: Industry benchmark comparison
    print(f"\n{'='*60}")
    print(f"Step 5: Industry peer benchmark comparison")
    print(f"{'='*60}")
    if any(finance_ok):
        run_industry_benchmark(company, years)
    else:
        print("  ⏭️  Skipping — no finance data available")

    # Summary
    print(f"\n{'='*60}")
    print(f"Deterministic steps complete. (Steps 0-5)")
    print(f"")
    print(f"Next: Run the Claude Code Workflow for LLM steps:")
    print(f"  /workflows/annual-report-pipeline-multi-year.js {company} {years[0]} {years[1]} {years[2]}")
    print(f"")
    print(f"Output directory: output/{company}/")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
