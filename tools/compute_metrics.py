"""Compute ratios + cross-year flags for a specific company/version."""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from finance_calc import calculate_ratios
from contradiction_calc import calculate_flags

company = sys.argv[1] if len(sys.argv) > 1 else "DemoMotor"
version = sys.argv[2] if len(sys.argv) > 2 else "v1"

BASE = Path(f"output/{company}/{version}")

print(f"Company: {company}  Version: {version}")
print(f"Base:    {BASE}")

# Auto-detect available years by scanning Y* directories
years = sorted([int(d.name[1:]) for d in BASE.iterdir() if d.is_dir() and d.name.startswith('Y')])
if not years:
    print("ERROR: No Y* directories found. Run text extraction first.")
    sys.exit(1)
print(f"Detected years: {years}")

for year in years:
    fp = BASE / f"Y{year}" / "finance" / "finance.json"
    data = json.loads(fp.read_text(encoding="utf-8"))
    ratios = calculate_ratios(data)
    for k in ["ar_start", "ar_end", "inv_start", "inv_end", "ap_start", "ap_end"]:
        if k in data:
            v = data[k]
            ratios[k] = v["value"] if isinstance(v, dict) else v
    rp = BASE / f"Y{year}" / "finance" / "ratios.json"
    rp.write_text(json.dumps(ratios, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Y{year}: DSO={ratios['dso_days']:.1f}d  DPO={ratios['dpo_days']:.1f}d  CCC={ratios['ccc_days']:.1f}d  GM={ratios['gross_margin_pct']:.1f}%")

y1 = (BASE / f"Y{years[0]}" / "finance" / "ratios.json").read_text(encoding="utf-8")
y2 = (BASE / f"Y{years[1]}" / "finance" / "ratios.json").read_text(encoding="utf-8")
y3 = (BASE / f"Y{years[2]}" / "finance" / "ratios.json").read_text(encoding="utf-8")

result = calculate_flags(y1, y2, y3)
(BASE / "cross_year").mkdir(parents=True, exist_ok=True)
(BASE / "cross_year" / "quant_flags.json").write_text(
    json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
)

flags = json.loads(result["contradiction_flags"])
print(f"\nCross-year: {result['overall_score']} | {result['summary_counts']} | {len(flags)} flags")
for f in flags:
    print(f"  [{f['severity']:>6}] {f['dimension']} ({f['period']}): {f['finding'][:120]}")
