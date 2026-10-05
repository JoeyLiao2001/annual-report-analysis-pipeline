"""the bank Report Renderer — transforms synthesis/report.json → styled HTML.

Usage:
    python tools/render_report.py <output_dir>
    python tools/render_report.py output/示例汽车

Reads: {output_dir}/synthesis/report.json
Writes: {output_dir}/synthesis/report.html
"""

import json
import sys
import re
from pathlib import Path
from datetime import datetime


# ── CSS Templates ──────────────────────────────────────────────────────────────

CSS_LEGACY = """      /* === Reset & Base === */
      *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

      body {
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, "Noto Sans", sans-serif;
        font-size: 11pt;
        line-height: 1.7;
        color: #1a1a1a;
        max-width: 210mm; /* A4 width */
        margin: 0 auto;
        padding: 20mm 15mm 25mm 15mm;
        background: #fff;
      }

      /* === Headings === */
      h1 {
        font-size: 16pt;
        font-weight: 700;
        color: #1F4E79;
        border-bottom: 2px solid #1F4E79;
        padding-bottom: 6px;
        margin: 28px 0 14px 0;
        page-break-after: avoid;
      }

      h2 {
        font-size: 13pt;
        font-weight: 700;
        color: #1F4E79;
        margin: 22px 0 10px 0;
        page-break-after: avoid;
      }

      h3 {
        font-size: 11.5pt;
        font-weight: 600;
        color: #1a1a1a;
        margin: 16px 0 8px 0;
        page-break-after: avoid;
      }

      h4 {
        font-size: 11pt;
        font-weight: 600;
        color: #444;
        margin: 12px 0 6px 0;
      }

      /* === Paragraphs === */
      p {
        margin: 8px 0;
        text-align: justify;
      }

      /* === Bold / Highlights (key numbers in the bank blue) === */
      strong {
        color: #1F4E79;
        font-weight: 600;
      }

      /* === Horizontal Rules === */
      hr {
        border: none;
        border-top: 1px solid #ddd;
        margin: 24px 0;
      }

      /* === Tables === */
      table {
        width: 100%;
        border-collapse: collapse;
        margin: 14px 0;
        font-size: 10pt;
        page-break-inside: avoid;
      }

      thead th {
        background: #1F4E79;
        color: #fff;
        font-weight: 600;
        text-align: left;
        padding: 8px 10px;
        font-size: 9.5pt;
        letter-spacing: 0.3px;
      }

      tbody td {
        padding: 7px 10px;
        border-bottom: 1px solid #e0e0e0;
        vertical-align: top;
      }

      tbody tr:nth-child(even) td {
        background: #f7f9fb;
      }

      tbody tr:hover td {
        background: #e8f0f8;
      }

      /* === Lists === */
      ul, ol {
        margin: 8px 0 8px 20px;
      }

      li {
        margin: 3px 0;
      }

      /* === Print === */
      @media print {
        body {
          padding: 12mm 10mm 15mm 10mm;
          font-size: 10pt;
          color: #000;
        }

        h1 { font-size: 14pt; page-break-before: avoid; }
        h2 { font-size: 12pt; }
        h3 { font-size: 10.5pt; }
        thead th { background: #1F4E79 !important; color: #fff !important; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
        tbody tr:nth-child(even) td { background: #f7f7f7 !important; -webkit-print-color-adjust: exact; print-color-adjust: exact; }

        @page {
          size: A4;
          margin: 15mm;
        }
      }"""

CSS_ADDITIONS = """
      /* === Footnotes === */
      .footnotes { font-size: 9pt; color: #555; margin-top: 30px; border-top: 1px solid #ccc; padding-top: 12px; }
      .footnote-ref { color: #1F4E79; font-weight: bold; font-size: 0.85em; vertical-align: super; }
      .footnote-item { margin: 4px 0; }
      .footnote-label { color: #1F4E79; font-weight: 600; }

      /* === Risk Boundary Indicators === */
      .risk-clear { color: #2e7d32; font-weight: 600; }
      .risk-flag { color: #c62828; font-weight: 700; }
      .risk-monitor { color: #e67e22; font-weight: 600; }

      /* === Product Tier Badges === */
      .badge { display: inline-block; padding: 2px 8px; border-radius: 3px; font-size: 8pt; font-weight: 700; color: #fff; margin-right: 4px; }
      .badge-immediate { background: #c62828; }
      .badge-nearterm { background: #e67e22; }
      .badge-developmental { background: #1565c0; }

      /* === Entity Markers === */
      .entity-indirect { color: #888; font-style: italic; font-size: 0.9em; }
      .tag-sg-priority { background: #c62828; color: #fff; padding: 1px 6px; border-radius: 2px; font-size: 8pt; font-weight: 700; }
      .tag-sea { background: #1565c0; color: #fff; padding: 1px 6px; border-radius: 2px; font-size: 8pt; font-weight: 700; }

      /* === Severity Badges === */
      .severity-high { color: #c62828; font-weight: 700; }
      .severity-medium { color: #e67e22; font-weight: 600; }
      .severity-low { color: #1565c0; font-weight: 600; }

      /* === Data Citations === */
      .source-cite { color: #888; font-size: 0.85em; font-style: italic; }

      /* === Page Citations === */
      .page-cite { color: #1F4E79; font-weight: 600; font-size: 0.9em; white-space: nowrap; }

      /* === Callout Box === */
      .callout { background: #f0f4f8; border-left: 4px solid #1F4E79; padding: 12px 16px; margin: 14px 0; font-size: 10pt; }
      .callout-title { font-weight: 700; color: #1F4E79; margin-bottom: 4px; }

      /* === Contradiction Card === */
      .contradiction-card { border: 1px solid #ddd; border-left: 4px solid #e67e22; padding: 12px 14px; margin: 10px 0; background: #fafafa; }
      .contradiction-card .card-header { font-weight: 700; margin-bottom: 6px; }
      .contradiction-card .card-body { font-size: 10pt; }
      .contradiction-card .card-body p { margin: 4px 0; }

      /* === Pain Point Block (Section 1 commercial opportunities) === */
      .pain-point-block { border: 1px solid #ddd; border-left: 4px solid #1F4E79; padding: 12px 14px; margin: 10px 0; background: #fafafa; }
      .pain-point-block .pp-header { font-weight: 700; color: #1F4E79; margin-bottom: 6px; font-size: 10.5pt; }
      .pain-point-block .pp-body { font-size: 10pt; }
      .pain-point-block .pp-body p { margin: 4px 0; }

      /* === Risk Rating === */
      .risk-rating-box { display: inline-block; padding: 4px 14px; border-radius: 4px; font-size: 13pt; font-weight: 700; color: #fff; margin: 8px 0; }
      .risk-rating-moderate-low { background: #2e7d32; }
      .risk-rating-moderate { background: #e67e22; }
      .risk-rating-high { background: #c62828; }
      .risk-rating-low { background: #1565c0; }"""

STANDARD_FOOTNOTES = [
    ("AP definition", "Accounts Payable (AP) defined as Trade Payables only (应付账款). Notes Payable excluded. Source: Consolidated Balance Sheet, Current Liabilities section."),
    ("DSO caveat", "DSO below 20 days may reflect Auto Finance JV off-balance-sheet effect — dealer receivables factored through GWM's 98.18%-owned Automotive Finance subsidiary (RMB 53.76B total assets) may shift AR off the manufacturer's balance sheet. Credit officers should verify AR composition."),
    ("Entity ownership", "Ownership marked as 'Not disclosed' means the percentage was not stated in the source annual report. Indirect entities identified via parent guarantee structures in the notes to the financial statements."),
    ("Product names", "All the bank product names verified against the bank Wholesale Banking Product Mapping Table (The bank Framework v2.4 reference)."),
]


# ── Helpers ────────────────────────────────────────────────────────────────────

CIRCLED = ["①", "②", "③", "④", "⑤", "⑥", "⑦", "⑧", "⑨", "⑩",
           "⑪", "⑫", "⑬", "⑭", "⑮", "⑯", "⑰", "⑱", "⑲", "⑳"]

_footnote_counter = 0
_footnote_used = {}  # label → str index


def _need_footnote(label: str) -> str:
    """Register a footnote usage; return the circled-number reference string."""
    global _footnote_counter, _footnote_used
    if label not in _footnote_used:
        if _footnote_counter >= len(CIRCLED):
            raise RuntimeError("Too many footnotes — increase CIRCLED list")
        _footnote_used[label] = CIRCLED[_footnote_counter]
        _footnote_counter += 1
    return _footnote_used[label]


def _maybe_footnote(label: str, text: str) -> str:
    """If text looks numeric (contains a digit), append the footnote ref."""
    if re.search(r'\d', str(text)):
        ref = _need_footnote(label)
        return f'{text} <span class="footnote-ref">{ref}</span>'
    return text


def _esc(s: str) -> str:
    """Minimal XML escaping."""
    if s is None:
        return ""
    s = str(s)
    s = s.replace("&", "&amp;")
    s = s.replace("<", "&lt;")
    s = s.replace(">", "&gt;")
    return s


def _cite_pages(s: str) -> str:
    """Wrap page references (p.47, pp.52-53) in .page-cite spans."""
    # pp.52-53 (range) — match before p. to avoid partial matches
    s = re.sub(r'\bpp\.(\d+)[–-](\d+)\b', r'<span class="page-cite">pp.\1-\2</span>', s)
    # p.47 (single page)
    s = re.sub(r'\bp\.(\d+)\b', r'<span class="page-cite">p.\1</span>', s)
    return s


def _badge(priority: str) -> str:
    """Map a priority string to a badge span."""
    p = priority.lower()
    if "immediate" in p:
        return '<span class="badge badge-immediate">IMMEDIATE</span>'
    if "near" in p:
        return '<span class="badge badge-nearterm">NEAR-TERM</span>'
    if "development" in p:
        return '<span class="badge badge-developmental">DEVELOPMENTAL</span>'
    return f'<span class="badge">{_esc(priority)}</span>'


def _severity_class(sev: str) -> str:
    s = str(sev).lower()
    if s == "high":
        return "severity-high"
    if s == "medium":
        return "severity-medium"
    return "severity-low"


def _risk_status_cell(status: str) -> str:
    """Render a risk-boundary status cell with coloured class."""
    s = str(status).upper()
    if "CLEAR" in s:
        cls = "risk-clear"
        symbol = "&#10003; CLEAR"
    elif "FLAG" in s or "VIOLAT" in s:
        cls = "risk-flag"
        symbol = "&#10007; FLAG"
    else:
        cls = "risk-monitor"
        symbol = "&#9888; MONITOR"
    return f'<span class="{cls}">{symbol}</span>'


def _mk_table(headers: list, rows: list) -> str:
    """Build an HTML table from headers and a list-of-lists rows."""
    thead = "".join(f"<th>{_esc(h)}</th>" for h in headers)
    tbody = ""
    for row in rows:
        cells = "".join(f"<td>{c if isinstance(c, str) and '<' in c else _esc(str(c))}</td>" for c in row)
        tbody += f"<tr>{cells}</tr>\n"
    return f"<table><thead><tr>{thead}</tr></thead><tbody>\n{tbody}</tbody></table>\n"


def _find_by_fuzzy_key(data: dict, keywords: list) -> any:
    """Find a value in *data* whose key contains all *keywords* (case-insensitive).
    Returns the first match, or None."""
    if not data or not isinstance(data, dict):
        return None
    for key in data:
        kl = key.lower()
        if all(kw.lower() in kl for kw in keywords):
            return data[key]
    return None


# ── Section Renderers ──────────────────────────────────────────────────────────

def _render_header(meta: dict) -> str:
    """Render report title block + company profile line.  No QA content."""
    company = _esc(meta.get("company", "Unknown Company"))
    year = _esc(str(meta.get("fiscal_year", "")))
    sector = _esc(meta.get("sector", ""))
    tier = _esc(meta.get("bank_signal_tier", ""))
    date_ = _esc(meta.get("report_date", ""))
    rationale = _esc(meta.get("bank_signal_rationale", ""))

    lines = []
    lines.append(f'<h1>Wholesale Banking Corporate Insight Report — {company} ({year})</h1>')

    # Meta table
    meta_rows = [
        ["Company", company],
        ["Fiscal Year", str(year)],
        ["Sector", sector],
        ["the bank Signal Tier", f"<strong>{tier}</strong> — {rationale}" if rationale else f"<strong>{tier}</strong>"],
        ["Report Date", date_],
    ]
    lines.append(_mk_table(["Field", "Detail"], meta_rows))

    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
#  Section 1: Executive Summary & Commercial Opportunities
#  Leadership-facing — pain points and ASEAN corridors pulled to the front.
# ══════════════════════════════════════════════════════════════════════════════

def _render_section1_executive(exec_data: dict, strategy_data: dict) -> str:
    """Section 1: Executive Summary & Commercial Opportunities.

    Pulls pain-point-to-product mapping and ASEAN corridor summary from
    strategy data so wholesale banking leadership sees commercial opportunities first.
    """
    if not exec_data and not strategy_data:
        return ""
    lines = ["<h1>1 &mdash; Executive Summary &amp; Commercial Opportunities</h1>"]

    # ── Company profile ──
    profile = exec_data.get("company_profile") if exec_data else None
    if profile:
        lines.append(f"<p>{_esc(profile)}</p>")

    cls_ = exec_data.get("sector_classification") if exec_data else None
    if cls_:
        lines.append(f"<p><strong>Sector Classification:</strong> {_esc(cls_)}</p>")

    relevance = exec_data.get("bank_relevance") if exec_data else None
    if relevance:
        lines.append(f"<p>{_esc(relevance)}</p>")

    # ── Key financial snapshot ──
    kfs = exec_data.get("key_financial_snapshot") if exec_data else None
    if kfs and isinstance(kfs, dict):
        lines.append("<h2>Key Financial Snapshot</h2>")
        kfs_rows = []
        for k, v in kfs.items():
            label = k.replace("_", " ").title()
            if any(w in k.lower() for w in ["revenue", "profit", "asset", "borrowing", "cash", "capital"]):
                val = _maybe_footnote("AP definition", str(v))
            else:
                val = _esc(str(v))
            kfs_rows.append([label, val])
        lines.append(_mk_table(["Metric", "Value"], kfs_rows))

    # ── Pain Points → the bank Products (pulled from strategy section) ──
    pain_points = None
    if strategy_data:
        pain_points = strategy_data.get("pain_point_to_product_mapping")
        if not pain_points:
            pain_points = _find_by_fuzzy_key(strategy_data, ["pain", "product"])

    if pain_points and isinstance(pain_points, list):
        lines.append("<h2>Commercial Opportunities &mdash; Pain Points &rarr; the bank Products</h2>")
        for pp in pain_points:
            pain = _esc(pp.get("pain_point", pp.get("pain", "")))
            product = _esc(pp.get("bank_product", pp.get("product", "")))
            fit = _esc(pp.get("fit_assessment", pp.get("fit", "")))
            restriction = _esc(pp.get("key_restriction", pp.get("restriction", "")))

            # Fit badge
            fit_upper = fit.upper()
            if "STRONG" in fit_upper:
                fit_badge = '<span class="risk-clear">STRONG FIT</span>'
            elif "MODERATE" in fit_upper:
                fit_badge = '<span class="risk-monitor">MODERATE FIT</span>'
            elif "DEVELOPMENT" in fit_upper:
                fit_badge = '<span class="severity-low">DEVELOPMENTAL FIT</span>'
            else:
                fit_badge = f'<span class="severity-low">{fit}</span>'

            lines.append("<div class='pain-point-block'>")
            lines.append(f"<div class='pp-header'>Pain Point: {pain}</div>")
            lines.append("<div class='pp-body'>")
            lines.append(f"<p><strong>the bank Product:</strong> {product}</p>")
            fit_line = f"<p><strong>Fit:</strong> {fit_badge}"
            if restriction:
                fit_line += f" <em>({restriction})</em>"
            fit_line += "</p>"
            lines.append(fit_line)
            # Rationale
            rationale = pp.get("rationale", pp.get("fit_rationale", pp.get("detail", "")))
            if rationale:
                lines.append(f"<p><strong>Rationale:</strong> {_esc(str(rationale))}</p>")
            lines.append("</div></div>")

    # ── ASEAN corridor summary (pulled from strategy section) ──
    asean_corridor = None
    if strategy_data:
        asean_corridor = strategy_data.get("asean_corridor_relevance")
        if not asean_corridor:
            asean_corridor = _find_by_fuzzy_key(strategy_data, ["asean", "corridor"])

    if asean_corridor and isinstance(asean_corridor, dict):
        lines.append("<h2>ASEAN Corridor Relevance</h2>")
        for corridor, detail in asean_corridor.items():
            if isinstance(detail, dict):
                lines.append("<div class='callout'>")
                corr_name = corridor.replace("_", " ").title()
                rel = _esc(str(detail.get("relevance", detail.get("assessment", ""))))
                lines.append(f"<div class='callout-title'>{_esc(corr_name)}: {rel}</div>")
                angle = detail.get("bank_angle", detail.get("opportunity", ""))
                if angle:
                    lines.append(f"<p>{_esc(str(angle))}</p>")
                lines.append("</div>")

    # ── Top opportunities (if present in exec_data) ──
    opps = exec_data.get("top_3_bank_opportunities") if exec_data else None
    if opps and isinstance(opps, list):
        lines.append("<h2>Top the bank Opportunities</h2>")
        for i, o in enumerate(opps, 1):
            rank = o.get("rank", i)
            opp_name = _esc(o.get("opportunity", ""))
            rationale = _esc(o.get("rationale", ""))
            wallet = _esc(str(o.get("estimated_wallet", "")))
            products = o.get("products", [])
            lines.append(f"<h3>#{rank} &mdash; {opp_name}</h3>")
            lines.append(f"<p>{rationale}</p>")
            lines.append(f"<p><strong>Estimated Wallet:</strong> {wallet}</p>")
            if products:
                prod_list = ", ".join(_esc(p) for p in products)
                lines.append(f"<p><strong>Products:</strong> {prod_list}</p>")

    # ── Risk flags summary ──
    rfs = exec_data.get("risk_flags_summary") if exec_data else None
    if rfs and isinstance(rfs, list):
        lines.append("<h2>Key Risk Flags</h2>")
        lines.append("<ul>")
        for rf in rfs:
            lines.append(f"<li>{_esc(rf)}</li>")
        lines.append("</ul>")

    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
#  Section 2: Financial Analysis
# ══════════════════════════════════════════════════════════════════════════════

def _render_section2_financial(data: dict) -> str:
    """Section 2: Financial Analysis."""
    if not data:
        return ""
    lines = ["<h1>2 &mdash; Financial Analysis</h1>"]

    # Revenue & Profitability
    rp = data.get("revenue_and_profitability")
    if rp and isinstance(rp, dict):
        lines.append("<h2>Revenue &amp; Profitability</h2>")
        narr_keys = {"trend_assessment"}
        for k, v in rp.items():
            if k in narr_keys:
                lines.append(f"<p><strong>{k.replace('_', ' ').title()}:</strong> {_esc(str(v))}</p>")
        # Build a table for the non-narrative keys
        table_rows = []
        for k, v in rp.items():
            if k not in narr_keys:
                label = k.replace("_", " ").title()
                table_rows.append([label, _esc(str(v))])
        if table_rows:
            lines.append(_mk_table(["Metric", "Value"], table_rows))

    # Working Capital Analysis
    wc = data.get("working_capital_analysis")
    if wc and isinstance(wc, dict):
        lines.append("<h2>Working Capital Analysis</h2>")
        # Key metrics table
        metric_keys = ["dso_days", "dio_days", "dpo_days", "ccc_days", "is_negative_wc"]
        wc_table = []
        for mk in metric_keys:
            v = wc.get(mk)
            if v is not None:
                label = mk.replace("_", " ").title()
                if mk == "dso_days":
                    display = _maybe_footnote("DSO caveat", str(v))
                else:
                    display = _esc(str(v))
                wc_table.append([label, display])
        if wc_table:
            lines.append(_mk_table(["Metric", "Value"], wc_table))

        # Narrative subsections
        for sub_k in ["dso_assessment", "dio_assessment", "dpo_assessment",
                       "industry_benchmark_context", "analysis"]:
            text = wc.get(sub_k)
            if text:
                label = sub_k.replace("_", " ").title()
                lines.append(f"<h3>{label}</h3>")
                lines.append(f"<p>{_esc(str(text))}</p>")

    # Key Financial Ratios
    kfr = data.get("key_financial_ratios")
    if kfr and isinstance(kfr, dict):
        lines.append("<h2>Key Financial Ratios &amp; Debt Structure</h2>")
        ratio_rows = []
        for k, v in kfr.items():
            if k == "debt_structure":
                continue  # handled separately
            label = k.replace("_", " ").replace("Pct", "(%)").title()
            ratio_rows.append([label, _esc(str(v))])
        if ratio_rows:
            lines.append(_mk_table(["Ratio / Metric", "Value"], ratio_rows))

        # Debt structure sub-table
        ds = kfr.get("debt_structure")
        if ds and isinstance(ds, dict):
            lines.append("<h3>Debt Structure</h3>")
            ds_rows = [[k.replace("_", " ").title(), _esc(str(v))] for k, v in ds.items()]
            lines.append(_mk_table(["Item", "Amount"], ds_rows))

        # FX exposure sub-table
        fx = kfr.get("foreign_exchange_exposure")
        if fx and isinstance(fx, dict):
            lines.append("<h3>Foreign Exchange Exposure</h3>")
            fx_rows = [[k.replace("_", " ").title(), _esc(str(v))] for k, v in fx.items()]
            lines.append(_mk_table(["Item", "Amount"], fx_rows))

    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
#  Section 3: Strategy & Supply Chain
#  Pain points moved to Section 1; ASEAN corridor DETAIL stays here.
# ══════════════════════════════════════════════════════════════════════════════

def _render_section3_strategy(data: dict) -> str:
    """Section 3: Strategy &amp; Supply Chain.

    Contains core business drivers, supply chain transformation, forward
    outlook / risks, and detailed ASEAN corridor analysis (the full
    corridor-by-corridor detail, complementing the summary in Section 1).
    Pain-point-to-product mapping has been moved to Section 1.
    """
    if not data:
        return ""
    lines = ["<h1>3 &mdash; Strategy &amp; Supply Chain</h1>"]

    # Core business drivers
    cbd = data.get("core_business_drivers")
    if cbd and isinstance(cbd, dict):
        for k, v in cbd.items():
            label = k.replace("_", " ").title()
            lines.append(f"<h2>{label}</h2>")
            if isinstance(v, list):
                lines.append("<ul>")
                for item in v:
                    lines.append(f"<li>{_esc(str(item))}</li>")
                lines.append("</ul>")
            else:
                lines.append(f"<p>{_esc(str(v))}</p>")

    # Supply chain & ASEAN footprint
    sc = data.get("supply_chain_and_asean_footprint")
    if sc and isinstance(sc, dict):
        lines.append("<h2>Supply Chain &amp; ASEAN Footprint</h2>")

        for k, v in sc.items():
            if k == "asean_operations":
                continue  # handled nested
            label = k.replace("_", " ").title()
            lines.append(f"<p><strong>{label}:</strong> {_esc(str(v))}</p>")

        asean_ops = sc.get("asean_operations")
        if asean_ops and isinstance(asean_ops, dict):
            lines.append("<h3>ASEAN Operations</h3>")
            lines.append("<ul>")
            for country, detail in asean_ops.items():
                lines.append(f"<li><strong>{_esc(country.title())}:</strong> {_esc(str(detail))}</li>")
            lines.append("</ul>")

    # NOTE: pain_point_to_product_mapping is intentionally NOT rendered here.
    # It has been moved to Section 1 (Executive Summary & Commercial Opportunities).

    # ASEAN corridor relevance — FULL detail
    acr = data.get("asean_corridor_relevance")
    if acr and isinstance(acr, dict):
        lines.append("<h2>ASEAN Corridor Detail</h2>")
        for corridor, detail in acr.items():
            if isinstance(detail, dict):
                lines.append("<div class='callout'>")
                corr_name = corridor.replace("_", " ").title()
                lines.append(f"<div class='callout-title'>{_esc(corr_name)}</div>")
                for ck, cv in detail.items():
                    lines.append(f"<p><strong>{_esc(ck.replace('_', ' ').title())}:</strong> {_esc(str(cv))}</p>")
                lines.append("</div>")

    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
#  Section 4: Entity & Event Analysis
# ══════════════════════════════════════════════════════════════════════════════

def _render_section4_entities(data: dict) -> str:
    """Section 4: Entity &amp; Event Analysis."""
    if not data:
        return ""
    lines = ["<h1>4 &mdash; Entity &amp; Event Analysis</h1>"]

    # ASEAN entities
    asean = data.get("asean_entities")
    if asean and isinstance(asean, dict):
        total = asean.get("total_count", "")
        lines.append(f"<h2>ASEAN Entities (The bank Primary Targets) — {total} entities</h2>")

        # Collect all entities into a unified table
        all_asean = []
        for grp in ["direct_entities", "indirect_entities_by_guarantee"]:
            arr = asean.get(grp, [])
            if isinstance(arr, list):
                all_asean.extend(arr)

        if all_asean:
            asean_headers = ["Entity", "Country", "Ownership %", "Strategic Role"]
            asean_rows = []
            for ent in all_asean:
                name = _esc(ent.get("entity_name", ""))
                country = _esc(ent.get("country", ""))
                ownership = _esc(str(ent.get("ownership", "")))
                role = _esc(ent.get("strategic_role", ""))

                is_indirect = ent.get("indirect", False)
                if is_indirect:
                    ownership = f'<span class="entity-indirect">{ownership} (indirect)</span>'
                    # Tag SEA for all ASEAN entities
                    role = f'<span class="tag-sea">SEA</span> {role}'

                asean_rows.append([name, country, ownership, role])

            lines.append(_mk_table(asean_headers, asean_rows))

        # Guarantees + notes
        guarantees = asean.get("combined_parent_guarantees", "")
        if guarantees:
            lines.append(f"<p><strong>Combined Parent Guarantees:</strong> {_esc(str(guarantees))}</p>")
        notes = asean.get("bank_targeting_notes", "")
        if notes:
            lines.append(f"<p>{_esc(str(notes))}</p>")

    # Non-ASEAN entities
    non_asean = data.get("non_asean_entities")
    if non_asean and isinstance(non_asean, dict):
        total = non_asean.get("total_count", "")
        entities_list = non_asean.get("entities", [])
        if entities_list:
            lines.append(f"<h2>Non-ASEAN Entities (Top {total})</h2>")
            non_headers = ["Entity", "Country", "Ownership %", "Strategic Role"]
            non_rows = []
            for ent in entities_list:
                name = _esc(ent.get("entity_name", ""))
                country = _esc(ent.get("country", ""))
                ownership = _esc(str(ent.get("ownership", "")))
                role = _esc(ent.get("strategic_role", ""))

                is_indirect = ent.get("indirect", False)
                if is_indirect:
                    ownership = f'<span class="entity-indirect">{ownership} (indirect)</span>'

                non_rows.append([name, country, ownership, role])
            lines.append(_mk_table(non_headers, non_rows))

    # Key corporate events
    events = data.get("key_corporate_events")
    if events and isinstance(events, list):
        lines.append("<h2>Key Corporate Events</h2>")
        ev_headers = ["Event", "Amount", "Lending Implication"]
        ev_rows = []
        for ev in events:
            ev_rows.append([
                _esc(ev.get("event", "")),
                _esc(str(ev.get("amount", ""))),
                _esc(ev.get("lending_implication", "")),
            ])
        lines.append(_mk_table(ev_headers, ev_rows))

    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
#  Section 5: Risk Assessment  (NO quality check / traceability content)
# ══════════════════════════════════════════════════════════════════════════════

def _render_section5_risk(data: dict) -> str:
    """Section 5: Risk Assessment.  No QA / quality-check content."""
    if not data:
        return ""
    lines = ["<h1>5 &mdash; Risk Assessment</h1>"]

    # Skip keys related to QA / quality checks
    _QA_SKIP_KEYS = {
        "quality_check", "self_correction", "traceability",
        "figure_verification", "product_name_verification",
        "quality_score", "qa_checklist",
    }

    # Contradiction analysis
    ca = data.get("contradiction_analysis_summary")
    if ca and isinstance(ca, dict):
        total = ca.get("total_contradictions", 0)
        by_sev = ca.get("by_severity", {})
        sev_parts = ", ".join(f"{k}: {v}" for k, v in by_sev.items())
        lines.append(f"<h2>Contradiction Analysis ({total} identified — {sev_parts})</h2>")

        summary = ca.get("summary", [])
        if isinstance(summary, list):
            for item in summary:
                sev = item.get("severity", "Low")
                sev_cls = _severity_class(sev)
                cat = _esc(item.get("category", ""))
                finding = _esc(item.get("finding", ""))
                impl = _esc(item.get("credit_implication", ""))
                lines.append("<div class='contradiction-card'>")
                lines.append(f"<div class='card-header'><span class='{sev_cls}'>{_esc(sev.upper())}</span> &mdash; {cat}</div>")
                lines.append(f"<div class='card-body'><p><strong>Finding:</strong> {finding}</p>")
                lines.append(f"<p><strong>Credit Implication:</strong> {impl}</p></div>")
                lines.append("</div>")

        # Consistency note
        cn = ca.get("consistency_note", "")
        if cn:
            lines.append(f"<p><em>{_esc(cn)}</em></p>")

    # Strategy execution gaps
    gaps = data.get("strategy_execution_gaps")
    if gaps and isinstance(gaps, list):
        lines.append("<h2>Strategy Execution Gaps</h2>")
        gap_headers = ["Gap", "Detail", "the bank Relevance"]
        gap_rows = []
        for g in gaps:
            gap_rows.append([
                _esc(g.get("gap", "")),
                _esc(g.get("detail", "")),
                _esc(g.get("bank_relevance", "")),
            ])
        lines.append(_mk_table(gap_headers, gap_rows))

    # Risk boundary checks
    rbc = data.get("risk_boundary_checks")
    if rbc and isinstance(rbc, dict):
        lines.append("<h2>Risk Boundary Checks</h2>")

        # Hard prohibitions
        hp = rbc.get("hard_prohibitions")
        if hp and isinstance(hp, dict):
            lines.append("<h3>Hard Prohibitions</h3>")
            hp_headers = ["#", "Prohibition", "Status", "Note"]
            hp_rows = []
            for i, (k, v) in enumerate(hp.items(), 1):
                if k.lower() in _QA_SKIP_KEYS:
                    continue
                label = k.replace("_", " ").title()
                status_html = _risk_status_cell(v)
                hp_rows.append([str(i), label, status_html, _esc(str(v))])
            lines.append(_mk_table(hp_headers, hp_rows))

        # Phase-out
        po = rbc.get("phase_out")
        if po and isinstance(po, dict):
            lines.append("<h3>Phase-Out Items</h3>")
            po_headers = ["#", "Item", "Status", "Note"]
            po_rows = []
            for i, (k, v) in enumerate(po.items(), 1):
                if k.lower() in _QA_SKIP_KEYS:
                    continue
                label = k.replace("_", " ").title()
                status_html = _risk_status_cell(v)
                po_rows.append([str(i), label, status_html, _esc(str(v))])
            lines.append(_mk_table(po_headers, po_rows))

        # Verdict
        verdict = rbc.get("verdict", "")
        if verdict:
            lines.append("<div class='callout'>")
            lines.append(f"<div class='callout-title'>Boundary Verdict</div>")
            lines.append(f"<p>{_esc(verdict)}</p></div>")

    # Overall risk rating
    rating = data.get("overall_risk_rating")
    rationale = data.get("risk_rating_rationale")
    if rating:
        rating_slug = rating.lower().replace(" ", "-")
        lines.append("<h2>Overall Risk Rating</h2>")
        lines.append(f'<div class="risk-rating-box risk-rating-{rating_slug}">{_esc(rating)}</div>')
    if rationale:
        lines.append(f"<p>{_esc(rationale)}</p>")

    return "\n".join(lines)


def _render_appendix(data: list) -> str:
    """Render Appendix: Product Recommendations by Priority."""
    if not data or not isinstance(data, list):
        return ""
    lines = ["<h1>Appendix — the bank Product Recommendations</h1>"]

    for tier in data:
        priority = tier.get("priority", "")
        products = tier.get("products", [])
        badge_html = _badge(priority)
        lines.append(f"<h2>{badge_html} {_esc(priority)}</h2>")
        if products:
            lines.append("<ul>")
            for p in products:
                lines.append(f"<li>{_esc(p)}</li>")
            lines.append("</ul>")

    return "\n".join(lines)


def _render_footnotes() -> str:
    """Render the standard footnote block with all registered footnotes."""
    used = _footnote_used
    if not used:
        return ""

    lines = []
    lines.append('<hr>')
    lines.append('<div class="footnotes">')
    lines.append('<h3>Footnotes</h3>')

    # Display in order of STANDARD_FOOTNOTES, but only those used
    for label, text in STANDARD_FOOTNOTES:
        if label in used:
            ref = used[label]
            lines.append(f'<div class="footnote-item"><span class="footnote-label">{ref} {_esc(label)}:</span> {_esc(text)}</div>')

    lines.append('</div>')
    return "\n".join(lines)


# ── Top-Level Renderer ─────────────────────────────────────────────────────────

def render_report(report_json_path: str, output_html_path: str):
    """Main entry point: read JSON, render HTML."""
    with open(report_json_path, "r", encoding="utf-8") as f:
        report = json.load(f)

    # Reset footnote state
    global _footnote_counter, _footnote_used
    _footnote_counter = 0
    _footnote_used = {}

    # Collect sections
    body_parts = []

    # Report metadata → header
    meta = report.get("report_metadata")
    if meta and isinstance(meta, dict):
        body_parts.append(_render_header(meta))

    # ── Load all section data upfront ──
    sec0 = report.get("section_0_executive_summary") or report.get("executive_summary") or {}
    sec1 = report.get("section_1_financial_analysis") or report.get("financial_analysis") or {}
    sec2 = report.get("section_2_strategy_commercial_alignment") or report.get("strategy_commercial_alignment") or {}
    sec3 = report.get("section_3_entity_event_analysis") or report.get("entity_event_analysis") or {}
    sec4 = report.get("section_4_risk_assessment") or report.get("risk_assessment") or {}

    # ── Section 1: Executive Summary & Commercial Opportunities ──
    # Pass BOTH exec_data and strategy_data so pain points + corridors are pulled forward.
    if sec0 or sec2:
        body_parts.append(_render_section1_executive(sec0, sec2))

    # ── Section 2: Financial Analysis ──
    if sec1:
        body_parts.append(_render_section2_financial(sec1))

    # ── Section 3: Strategy & Supply Chain ──
    if sec2:
        body_parts.append(_render_section3_strategy(sec2))

    # ── Section 4: Entity & Event Analysis ──
    if sec3:
        body_parts.append(_render_section4_entities(sec3))

    # ── Section 5: Risk Assessment ──
    if sec4:
        body_parts.append(_render_section5_risk(sec4))

    # Appendix
    appendix = report.get("appendix_bank_product_recommendations_priority") or report.get("appendix")
    if appendix:
        body_parts.append(_render_appendix(appendix))

    # Footnotes
    body_parts.append(_render_footnotes())

    body = "\n".join(body_parts)

    # Apply page citation styling globally
    body = _cite_pages(body)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Wholesale Banking Corporate Insight Report</title>
<style>
{CSS_LEGACY}
{CSS_ADDITIONS}
</style>
</head>
<body>

{body}

</body>
</html>
"""
    # Write output
    out_path = Path(output_html_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")

    print(f"Report rendered: {out_path}")
    print(f"  Lines: {len(html.splitlines())}")
    print(f"  Footnoted claims: {_footnote_counter}")
    return out_path


# ── CLI ────────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    output_dir = Path(sys.argv[1])
    if not output_dir.is_absolute():
        output_dir = Path.cwd() / output_dir

    report_json = output_dir / "synthesis" / "report.json"
    if not report_json.exists():
        print(f"ERROR: report.json not found at {report_json}")
        sys.exit(2)

    report_html = output_dir / "synthesis" / "report.html"

    render_report(str(report_json), str(report_html))


if __name__ == "__main__":
    main()
