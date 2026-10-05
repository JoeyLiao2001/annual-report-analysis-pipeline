// Wholesale Banking Multi-Year Pipeline Orchestrator
// ==========================================
// Runs the 9-step pipeline across 3 fiscal years, then cross-year analysis.
//
// Usage: /workflows/annual-report-pipeline-multi-year.js <company_name> <year1> <year2> <year3> [--skip-fetch] [--skip-route] [--version <vN>] [--deep-review]
// Example: /workflows/annual-report-pipeline-multi-year.js DemoMotor 2023 2024 2025 --skip-route --version v2
//
// When invoked from pipeline-run skill:
//   args: ["DemoElectronics", 2023, 2024, 2025, "--skip-fetch", "--skip-route", "--version", "v1"]
//
// Phases:
//   0) Route: Chapter detection + semantic router -> tagged/ files (skip with --skip-route)
//   1) Extract: 8 agents parallel -- financex3 + strategyx3 + entitiesx1 + eventsx1
//   2) Calculate: Deterministic Python (compute_metrics.py) -> ratios.json + quant_flags.json
//   3) Cross-Year Contradiction: 13-dimension LLM (A1-A5 quant, B1-B5 strategy, C1-C3 joint)
//   4) Synthesize & Review Loop: Synthesize -> Review -> Fix (max 3 iterations, threshold 90)
//   5) Package: Confirm deliverables at version root
//
// Pre-workflow steps handled by pipeline-run skill:
//   A) Year probe: WebSearch to find latest available annual report
//   B) Version detect: Auto-increment version number
//   C) Fetch + Parse: Download PDFs -> parse to HTML
//   D) Create output structure + _run.json
//   E) Route: Chapter detection + merge -> tagged/ files (then workflow with --skip-route)

export const meta = {
  name: 'annual-report-pipeline-multi-year',
  description: '3-year Wholesale Banking financial analysis with CCC trajectory, strategy consistency, and cross-year contradiction detection',
  phases: [
    { title: 'Route Y1/Y2/Y3', detail: 'Semantic router for each year (parallel)' },
    { title: 'Extract Y1/Y2/Y3', detail: 'Finance + Strategy extraction for all 3 years + entities/events for Y3 (parallel)' },
    { title: 'Calculate', detail: 'Per-year ratios + cross-year quant flags (deterministic, Python)' },
    { title: 'Cross-Year Contradiction', detail: '13-dimension LLM contradiction detection' },
    { title: 'Synthesize & Review Loop', detail: 'Synthesize -> Review -> Fix (max 3 iterations, threshold 90)' },
    { title: 'Package', detail: 'Copy deliverables to version root' },
  ],
};

// -- Parse args: [company, y1, y2, y3, ...flags] --
const company = args[0];
const years = [parseInt(args[1]), parseInt(args[2]), parseInt(args[3])];
const skipFetch = args.includes('--skip-fetch');
const skipRoute = args.includes('--skip-route');
const deepReview = args.includes('--deep-review');

// Parse --version flag: --version v2 -> "v2", default "v1"
const versionIdx = args.indexOf('--version');
const VERSION = versionIdx !== -1 && args[versionIdx + 1] ? args[versionIdx + 1] : 'v1';

if (!company || years.some(isNaN)) {
  log('Usage: /workflows/annual-report-pipeline-multi-year.js <company> <year1> <year2> <year3> [--skip-fetch] [--skip-route] [--version <vN>] [--deep-review]');
  throw new Error('Missing required arguments: company and 3 fiscal years');
}

const [Y1, Y2, Y3] = years;
const ABS_OUTPUT = `D:\\\\NUS\\\\the bank\\\\this repo\\\\output\\\\${company}\\\\${VERSION}`;
const outputDir = (y) => `${ABS_OUTPUT}\\\\Y${y}`;
const inputHtml  = (y) => `D:\\\\NUS\\\\the bank\\\\this repo\\\\input\\\\parsed\\\\${company}${y}_final.html`;

log(`Multi-Year Pipeline: ${company} (${Y1}/${Y2}/${Y3})`);
log(`Version: ${VERSION}`);
log(`Output: ${ABS_OUTPUT}`);
if (skipFetch) log('--skip-fetch: using pre-parsed HTML');
if (skipRoute) log('--skip-route: tagged/ files already exist');
if (deepReview) log('--deep-review: llm-council quality review enabled');

// ==================================================================
// Route all 3 years (parallel) -- SKIP if --skip-route
// =====    Produces tagged/{finance,strategy,entities,events}.md
// ==================================================================
phase('Route Y1/Y2/Y3');

if (!skipRoute) {
  const routeResults = await parallel(
    years.map(y => () => agent(
      `Read the agent definition at skills/semantic-router/SKILL.md. ` +
      `Execute its instructions on ${inputHtml(y)}. ` +
      `First run: python tools/chapter_detector.py ${inputHtml(y)}. ` +
      `Then read the HTML and identify chapter boundaries and tags. ` +
      `Save route.json to ${outputDir(y)}/router/route.json. ` +
      `Also save llm_raw_response.txt and parse_log.md to ${outputDir(y)}/router/. ` +
      `Also merge chapters by tag and save to ${outputDir(y)}/tagged/{finance,strategy,entities,events}.md. ` +
      `Company: ${company}, Fiscal Year: ${y}`,
      { label: `route-Y${y}`, phase: 'Route Y1/Y2/Y3' }
    ))
  );

  log(`Route complete: Y${Y1}=${routeResults[0] ? 'done' : 'FAILED'}, Y${Y2}=${routeResults[1] ? 'done' : 'FAILED'}, Y${Y3}=${routeResults[2] ? 'done' : 'FAILED'}`);
} else {
  log('--skip-route: tagged/ files already exist, skipping chapter detection and routing');
  log(`Expected tagged files per year: ${outputDir('{Y}')}/tagged/{finance,strategy,entities,events}.md`);
}

// ==================================================================
// Phase 3: Extract -- Y1/Y2 slim (finance+strategy only), Y3 full
// =====  8 agents run concurrently  ==============================
//        Y1: finance + strategy (2 agents, ~150 pages each)
//        Y2: finance + strategy (2 agents, ~150 pages each)
//        Y3: finance + strategy + entities + events (4 agents)
//        Estimated total: ~230K tokens vs ~570K for full 3-year
// ==================================================================
phase('Extract Y1/Y2/Y3');

const extractResults = await parallel([
  // -- Finance (all 3 years) --
  ...years.map(y => () => agent(
    `Read skills/extract-finance/SKILL.md. Execute on ${outputDir(y)}/tagged/finance.md. ` +
    `IMPORTANT: Extract metrics ONLY for fiscal year ${y}. Ignore other years. ` +
    `Save finance.json, llm_raw_response.txt, and parse_log.md to ${outputDir(y)}/finance/. ` +
    `Company: ${company}, Fiscal Year: ${y}`,
    { label: `finance-Y${y}`, phase: 'Extract Y1/Y2/Y3' }
  )),

  // -- Strategy (all 3 years) --
  ...years.map(y => () => agent(
    `Read skills/extract-strategy/SKILL.md. Execute on ${outputDir(y)}/tagged/strategy.md. ` +
    `Save strategy.json, llm_raw_response.txt, and parse_log.md to ${outputDir(y)}/strategy/. ` +
    `Company: ${company}, Fiscal Year: ${y}`,
    { label: `strategy-Y${y}`, phase: 'Extract Y1/Y2/Y3' }
  )),

  // -- Entities (Y3 only -- current entity structure) --
  () => agent(
    `Read skills/extract-entities/SKILL.md. Execute on ${outputDir(Y3)}/tagged/entities.md. ` +
    `CRITICAL: Apply ASEAN Greedy Extraction (unlimited ASEAN, non-ASEAN <= 10). ` +
    `Country = Singapore -> [SG PRIORITY]. Scan guarantee disclosures, related-party transactions, and segment reports for indirect ASEAN subsidiaries. ` +
    `Save entities.json, llm_raw_response.txt, and parse_log.md to ${outputDir(Y3)}/entities/. ` +
    `Company: ${company}, Fiscal Year: ${Y3}`,
    { label: `entities-Y${Y3}`, phase: 'Extract Y1/Y2/Y3' }
  ),

  // -- Events (Y3 only -- latest material events) --
  () => agent(
    `Read skills/extract-events/SKILL.md. Execute on ${outputDir(Y3)}/tagged/events.md. ` +
    `Save events.json, llm_raw_response.txt, and parse_log.md to ${outputDir(Y3)}/events/. ` +
    `Company: ${company}, Fiscal Year: ${Y3}`,
    { label: `events-Y${Y3}`, phase: 'Extract Y1/Y2/Y3' }
  ),
]);

const financeDone = years.filter((_, i) => extractResults[i]).length;
const strategyDone = years.filter((_, i) => extractResults[3 + i]).length;
const entitiesDone = extractResults[6] ? 1 : 0;
const eventsDone = extractResults[7] ? 1 : 0;
log(`Extraction: Finance ${financeDone}/3, Strategy ${strategyDone}/3, Entities ${entitiesDone}/1 (Y${Y3}), Events ${eventsDone}/1 (Y${Y3})`);

// ==================================================================
// Phase 4: Calculate per-year ratios + cross-year contradiction flags
// =======  Deterministic (Python, zero LLM tokens)  ==============
// ==================================================================
phase('Calculate');

// Run compute_metrics.py which handles both per-year ratios and cross-year quant_flags
await agent(
  `Run the deterministic calculation tool:

   Execute: python <repo>/tools/compute_metrics.py ${company} ${VERSION}

   This will:
   - Compute per-year ratios (DSO, DIO, DPO, CCC, Gross Margin) for each year
   - Save ratios.json to ${outputDir('{Y}')}/finance/ for each year
   - Compute cross-year contradiction quant_flags (12 rules including A1-A5)
   - Save to ${ABS_OUTPUT}/cross_year/quant_flags.json

   Report the output: DSO/DPO/CCC/GM values per year and flag summary.`,
  { label: 'compute-ratios-flags', phase: 'Calculate' }
);

  log('Calculate complete. Ratios and quant_flags saved.');

// ==================================================================
// Phase 5: Cross-Year Contradiction (LLM -- 13 dimensions)
// =======  2-pass protocol:
//          Pass 1: compare 3 strategy.json (B1-B5) w/o seeing finance
//          Pass 2: read quant_flags + finance data (C1-C3)
//          A1-A5 financial trends = pre-computed in quant_flags.json
// ==================================================================
phase('Cross-Year Contradiction');

await agent(
  `Read skills/contradiction-detector/SKILL.md (13-dimension multi-year protocol). Execute:

  === PASS 1: Strategy Evolution (B1-B5) ===
  Read ONLY these three files:
    - ${outputDir(Y1)}/strategy/strategy.json
    - ${outputDir(Y2)}/strategy/strategy.json
    - ${outputDir(Y3)}/strategy/strategy.json

  Compare them for:
    B1. Risk Narrative Evolution -- risks appearing/disappearing/escalating
    B2. Business Segment Trajectory -- segments/frameworks abandoned or renamed
    B3. Geographic Focus Evolution -- internationalization accelerating/retreating
    B4. Management Tone Evolution -- expansion->stability->cost-cutting trajectory
    B5. Supply Chain Concentration Narrative -- concentration mentions changing

  === PASS 2: Cross-Dimension (C1-C3) ===
  Now read:
    - output/${company}/cross_year/quant_flags.json (12 quantitative rules including A1-A5)
    - ${outputDir(Y1)}/finance/finance.json + ratios.json
    - ${outputDir(Y2)}/finance/finance.json + ratios.json
    - ${outputDir(Y3)}/finance/finance.json + ratios.json

  Cross-reference with Pass 1 findings for:
    C1. Strategy Promise vs Financial Delivery -- did Y1 commitments materialize?
    C2. Adversity Narrative vs Data Honesty -- is management honest about problems?
    C3. Internationalization Rhetoric vs Entity Footprint -- slogans or real execution?

  CRITICAL: A1-A5 financial trends are pre-computed in quant_flags.json.
  Reference them but do NOT duplicate -- add semantic interpretation.

  Save contradictions.json, llm_raw_response.txt, and parse_log.md to output/${company}/cross_year/.`,
  { label: 'cross-year-contradiction', phase: 'Cross-Year Contradiction' }
);

// ==================================================================
  log('Contradiction detection complete. 13 dimensions analyzed.');

// Phase 6: Synthesize -> Review -> Surgical Fix loop
// =======  Quality gate at 90/100. Max 3 iterations (1 synthesize + up to 2 surgical fix rounds).
//          DD16 (2026-07-06): Fix = targeted HTML edits, NOT re-synthesize.
//          Re-synthesizing the entire report loses context and introduces new errors.
//          Each review finding → one Edit(old, new) on the HTML.
// ==================================================================

const QUALITY_THRESHOLD = 90;
const MAX_FIX_ITERATIONS = 3;

const SOURCE_FILES = `
    - ${ABS_OUTPUT}/Y${Y1}/finance/finance.json + ratios.json
    - ${ABS_OUTPUT}/Y${Y2}/finance/finance.json + ratios.json
    - ${ABS_OUTPUT}/Y${Y3}/finance/finance.json + ratios.json
    - ${ABS_OUTPUT}/Y${Y1}/strategy/strategy.json
    - ${ABS_OUTPUT}/Y${Y2}/strategy/strategy.json
    - ${ABS_OUTPUT}/Y${Y3}/strategy/strategy.json
    - ${ABS_OUTPUT}/Y${Y3}/entities/entities.json + parse_log.md
    - ${ABS_OUTPUT}/Y${Y3}/events/events.json + parse_log.md
    - ${ABS_OUTPUT}/cross_year/contradictions.json
    - ${ABS_OUTPUT}/cross_year/quant_flags.json
  `;

let score = 0;
let iteration = 0;

// ====================================================================
// ITERATION 1: Full synthesize (first and ONLY full generation)
// ====================================================================
iteration++;
phase(`Synthesize v1 (full generation)`);

await agent(`Read skills/synthesize-review/SKILL.md. Execute on ALL inputs:

  === 3-YEAR FINANCE ===
  ${ABS_OUTPUT}/Y${Y1}/finance/finance.json + ratios.json
  ${ABS_OUTPUT}/Y${Y2}/finance/finance.json + ratios.json
  ${ABS_OUTPUT}/Y${Y3}/finance/finance.json + ratios.json

  === 3-YEAR STRATEGY ===
  ${ABS_OUTPUT}/Y${Y1}/strategy/strategy.json
  ${ABS_OUTPUT}/Y${Y2}/strategy/strategy.json
  ${ABS_OUTPUT}/Y${Y3}/strategy/strategy.json

  === CURRENT STATE (Y${Y3}) ===
  Entities: ${ABS_OUTPUT}/Y${Y3}/entities/entities.json
  Events:   ${ABS_OUTPUT}/Y${Y3}/events/events.json

  === CROSS-YEAR ===
  Quant flags: ${ABS_OUTPUT}/cross_year/quant_flags.json
  Contradictions: ${ABS_OUTPUT}/cross_year/contradictions.json

  === DELIVERABLES ===
  Produce the bank lending analysis report with 6 sections as defined in synthesize-review.md:
  1. Executive Summary -- company ID, 3-year key metrics table, the bank opportunities, risk verdict
  2. Financial Analysis -- revenue/profit trends, working capital (DSO/DIO/DPO/CCC), margin analysis
  3. Strategy & Commercial Alignment -- business model, supply chain, ASEAN footprint, pain point->product mapping
  4. Entity & Event Analysis -- ASEAN/non-ASEAN entity tables, material events with lending implications
  5. Risk Assessment -- cross-reference contradictions.json, strategy-execution gaps, risk boundary verification
  6. The bank Product Recommendations -- specific the bank products, rationale, priority, risk boundary check

  Apply ALL writing style rules (Humanizer, MECE, anti-repetition, no dashes, no signposting, credit conclusion first).
  Apply ALL entity active-status verification and event temporal scope rules from Section 4.
  Apply ALL strategy temporal priority rules from Section 3.

  CRITICAL CONSTRAINTS:
  - All data points MUST cite specific source files. Do not fabricate or estimate numbers.
  - The bank business scope: Singapore, Malaysia, Thailand, Vietnam, Indonesia, China corridors ONLY.

  SAVE TO:
  - ${ABS_OUTPUT}/synthesis/report.json
  - ${ABS_OUTPUT}/synthesis/llm_raw_response.txt
  - ${ABS_OUTPUT}/synthesis/parse_log.md
  - ${ABS_OUTPUT}/${company}_3Y_Report.html (render the report as styled HTML)
  `, { label: `synthesize-v1`, phase: `Synthesize & Review Loop` });

log('Synthesize v1 complete.');

while (iteration < MAX_FIX_ITERATIONS) {

  // ==================================================================
  // REVIEW (runs every iteration — provenance + 3 perspectives + cross-exam)
  // ==================================================================
  phase(`Review v${iteration}`);

  await agent(`Read skills/synthesize-review/SKILL.md Pre-Review: Data Provenance Check section.
  Run data provenance check on ${ABS_OUTPUT}/${company}_3Y_Report.html.

  Cross-validate against source data: ${SOURCE_FILES}

  Flag: ENTITY_LOW_CONFIDENCE, ENTITY_CONFIRMED_DEREGISTERED, ENTITY_MISSING_CURRENT_YEAR, EVENT_SOURCE_MISMATCH, EVENT_PRIOR_YEAR, EVENT_MISSING_SUBSEQUENT_FLAG.

  SAVE provenance report to: ${ABS_OUTPUT}/synthesis/provenance_v${iteration}.md
  `, { label: `provenance-v${iteration}`, phase: `Synthesize & Review Loop` });

  // -- Stage 1: Four Independent Perspectives --
  await parallel([
    () => agent(`Read skills/review-auditor/SKILL.md.
    Review: ${ABS_OUTPUT}/${company}_3Y_Report.html
    Provenance report: ${ABS_OUTPUT}/synthesis/provenance_v${iteration}.md
    Source data: ${SOURCE_FILES}
    SAVE findings to: ${ABS_OUTPUT}/synthesis/auditor_v${iteration}.md
    `, { label: `auditor-v${iteration}`, phase: `Synthesize & Review Loop` }),

    () => agent(`Read skills/review-risk-officer/SKILL.md.
    Review: ${ABS_OUTPUT}/${company}_3Y_Report.html
    Provenance report: ${ABS_OUTPUT}/synthesis/provenance_v${iteration}.md
    Source data: ${SOURCE_FILES}
    SAVE findings to: ${ABS_OUTPUT}/synthesis/riskofficer_v${iteration}.md
    `, { label: `riskofficer-v${iteration}`, phase: `Synthesize & Review Loop` }),

    () => agent(`Read skills/review-cfo/SKILL.md.
    Review: ${ABS_OUTPUT}/${company}_3Y_Report.html
    Provenance report: ${ABS_OUTPUT}/synthesis/provenance_v${iteration}.md
    Source data: ${SOURCE_FILES}
    SAVE findings to: ${ABS_OUTPUT}/synthesis/cfo_v${iteration}.md
    `, { label: `cfo-v${iteration}`, phase: `Synthesize & Review Loop` }),

    () => agent(`Read skills/verify-timeliness/SKILL.md — the FULL anti-laziness protocol.
    Execute: For EVERY product recommendation in ${ABS_OUTPUT}/synthesis/report.json (section_1.commercial_opportunities),
    run 4 MANDATORY search queries per recommendation following the Q1-Q4 dimensions defined in the spec.
    Company: ${company}, Fiscal Year: ${Y3}
    Annual report filing cutoff: results must be dated AFTER the annual report publication date.
    SAVE timeliness_check.json, timeliness_llm_raw_response.txt to ${ABS_OUTPUT}/synthesis/.
    Also SAVE findings in review format to: ${ABS_OUTPUT}/synthesis/timeliness_v${iteration}.md

    TIMELINESS FINDINGS FORMAT (one finding per recommendation):
    F-T{n}: [opportunity_title]
    SEVERITY: [HIGH|MEDIUM|LOW]
    Verdict: [EXPIRED|NEEDS_UPDATE|UNCERTAIN|VALID]
    Finding: [one-paragraph evidence summary with source citations]
    Fix instruction: [DELETE|REWRITE|FOOTNOTE|NONE — concrete action for surgical fix]
    Source: [URL, date]
    `, { label: `timeliness-v${iteration}`, phase: `Synthesize & Review Loop` })
  ]);

  // -- Stage 2+3: Cross-Examination + Chair Synthesis --
  await agent(`Read skills/synthesize-review/SKILL.md Stage 2 and Stage 3 sections.

  === FOUR PERSPECTIVE FINDINGS ===
  TIMELINESS: ${ABS_OUTPUT}/synthesis/timeliness_v${iteration}.md
  AUDITOR: ${ABS_OUTPUT}/synthesis/auditor_v${iteration}.md
  RISK OFFICER: ${ABS_OUTPUT}/synthesis/riskofficer_v${iteration}.md
  CFO: ${ABS_OUTPUT}/synthesis/cfo_v${iteration}.md

  === PROVENANCE REPORT ===
  ${ABS_OUTPUT}/synthesis/provenance_v${iteration}.md

  Stage 2: Cross-examine. Each perspective's findings reviewed against the other two. Respond AGREE/DISAGREE with evidence.
  Provenance flags AGREED by >=2 perspectives -> promote to HIGH severity.

  Stage 3: Chair synthesis. Deduplicate across all three perspectives. Assign final severity. Calculate score.

  Score formula: max(0, 100 - 20*HIGH - 5*MED - 1*LOW)

  SAVE review report to: ${ABS_OUTPUT}/${company}_3Y_Review.md
  Also save to: ${ABS_OUTPUT}/synthesis/review_v${iteration}.md

  IMPORTANT: For each finding (HIGH and MEDIUM), include a **fix instruction** with:
  - The exact text to find in the HTML (old_string)
  - The replacement text (new_string)
  - This enables automated surgical application in the fix phase.
  `, { label: `cross-exam-v${iteration}`, phase: `Synthesize & Review Loop` });

  // -- Parse score --
  log(`Review v${iteration} complete. Extracting score...`);

  const reviewOutput = await agent(
    `Read ${ABS_OUTPUT}/${company}_3Y_Review.md.
     Extract ONLY the final numeric score (0-100). Output just the number.`,
    { label: 'extract-score', phase: `Synthesize & Review Loop` }
  );

  const parsedScore = parseInt(reviewOutput);
  if (!isNaN(parsedScore)) {
    score = parsedScore;
  } else {
    score = 0;
  }

  log(`Quality Score: ${score}/100 (threshold: ${QUALITY_THRESHOLD})`);

  if (score >= QUALITY_THRESHOLD) {
    log(`PASSED -- score ${score} >= ${QUALITY_THRESHOLD}. Delivering.`);
    break;
  }

  // ==================================================================
  // SURGICAL FIX (DD16): Read review findings, apply targeted edits to HTML.
  // Do NOT re-synthesize. Each finding → one Edit(old_string, new_string).
  // ==================================================================
  iteration++;
  if (iteration <= MAX_FIX_ITERATIONS) {
    phase(`Surgical Fix v${iteration}`);

    log(`Score ${score} < ${QUALITY_THRESHOLD}. Applying surgical fixes (DD16)...`);

    await agent(`SURGICAL FIX — Apply targeted edits to ${ABS_OUTPUT}/${company}_3Y_Report.html.

  Read the review report at ${ABS_OUTPUT}/${company}_3Y_Review.md (Section 3.2 Final Findings).
  For each HIGH and MEDIUM finding, read the surrounding context in ${ABS_OUTPUT}/${company}_3Y_Report.html.

  Apply ONE Edit tool call per finding. Change ONLY the specific sentences/paragraphs/numbers
  flagged by the review. Do NOT rewrite the entire report. Do NOT touch sections without findings.

  Rules:
  - Each Edit must be a minimal, targeted change — one finding = one edit.
  - Preserve all surrounding content exactly as-is.
  - Process HIGH findings first, then MEDIUM, then LOW if time permits.
  If any finding is marked EXPIRED -> DELETE: remove the entire recommendation card from the HTML. Do not rephrase. Do not downgrade. The opportunity no longer exists.
  - After all edits, verify the HTML is still valid (no broken tags).

  This is a surgical procedure, not a rewrite. The goal is to fix the 4-9 specific issues
  identified in the review, preserving all the correctly-written content.`,
    { label: `surgical-fix-v${iteration}`, phase: `Synthesize & Review Loop` });

    log(`Surgical fix v${iteration} applied.`);
  } else {
    log(`MAX ITERATIONS REACHED -- score ${score} < ${QUALITY_THRESHOLD}. Delivering best effort.`);
    break;
  }
}

// -- Final deliverables already at version root from synthesize + review steps --
phase('Package');

log(`Deliverables at ${ABS_OUTPUT}/:`);
log(`  * ${ABS_OUTPUT}/${company}_3Y_Report.html`);
log(`  * ${ABS_OUTPUT}/${company}_3Y_Review.md`);
log(`  _run.json, cross_year/, Y${Y1}/, Y${Y2}/, Y${Y3}/`);

// ==================================================================
// Pipeline Complete
// ==================================================================
log('=======================================');
log(`Multi-Year Pipeline Complete: ${company} (${Y1}-${Y3})`);
log(`Version: ${VERSION}`);
log(`Quality Score: ${score}/100 (target: ${QUALITY_THRESHOLD})`);
log(`Fix iterations: ${iteration}`);
log(`Report: ${ABS_OUTPUT}/${company}_3Y_Report.html`);
log(`Review: ${ABS_OUTPUT}/${company}_3Y_Review.md`);
if (score >= QUALITY_THRESHOLD) log('[OK] DELIVERED');
else log('[!!]  DELIVERED WITH CAVEATS -- review findings attached');
log('=======================================');

return {
  company,
  years: [Y1, Y2, Y3],
  version: VERSION,
  score,
  iterations: iteration,
  output: `${ABS_OUTPUT}/${company}_3Y_Report.html`,
  status: score >= QUALITY_THRESHOLD ? 'delivered' : 'delivered_with_caveats',
};
