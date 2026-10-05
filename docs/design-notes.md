# Design-Decision Log

Precedents and rationale behind the pipeline's design decisions. Company names are
fictional placeholders (DemoEV, DemoMotor, ...).

| # | Decision | Why |
|---|----------|-----|
| 1 | `v1`/`v2` versioning for repeat runs | Same company may run multiple times with prompt tweaks |
| 2 | English-only file/directory names | Avoid Unicode path issues across tools |
| 3 | 3-year scope | **Iterate, never assume.** Go to the company's IR/disclosure page, scrape the actual available year list, verify by downloading the latest candidate PDF. Once confirmed, derive year set = `[latest-2, latest-1, latest]`. Do NOT assume `current_year - 1` — some companies publish earlier, later, or on different schedules. This caused a DemoInfra miss: we defaulted to 2024 when 2025 was already published. |
| 4 | 13-dimension contradiction detection | A1-A5 (financial) + B1-B5 (strategic) + C1-C3 (cross) |
| 5 | `latest/` symlink to newest version | Toolchains reference stable path, not version-specific |
| 6 | Final report at version root | `{Company}_3Y_Report.html` — one click to find |
| 17 | **Strategy source is country-dependent** | Chinese annual reports bundle MD&A + financials in one PDF. Korean companies split them: financial statements (English) + business report/사업보고서 (Korean) + IR presentations (English). Non-Chinese companies may need strategy content from a separate document (IR deck, analyst presentation) rather than from the router's tagged/strategy.md. Pipeline must support `--strategy-source` or auto-detect when strategy.md is <10KB after routing. DemoInfra precedent: strategy came from CEO Investor Day + quarterly IR presentations, manually written to tagged/strategy.md. |
| 18 | **Finance extraction is accounting-standard-agnostic** | The pipeline was built on Chinese GAAP account names (营业收入, 营业成本, 应付票据). K-IFRS uses different names (Revenue, Cost of Sales, Trade Payables — no Notes Payable concept). extract-finance agent needs explicit per-standard mapping. Chinese GAAP ≠ K-IFRS ≠ US GAAP ≠ IFRS. Agent prompts must include a mapping table when the source is not Chinese GAAP. DemoInfra FY2024 COGS required derivation because the income statement face page wasn't tagged by the router — a cascading failure from the document-structure issue above. |
| 7 | `_run.json` + `_token_log.md` metadata | Reproducibility and cost tracking |
| 8 | One skill per node: `skills/<name>/SKILL.md` | Standard skill packaging; harness loads the file the workflow names |
| 9 | Router: keyword-based chapter detection | Robust to OCR noise, human-auditable |
| 10 | Agent orchestration via Workflow scripts | Deterministic steps in Python, LLM steps in Workflow |
| 11 | ~50% deterministic (zero LLM tokens) | PDF parse, chapter detect, finance calc, contradiction calc — all Python |
| 12 | Bank product framework injected at synthesis | Keeps the synthesizer bank-agnostic; framework lives in `reference/product-framework/` |
| 13 | PyMuPDF + Tesseract hybrid parser | MHeiHK CID fonts in CN annual reports require OCR |
| 14 | File-existence checkpoint skip | Same prompt works for full run or resume |
| 15 | Review-Fix loop with 90 threshold | Industry standard QC; review embedded in pipeline. Max 3 iterations. Score = max(0, 100 - 20*HIGH - 5*MED - 1*LOW). ≥90 → deliver; <90 → fix → re-review |
| 16 | **Surgical fix, not re-synthesize** | Re-synthesizing the entire HTML report from scratch loses context, introduces new errors, and dilutes reviewer attention. Fix iterations MUST apply targeted edits directly to the HTML — change only the sentences/paragraphs/numbers flagged by review. One edit per finding. Do NOT regenerate the whole report. DemoEV v1 precedent: 3 full re-synthesize rounds produced score 75; one pass of 9 surgical edits fixed all issues. |
