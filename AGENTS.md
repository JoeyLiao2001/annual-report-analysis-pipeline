# Annual Report Analysis Pipeline — Harness Manual

Operating manual for agent-harness tools (Codex, Claude Code, ...) driving this pipeline:
raw listed-company annual reports in → cited, cross-checked wholesale-banking credit &
opportunity report out.

**Design principle:** deterministic Python for all arithmetic; LLM agents for semantic work
only. ~50% of the pipeline runs with zero LLM tokens, and every claim stays traceable to the
source document.

## Pipeline

```
fetch-report → parse_pdf.py → semantic-router
    → extract-{finance,strategy,entities,events} (parallel)
    → finance_calc.py → contradiction_calc.py → contradiction-detector
    → synthesize-review (+ bank product framework, injected)
    → review {auditor, CFO, risk officer} → score ≥ 90 ? deliver : surgical fix (max 3)
```

**Quality gate.** Three blinded reviewers score the report 0–100
(`100 − 20·HIGH − 5·MED − 1·LOW`); below 90 loops back. Fix iterations apply **targeted
edits to the delivered HTML** — never a full re-synthesis.

## Skills

One skill per pipeline node, packaged as `skills/<name>/SKILL.md` (frontmatter carries name,
description, model, temperature; the body is the system prompt + IO contract). Workflow
orchestrators invoke them in sequence.

| Skill | Role |
|---|---|
| `fetch-report` | locate & download the annual report PDF (WebSearch) |
| `semantic-router` | tag chapter boundaries in the parsed HTML |
| `extract-finance` / `extract-strategy` / `extract-entities` / `extract-events` / `extract-ratios` | per-domain extraction (JSON schemas) |
| `contradiction-detector` | 13-dimension cross-year contradiction analysis |
| `synthesize-review` | synthesis + injected bank product framework |
| `review-auditor` / `review-cfo` / `review-risk-officer` | blinded 3-perspective review |
| `verify-timeliness` | anti-stale desktop search on every recommendation |

## Tools (deterministic, zero LLM tokens)

| Tool | Purpose |
|---|---|
| `parse_pdf.py` | PDF → HTML (PyMuPDF + Tesseract OCR hybrid for CN CID fonts) |
| `batch_parse.py` | overnight batch parser |
| `chapter_detector.py` | heading extraction + tag merge |
| `finance_calc.py` | DSO / DIO / DPO / CCC / gross margin |
| `contradiction_calc.py` | 12 quantitative cross-year rules |
| `entity_validator.py` | country & ASEAN validation |
| `compute_metrics.py` | one company/version: ratios + flags |
| `compute_all_years.py` | one-shot 3-year ratios + flags |
| `run_multi_year.py` | deterministic pre/post-processing runner |
| `headroom_compress.py` | HTML compression before LLM ingestion |
| `industry_benchmark.py` | industry benchmark layer (skips gracefully if data absent) |
| `render_report.py` | `report.json` → styled HTML report |
| `distress_model/` | CDEW financial distress model — tested sub-project |

## Running

```
/workflows/annual-report-pipeline.js <Company> <Year>            # single year
/workflows/annual-report-pipeline-multi-year.js <Company> <Y1..3> # three years + cross-year
python tools/run_multi_year.py <Company> <Y1> <Y2> <Y3>           # deterministic steps only
```

LLM access via `.env` (see `.env.example`). Pre-parsed HTML can be dropped into
`input/parsed/{Company}_{Year}_final.html` to skip fetch + parse.

## Path conventions (hard rules)

| Path | Written by | Notes |
|---|---|---|
| `input/pdfs/` | `fetch-report` only | ingest-once, read-only after |
| `input/parsed/` | `parse_pdf.py` only | `{Company}{Year}_final.html` |
| `output/{Company}/{version}/` | pipeline agents + `compute_metrics.py` + `render_report.py` | everything else is read-only |

- Absolute paths only; English-only file and directory names.
- File-existence checkpoint skip: the same prompts serve a full run or a mid-pipeline resume.
- Final deliverable sits at the version root: `{Company}_3Y_Report.html`.

Design precedents and the full decision log live in [docs/design-notes.md](docs/design-notes.md).
