"""One-shot: compute ratios for all 3 years + cross-year contradiction flags."""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from finance_calc import calculate_ratios
from contradiction_calc import calculate_flags

import sys
if len(sys.argv) > 1:
    OUTPUT = Path(__file__).resolve().parent.parent / "output" / sys.argv[1]
else:
    OUTPUT = Path(__file__).resolve().parent.parent / "output" / "示例汽车"  # legacy default

for year in [2022, 2023, 2024]:
    fp = OUTPUT / f"Y{year}" / "finance" / "finance.json"
    data = json.loads(fp.read_text(encoding='utf-8'))
    ratios = calculate_ratios(data)
    # Merge raw values needed for A2/A4/A5 rules
    for k in ['ar_start', 'ar_end', 'inv_start', 'inv_end', 'ap_start', 'ap_end']:
        if k in data:
            ratios[k] = data[k]
    rp = OUTPUT / f"Y{year}" / "finance" / "ratios.json"
    rp.write_text(json.dumps(ratios, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f"Y{year}: DSO={ratios['dso_days']:.1f}d  DPO={ratios['dpo_days']:.1f}d  CCC={ratios['ccc_days']:.1f}d  GM={ratios['gross_margin_pct']:.1f}%")

# Cross-year
y1 = (OUTPUT / "Y2022" / "finance" / "ratios.json").read_text(encoding='utf-8')
y2 = (OUTPUT / "Y2023" / "finance" / "ratios.json").read_text(encoding='utf-8')
y3 = (OUTPUT / "Y2024" / "finance" / "ratios.json").read_text(encoding='utf-8')

result = calculate_flags(y1, y2, y3)
cross_dir = OUTPUT / "cross_year"
cross_dir.mkdir(parents=True, exist_ok=True)
(cross_dir / "quant_flags.json").write_text(
    json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')

flags = json.loads(result['contradiction_flags'])
print(f"\nCross-year: {result['overall_score']} | {result['summary_counts']} | {len(flags)} flags")
for f in flags:
    print(f"  [{f['severity']:>6}] {f['dimension']} ({f['period']})")
    print(f"          {f['finding'][:120]}")
