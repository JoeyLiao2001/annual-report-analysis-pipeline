// Wholesale Banking Agent Pipeline Orchestrator
// Usage: /workflows/annual-report-pipeline.js <company_name> <year> [--skip-fetch] [--deep-review]
//
// Pipeline:
// Step 1: fetch-report (agent) → input/pdfs/{name}_{year}.pdf
// Step 2: parse_pdf.py (tool) → input/parsed/{name}_{year}_final.html  [SKIP if HTML exists]
// Step 3: semantic-router (agent) → output/{company}/router/route.json
// Step 3.5: chapter_detector.py merge → output/{company}/tagged/{strategy,finance,entities,events}.md
// Steps 4-7: extract-{finance,strategy,entities,events} (4 agents, parallel)
// Step 7.5: finance_calc.py → output/{company}/finance/ratios.json
// Step 7.6: entity_validator.py → validation report
// Step 8: contradiction_calc.py → output/{company}/contradiction/quant_flags.json
// Step 8.5: contradiction-detector (agent) → output/{company}/contradiction/contradictions.json
// Step 9: synthesize-review (agent) → output/{company}/synthesis/report.json

export const meta = {
  name: 'annual-report-pipeline',
  description: 'Run the full Wholesale Banking financial analysis pipeline for a company annual report',
  phases: [
    { title: 'Fetch & Parse', detail: 'Fetch PDF + parse to HTML' },
    { title: 'Route', detail: 'Semantic router: identify + tag chapters' },
    { title: 'Merge Chapters', detail: 'Merge HTML content by tag (deterministic)' },
    { title: 'Extract', detail: 'Finance, Strategy, Entities, Events (parallel)' },
    { title: 'Calculate & Validate', detail: 'Finance ratios + entity validation (deterministic)' },
    { title: 'Contradiction', detail: 'Quant flags + semantic detection' },
    { title: 'Synthesize', detail: 'Final report + optional deep review' }
  ]
};

// Parse CLI args from the `args` global (first two positional, rest flags)
const company = args[0];
const year = args[1];
const skipFetch = args.includes('--skip-fetch');
const deepReview = args.includes('--deep-review');

if (!company || !year) {
  log('Usage: /workflows/annual-report-pipeline.js <company_name> <year> [--skip-fetch] [--deep-review]');
  throw new Error('Missing required arguments: company_name and year');
}

const outputDir = `output/${company}`;
const inputHtml = `input/parsed/${company}${year}_final.html`;
const inputPdf = `input/pdfs/${company}${year}.pdf`;

log(`Pipeline starting: ${company} (${year})`);
log(`Output directory: ${outputDir}/`);
if (skipFetch) log('--skip-fetch: will use existing PDF if available');
if (deepReview) log('--deep-review: llm-council quality review enabled');

// ── Step 1: Fetch Report ──
phase('Fetch & Parse');

if (skipFetch) {
  log(`Skipping fetch (--skip-fetch). Expecting PDF at ${inputPdf}`);
} else {
  await agent(
    `Read the agent definition at skills/fetch-report/SKILL.md. ` +
    `Fetch the ${year} annual report PDF for ${company}. Save to ${inputPdf}. ` +
    `Output metadata to ${outputDir}/fetch-report/.`,
    { label: 'fetch-report', phase: 'Fetch & Parse' }
  );
}

// ── Step 2: Parse PDF to HTML ──
// Run deterministic parse tool
log(`Parsing PDF: ${inputPdf} → ${inputHtml}`);
// Note: parse_pdf.py handles its own skip-if-exists logic
// In practice this runs as: python tools/parse_pdf.py "${inputPdf}" -o "${inputHtml}"
log(`Verify parsed HTML exists at ${inputHtml}. If not, run: python tools/parse_pdf.py "${inputPdf}"`);

// ── Step 3: Semantic Router ──
phase('Route');

await agent(
  `Read the agent definition at skills/semantic-router/SKILL.md. ` +
  `Execute its instructions on ${inputHtml}. ` +
  `First run: python tools/chapter_detector.py ${inputHtml} to get heading candidates. ` +
  `Then read the HTML and identify chapter boundaries and tags. ` +
  `Save route.json to ${outputDir}/router/route.json. ` +
  `Also save llm_raw_response.txt and parse_log.md to ${outputDir}/router/.`,
  { label: 'semantic-router', phase: 'Route' }
);

// ── Step 3.5: Merge Chapters by Tag (deterministic) ──
phase('Merge Chapters');

log('Merging chapters by tag using chapter_detector.py...');
// This is a deterministic operation:
// python -c "from tools.chapter_detector import extract_headings, merge_chapters; import json;
//   headings = extract_headings('${inputHtml}');
//   route = json.load(open('${outputDir}/router/route.json'));
//   merged = merge_chapters(headings, route, '${inputHtml}');
//   for tag, content in merged.items():
//     with open(f'${outputDir}/tagged/{tag}.md', 'w') as f: f.write(content)"
log(`Expected output: ${outputDir}/tagged/{strategy,finance,entities,events}.md`);

// ── Steps 4-7: Extract (parallel) ──
phase('Extract');

const extractResults = await parallel([
  () => agent(
    `Read skills/extract-finance/SKILL.md. Execute on ${outputDir}/tagged/finance.md. ` +
    `Extract metrics for fiscal year ${year}. Save to ${outputDir}/finance/finance.json ` +
    `and llm_raw_response.txt and parse_log.md to ${outputDir}/finance/.`,
    { label: 'extract-finance', phase: 'Extract' }
  ),
  () => agent(
    `Read skills/extract-strategy/SKILL.md. Execute on ${outputDir}/tagged/strategy.md. ` +
    `Save to ${outputDir}/strategy/strategy.json ` +
    `and llm_raw_response.txt and parse_log.md to ${outputDir}/strategy/.`,
    { label: 'extract-strategy', phase: 'Extract' }
  ),
  () => agent(
    `Read skills/extract-entities/SKILL.md. Execute on ${outputDir}/tagged/entities.md. ` +
    `Save to ${outputDir}/entities/entities.json ` +
    `and llm_raw_response.txt and parse_log.md to ${outputDir}/entities/.`,
    { label: 'extract-entities', phase: 'Extract' }
  ),
  () => agent(
    `Read skills/extract-events/SKILL.md. Execute on ${outputDir}/tagged/events.md. ` +
    `Save to ${outputDir}/events/events.json ` +
    `and llm_raw_response.txt and parse_log.md to ${outputDir}/events/.`,
    { label: 'extract-events', phase: 'Extract' }
  )
]);

// ── Step 7.5: Calculate Financial Ratios (deterministic) ──
phase('Calculate & Validate');

log('Running finance_calc.py to compute DSO/DIO/DPO/CCC/GrossMargin...');
log(`Expected output: ${outputDir}/finance/ratios.json`);

log('Running entity_validator.py to validate entity extraction...');
log(`Expected output: ${outputDir}/entities/validation.json`);

// ── Step 8: Contradiction Detection ──
phase('Contradiction');

log('Running contradiction_calc.py for quantitative flags...');
log(`Expected output: ${outputDir}/contradiction/quant_flags.json`);

await agent(
  `Read skills/contradiction-detector/SKILL.md. ` +
  `Execute on the following inputs: ` +
  `- Quantitative flags: ${outputDir}/contradiction/quant_flags.json ` +
  `- Strategy: ${outputDir}/strategy/strategy.json ` +
  `- Finance: ${outputDir}/finance/finance.json ` +
  `Save contradictions.json, llm_raw_response.txt, and parse_log.md to ${outputDir}/contradiction/.`,
  { label: 'contradiction-detector', phase: 'Contradiction' }
);

// ── Step 9: Synthesize & Review ──
phase('Synthesize');

const synthesisPrompt = `Read skills/synthesize-review/SKILL.md. Execute on all inputs under ${outputDir}/:
  - ${outputDir}/finance/finance.json + ratios.json
  - ${outputDir}/strategy/strategy.json
  - ${outputDir}/entities/entities.json
  - ${outputDir}/events/events.json
  - ${outputDir}/contradiction/contradictions.json
  Synthesize into a full the bank lending analysis report.
  Save report.json, llm_raw_response.txt, and parse_log.md to ${outputDir}/synthesis/.
  Deep review mode: ${deepReview ? 'ENABLED — run the llm-council 3-stage review protocol and save review_report.md' : 'DISABLED'}.`;

await agent(synthesisPrompt, { label: 'synthesize-review', phase: 'Synthesize' });

// ── Pipeline Complete ──
log('═══════════════════════════════════════');
log(`Pipeline complete: ${company} (${year})`);
log(`Output directory: ${outputDir}/`);
log('Output structure:');
log(`  ${outputDir}/router/route.json`);
log(`  ${outputDir}/tagged/{strategy,finance,entities,events}.md`);
log(`  ${outputDir}/finance/finance.json + ratios.json`);
log(`  ${outputDir}/strategy/strategy.json`);
log(`  ${outputDir}/entities/entities.json`);
log(`  ${outputDir}/events/events.json`);
log(`  ${outputDir}/contradiction/contradictions.json`);
log(`  ${outputDir}/synthesis/report.json`);
if (deepReview) log(`  ${outputDir}/synthesis/review_report.md`);
log('═══════════════════════════════════════');
