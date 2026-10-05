"""
contradiction_calc.py — Quantitative contradiction flags from 3-year finance data.

Port of 04_Contradiction_Calc.py from the bank reference prompts, stripped of
Dify-specific wrappers and exposed as a clean Python function.
"""

import json


def parse_summary(label, raw):
    """Parse a financial_summary JSON string into a dict, with error handling."""
    try:
        if not raw or raw == "{}":
            return {}
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}


def safe_get(d, key):
    """Get a value, treating -999.0 as None."""
    v = d.get(key, -999.0)
    if v == -999.0:
        return None
    return v


def pct_change(old, new):
    """Percentage change from old to new. Returns None if either is None or old is 0."""
    if old is None or new is None or old == 0:
        return None
    return (new - old) / abs(old)


def calculate_flags(y1_fs="{}", y2_fs="{}", y3_fs="{}"):
    """Compute quantitative contradiction flags from 3-year finance data.

    Input: Three JSON strings, each containing finance_calc.py output:
           {"revenue": float, "cogs": float, "gross_margin_pct": float,
            "dso_days": float, "dio_days": float, "dpo_days": float,
            "ccc_days": float, "is_negative_wc": bool}
           Missing values use -999.0 sentinel.

    Returns: {"contradiction_flags": list[dict], "overall_score": str,
              "summary_counts": str, "status": str}
    """
    y1 = parse_summary("Y1", y1_fs)
    y2 = parse_summary("Y2", y2_fs)
    y3 = parse_summary("Y3", y3_fs)

    years = [("Y1", y1), ("Y2", y2), ("Y3", y3)]
    valid = [(label, d) for label, d in years if safe_get(d, "revenue") is not None]

    flags = []

    # ── Rule 1: Revenue vs. Gross Margin direction ──
    for i in range(1, len(valid)):
        prev_label, prev = valid[i - 1]
        curr_label, curr = valid[i]

        rev_old = safe_get(prev, "revenue")
        rev_new = safe_get(curr, "revenue")
        gm_old = safe_get(prev, "gross_margin_pct")
        gm_new = safe_get(curr, "gross_margin_pct")

        if rev_old and rev_new and gm_old is not None and gm_new is not None:
            rev_chg = pct_change(rev_old, rev_new)
            gm_chg = gm_new - gm_old
            if rev_chg is not None and rev_chg > 0.05 and gm_chg < -2.0:
                flags.append({
                    "dimension": "Revenue vs. Gross Margin",
                    "period": f"{prev_label} -> {curr_label}",
                    "finding": f"Revenue +{rev_chg*100:.1f}% but gross margin {gm_chg:+.1f}pp",
                    "severity": "Medium",
                    "signal": "Revenue growth at the cost of margin — possible price competition or input cost pressure",
                    "lending_implication": "Verify revenue quality and pricing power sustainability before extending working capital lines"
                })

    # ── Rule 2: DSO deterioration ──
    for i in range(1, len(valid)):
        prev_label, prev = valid[i - 1]
        curr_label, curr = valid[i]
        dso_old = safe_get(prev, "dso_days")
        dso_new = safe_get(curr, "dso_days")
        if dso_old and dso_new:
            chg = pct_change(dso_old, dso_new)
            if chg is not None and chg > 0.20:
                flags.append({
                    "dimension": "DSO Trend",
                    "period": f"{prev_label} -> {curr_label}",
                    "finding": f"DSO +{chg*100:.0f}% ({dso_old:.0f}d -> {dso_new:.0f}d)",
                    "severity": "High",
                    "signal": "Receivables collection slowing materially — possible channel stuffing or customer distress",
                    "lending_implication": "AR Purchase / Distributor Finance opportunity, but verify buyer credit quality first"
                })

    # ── Rule 3: DIO deterioration ──
    for i in range(1, len(valid)):
        prev_label, prev = valid[i - 1]
        curr_label, curr = valid[i]
        dio_old = safe_get(prev, "dio_days")
        dio_new = safe_get(curr, "dio_days")
        if dio_old and dio_new:
            chg = pct_change(dio_old, dio_new)
            if chg is not None and chg > 0.50:
                flags.append({
                    "dimension": "DIO Trend",
                    "period": f"{prev_label} -> {curr_label}",
                    "finding": f"DIO +{chg*100:.0f}% ({dio_old:.0f}d -> {dio_new:.0f}d)",
                    "severity": "Medium",
                    "signal": "Inventory build-up significantly outpacing demand — possible obsolescence risk",
                    "lending_implication": "Caution on inventory-backed lending; verify inventory composition and turnover by product line"
                })

    # ── Rule 4: DPO compression ──
    for i in range(1, len(valid)):
        prev_label, prev = valid[i - 1]
        curr_label, curr = valid[i]
        dpo_old = safe_get(prev, "dpo_days")
        dpo_new = safe_get(curr, "dpo_days")
        if dpo_old and dpo_new:
            chg = pct_change(dpo_old, dpo_new)
            if chg is not None and chg < -0.20:
                flags.append({
                    "dimension": "DPO Trend",
                    "period": f"{prev_label} -> {curr_label}",
                    "finding": f"DPO {chg*100:.0f}% ({dpo_old:.0f}d -> {dpo_new:.0f}d) — payables being compressed",
                    "severity": "Medium",
                    "signal": "Suppliers tightening credit terms or company losing bargaining power — possible liquidity strain",
                    "lending_implication": "Supplier Finance / FSCM opportunity to ease payables pressure and stabilize supply chain"
                })

    # ── Rule 5: CCC trend ──
    for i in range(1, len(valid)):
        prev_label, prev = valid[i - 1]
        curr_label, curr = valid[i]
        ccc_old = safe_get(prev, "ccc_days")
        ccc_new = safe_get(curr, "ccc_days")
        if ccc_old and ccc_new:
            chg = pct_change(ccc_old, ccc_new)
            if chg is not None and chg > 0.30:
                flags.append({
                    "dimension": "CCC Trend",
                    "period": f"{prev_label} -> {curr_label}",
                    "finding": f"CCC +{chg*100:.0f}% ({ccc_old:.0f}d -> {ccc_new:.0f}d)",
                    "severity": "High",
                    "signal": "Working capital cycle lengthening materially — cash trapped in operations",
                    "lending_implication": "Working capital financing demand likely increasing; structure with tenor matching the CCC cycle"
                })

    # ── Rule 6: Revenue direction reversal ──
    if len(valid) >= 2:
        revs = [safe_get(d, "revenue") for _, d in valid]
        revs = [r for r in revs if r is not None]
        if len(revs) >= 2:
            growing = all(revs[i] > revs[i-1] for i in range(1, len(revs)))
            if not growing and len(revs) >= 2:
                latest_growth = pct_change(revs[-2], revs[-1])
                if latest_growth is not None and latest_growth < -0.05:
                    flags.append({
                        "dimension": "Revenue Contraction",
                        "period": f"{valid[-2][0]} -> {valid[-1][0]}",
                        "finding": f"Revenue declined {latest_growth*100:.1f}% YoY",
                        "severity": "High",
                        "signal": "Revenue contraction in most recent year — verify if cyclical or structural",
                        "lending_implication": "Reassess credit capacity; consider covenant-light structures if contraction is temporary"
                    })

    # ── Rule 7: Negative WC sustainability ──
    for label, d in valid:
        is_neg = d.get("is_negative_wc", False)
        dpo = safe_get(d, "dpo_days")
        dso = safe_get(d, "dso_days")
        if is_neg and dpo is not None and dso is not None and dpo < dso * 1.5:
            flags.append({
                "dimension": "Negative WC Sustainability",
                "period": label,
                "finding": f"Negative WC flagged but DPO ({dpo:.0f}d) is less than 1.5x DSO ({dso:.0f}d)",
                "severity": "Low",
                "signal": "Negative working capital position may be narrow — monitor for reversal risk",
                "lending_implication": "Monitor working capital closely; a reversal could create sudden financing demand"
            })

    # ── Rule 8: Data gap / disclosure change ──
    metric_keys = ["revenue", "gross_margin_pct", "dso_days", "dio_days", "dpo_days", "ccc_days"]
    for key in metric_keys:
        presence = [1 if safe_get(d, key) is not None else 0 for _, d in years]
        if sum(presence) == 2 and presence.count(1) == 2:
            missing_year = years[presence.index(0)][0]
            flags.append({
                "dimension": "Data Gap",
                "period": missing_year,
                "finding": f"'{key}' available in 2 of 3 years — missing in {missing_year}",
                "severity": "Low",
                "signal": "Possible disclosure change or reporting gap — not necessarily an error",
                "lending_implication": "Flag for manual review; may indicate restated financials or change in reporting scope"
            })

    # ── Rule 9 (A2): Revenue Quality — AR growth vs Revenue growth ──
    for i in range(1, len(valid)):
        prev_label, prev = valid[i - 1]
        curr_label, curr = valid[i]

        rev_old = safe_get(prev, "revenue")
        rev_new = safe_get(curr, "revenue")
        ar_old = safe_get(prev, "ar_end")
        ar_new = safe_get(curr, "ar_end")

        if all([rev_old, rev_new, ar_old, ar_new]):
            rev_growth = pct_change(rev_old, rev_new)
            ar_growth = pct_change(ar_old, ar_new)
            if rev_growth is not None and ar_growth is not None:
                ratio = ar_growth / rev_growth if rev_growth > 0.03 else float('inf')
                if rev_growth > 0.05 and ratio > 1.5:
                    flags.append({
                        "dimension": "Revenue Quality (A2)",
                        "period": f"{prev_label} -> {curr_label}",
                        "finding": f"AR +{ar_growth*100:.1f}% vs Revenue +{rev_growth*100:.1f}% — AR growing {ratio:.1f}x faster",
                        "severity": "High",
                        "signal": "Revenue quality deterioration: receivables growing far faster than revenue. Possible channel stuffing, looser credit terms, or customer distress",
                        "lending_implication": "Red flag for AR Purchase / Distributor Finance. Verify underlying customer payment behavior before extending receivables-backed facilities"
                    })
                elif rev_growth > 0.05 and ratio > 1.0:
                    flags.append({
                        "dimension": "Revenue Quality (A2)",
                        "period": f"{prev_label} -> {curr_label}",
                        "finding": f"AR +{ar_growth*100:.1f}% vs Revenue +{rev_growth*100:.1f}% — AR growing {ratio:.1f}x faster",
                        "severity": "Medium",
                        "signal": "AR growth outpacing revenue — monitor collection period trend",
                        "lending_implication": "Monitor AR aging before increasing receivables financing limits"
                    })

    # ── Rule 10 (A5): Inventory-GM Divergence ──
    for i in range(1, len(valid)):
        prev_label, prev = valid[i - 1]
        curr_label, curr = valid[i]

        dio_old = safe_get(prev, "dio_days")
        dio_new = safe_get(curr, "dio_days")
        gm_old = safe_get(prev, "gross_margin_pct")
        gm_new = safe_get(curr, "gross_margin_pct")

        if all([dio_old, dio_new, gm_old is not None, gm_new is not None]):
            dio_chg = pct_change(dio_old, dio_new)
            gm_chg = gm_new - gm_old
            # DIO up AND GM down simultaneously = inventory impairment risk
            if dio_chg is not None and dio_chg > 0.30 and gm_chg < -2.0:
                flags.append({
                    "dimension": "Inventory Health (A5)",
                    "period": f"{prev_label} -> {curr_label}",
                    "finding": f"DIO +{dio_chg*100:.0f}% ({dio_old:.0f}d→{dio_new:.0f}d) while GM {gm_chg:+.1f}pp → inventory may be impaired",
                    "severity": "High",
                    "signal": "Inventory building up while margins compressing — classic pre-impairment pattern. Goods may be unsellable at book value",
                    "lending_implication": "Caution on inventory-backed lending. Request inventory aging + composition breakdown. Consider lower advance rate"
                })
            elif dio_chg is not None and dio_chg > 0.20 and gm_chg < 0:
                flags.append({
                    "dimension": "Inventory Health (A5)",
                    "period": f"{prev_label} -> {curr_label}",
                    "finding": f"DIO +{dio_chg*100:.0f}% with GM {gm_chg:+.1f}pp — watch for potential impairment",
                    "severity": "Medium",
                    "signal": "Margin pressure combined with rising inventory days — monitor for impairment indicators",
                    "lending_implication": "Inventory financing: review obsolescence provisions before setting advance rates"
                })

    # ── Rule 11 (A4): DPO-Revenue Relationship ──
    for i in range(1, len(valid)):
        prev_label, prev = valid[i - 1]
        curr_label, curr = valid[i]

        dpo_old = safe_get(prev, "dpo_days")
        dpo_new = safe_get(curr, "dpo_days")
        rev_old = safe_get(prev, "revenue")
        rev_new = safe_get(curr, "revenue")

        if all([dpo_old, dpo_new, rev_old, rev_new]):
            dpo_chg = pct_change(dpo_old, dpo_new)
            rev_chg = pct_change(rev_old, rev_new)
            # DPO stretching while revenue declining = suppliers tightening
            if dpo_chg is not None and rev_chg is not None:
                if dpo_chg > 0.15 and rev_chg < -0.05:
                    flags.append({
                        "dimension": "Supplier Financing Pressure (A4)",
                        "period": f"{prev_label} -> {curr_label}",
                        "finding": f"DPO +{dpo_chg*100:.0f}% ({dpo_old:.0f}d→{dpo_new:.0f}d) while Revenue {rev_chg*100:.1f}% — stretched payables despite shrinking business",
                        "severity": "High",
                        "signal": "DPO lengthening while revenue declining = suppliers likely tightening terms or company delaying payments under cash pressure",
                        "lending_implication": "Supplier Finance / FSCM opportunity but assess whether DPO stretch is voluntary (bargaining power) or involuntary (liquidity stress)"
                    })
                elif dpo_chg > 0.15 and rev_chg > 0.10:
                    flags.append({
                        "dimension": "Supplier Financing Leverage (A4)",
                        "period": f"{prev_label} -> {curr_label}",
                        "finding": f"DPO +{dpo_chg*100:.0f}% alongside Revenue +{rev_chg*100:.1f}% — likely supplier bargaining power improvement",
                        "severity": "Low",
                        "signal": "DPO stretching with revenue growth → likely negotiating better supplier terms, not distress",
                        "lending_implication": "Working capital efficiency improving. If sustainable, lower financing need"
                    })

    # ── Rule 12 (A1): CCC Composition Decomposition ──
    # Identify which component drives CCC change
    if len(valid) >= 2:
        first_label, first = valid[0]
        last_label, last = valid[-1]

        dso_first = safe_get(first, "dso_days")
        dso_last = safe_get(last, "dso_days")
        dio_first = safe_get(first, "dio_days")
        dio_last = safe_get(last, "dio_days")
        dpo_first = safe_get(first, "dpo_days")
        dpo_last = safe_get(last, "dpo_days")
        ccc_first = safe_get(first, "ccc_days")
        ccc_last = safe_get(last, "ccc_days")

        if all([dso_first, dso_last, dio_first, dio_last, dpo_first, dpo_last, ccc_first, ccc_last]):
            ccc_change = ccc_last - ccc_first
            dso_contrib = dso_last - dso_first
            dio_contrib = dio_last - dio_first
            dpo_contrib = -(dpo_last - dpo_first)  # DPO increase reduces CCC

            if abs(ccc_change) > 10:  # Only flag if CCC moved meaningfully
                # Find the dominant contributor
                contributors = [
                    ("DSO", dso_contrib),
                    ("DIO", dio_contrib),
                    ("DPO", dpo_contrib),
                ]
                contributors.sort(key=lambda x: abs(x[1]), reverse=True)
                primary = contributors[0]

                flags.append({
                    "dimension": "CCC Composition (A1)",
                    "period": f"{first_label} → {last_label}",
                    "finding": (
                        f"CCC {ccc_change:+.0f}d ({ccc_first:.0f}→{ccc_last:.0f}d). "
                        f"Primary driver: {primary[0]} ({primary[1]:+.0f}d contribution). "
                        f"Breakdown: DSO {dso_contrib:+.0f}d, DIO {dio_contrib:+.0f}d, DPO {dpo_contrib:+.0f}d"
                    ),
                    "severity": "High" if abs(ccc_change) > 40 else "Medium",
                    "signal": (
                        f"CCC {'deterioration' if ccc_change > 0 else 'improvement'} driven primarily by {primary[0]}. "
                        f"{'DSO-driven = collections problem. Check buyer credit quality.' if primary[0] == 'DSO' and dso_contrib > 0 else ''}"
                        f"{'DIO-driven = inventory build-up. Check for obsolescence.' if primary[0] == 'DIO' and dio_contrib > 0 else ''}"
                        f"{'DPO-driven compression = suppliers reducing credit. Check for liquidity stress.' if primary[0] == 'DPO' and dpo_contrib > 0 else ''}"
                    ),
                    "lending_implication": (
                        f"Structure financing to address the specific CCC driver: "
                        f"{'AR Purchase / Distributor Finance' if primary[0] == 'DSO' and dso_contrib > 0 else ''}"
                        f"{'Inventory finance with conservative advance rate' if primary[0] == 'DIO' and dio_contrib > 0 else ''}"
                        f"{'Supplier Finance / FSCM for payables pressure' if primary[0] == 'DPO' and dpo_contrib > 0 else ''}"
                    )
                })

    # ── Summary scoring ──
    severity_order = {"High": 3, "Medium": 2, "Low": 1}
    red_count = sum(1 for f in flags if f["severity"] == "High")
    amber_count = sum(1 for f in flags if f["severity"] == "Medium")
    green_count = sum(1 for f in flags if f["severity"] == "Low")

    if red_count > 0:
        overall = "CAUTION"
    elif amber_count > 1:
        overall = "WATCH"
    else:
        overall = "CLEAN"

    return {
        "contradiction_flags": json.dumps(flags, ensure_ascii=False),
        "overall_score": overall,
        "summary_counts": f"Red: {red_count}, Amber: {amber_count}, Green: {green_count}",
        "status": "success"
    }


if __name__ == "__main__":
    # ── Test: 3 sample years ──

    # Y1: strong base year
    y1 = json.dumps({
        "revenue": 1000.0,
        "cogs": 700.0,
        "gross_margin_pct": 30.0,
        "dso_days": 40.0,
        "dio_days": 60.0,
        "dpo_days": 50.0,
        "ccc_days": 65.0,
        "is_negative_wc": False,
        "ar_start": 100.0,
        "ar_end": 110.0,
        "ap_start": 85.0,
        "ap_end": 95.0,
        "inv_start": 105.0,
        "inv_end": 115.0
    })

    # Y2: revenue up, but margin eroding and DSO/CCC deteriorating
    y2 = json.dumps({
        "revenue": 1100.0,
        "cogs": 800.0,
        "gross_margin_pct": 27.3,
        "dso_days": 50.0,
        "dio_days": 75.0,
        "dpo_days": 35.0,
        "ccc_days": 95.0,
        "is_negative_wc": False,
        "ar_start": 110.0,
        "ar_end": 180.0,
        "ap_start": 70.0,
        "ap_end": 77.0,
        "inv_start": 140.0,
        "inv_end": 165.0
    })

    # Y3: revenue declines, margins compress further, WC worsens
    y3 = json.dumps({
        "revenue": 1000.0,
        "cogs": 750.0,
        "gross_margin_pct": 25.0,
        "dso_days": 62.0,
        "dio_days": 120.0,
        "dpo_days": 25.0,
        "ccc_days": 157.0,
        "is_negative_wc": False,
        "ar_start": 180.0,
        "ar_end": 250.0,
        "ap_start": 45.0,
        "ap_end": 52.0,
        "inv_start": 200.0,
        "inv_end": 250.0
    })

    result = calculate_flags(y1, y2, y3)
    flags = json.loads(result["contradiction_flags"])

    print(f"Overall: {result['overall_score']}")
    print(f"Counts:  {result['summary_counts']}")
    print(f"Status:  {result['status']}")
    print(f"Flags triggered: {len(flags)}")
    print()

    for f in flags:
        print(f"  [{f['severity']:>6}] {f['dimension']} ({f['period']})")
        print(f"          {f['finding']}")

    # Assertions to catch regressions
    assert result["status"] == "success"
    assert result["overall_score"] == "CAUTION"  # at least one High flag
    assert len(flags) > 0

    flag_dims = {f["dimension"] for f in flags}
    assert "Revenue vs. Gross Margin" in flag_dims
    assert "DSO Trend" in flag_dims
    assert "DIO Trend" in flag_dims
    assert "DPO Trend" in flag_dims
    assert "CCC Trend" in flag_dims
    assert "Revenue Contraction" in flag_dims
    # New 13-dimension rules
    assert "Revenue Quality (A2)" in flag_dims, "A2: Revenue Quality should fire (AR 6.4x faster than Revenue)"
    assert "Inventory Health (A5)" in flag_dims, "A5: Inventory-GM divergence should fire"
    assert "CCC Composition (A1)" in flag_dims, "A1: CCC decomposition should fire"
    # A4 should NOT fire on test data — DPO is compressing (Rule 4 catches it),
    # DPO is not stretching with revenue decline (the A4 trigger condition)
    a4_flags = [f for f in flags if f["dimension"] == "Supplier Financing Pressure (A4)"]
    a4_low = [f for f in flags if f["dimension"] == "Supplier Financing Leverage (A4)"]
    assert len(a4_flags) == 0, f"A4 Pressure should not fire on test data (DPO compressing, not stretching)"
    assert len(a4_low) == 0, f"A4 Leverage should not fire on test data"

    print()
    print(f"All assertions passed ({len(flags)} flags across {len(flag_dims)} dimensions).")
