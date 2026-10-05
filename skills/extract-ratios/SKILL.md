# extract-ratios — Shadow Extraction Agent (English)

## Role

Extract the raw financial line items needed by the UCI-aligned ratio
calculator from a company's tagged annual-report text
(`output/{Company}/{version}/Y{yyyy}/tagged/finance.md`). Output is a
JSON superset of statement line items with page citations. You extract
values exactly as printed; you never calculate, estimate, or derive
values (the calculator performs derivation).

## Input

- File: `output/{Company}/{version}/Y{yyyy}/tagged/finance.md`
- Target fiscal year: specified in the task

## Language and unit handling

- Reports may be in Chinese, English, or mixed. Match line items by
  statement position, section heading meaning, and standard IFRS /
  CN-GAAP terminology as described in English below.
- Record the original printed label (in its source language) in the
  optional `source_label` field of each line item.
- Preserve the value, sign, and unit exactly as printed. If a statement
  uses thousands (e.g., thousands-of-CNY or ten-thousands-of-CNY units) or millions, record the unit and keep
  values consistent within the file.

## Line item definitions (canonical key set)

| Key | Definition |
|-----|------------|
| `revenue` | Operating revenue / net sales (top line of the income statement) |
| `revenue_prior_year` | Same revenue line, prior-year comparative column |
| `cogs` | Cost of products sold / operating cost |
| `taxes_surcharges` | Taxes and surcharges |
| `selling_expense` | Selling expenses |
| `admin_expense` | Administrative expenses |
| `rnd_expense` | Research and development expenses |
| `finance_expense` | Finance expenses; sign as printed (can be negative) |
| `interest_expense` | Interest expense component of finance expenses |
| `interest_income` | Interest income component of finance expenses |
| `operating_profit` | Profit on operating activities |
| `total_profit` | Total profit before tax |
| `income_tax_expense` | Income tax expense |
| `net_profit` | Net profit attributable to the consolidated group (profit for the year) |
| `total_assets` | Total assets |
| `current_assets` | Total current assets |
| `fixed_assets` | Fixed assets |
| `total_liabilities` | Total liabilities |
| `current_liabilities` | Total current / short-term liabilities |
| `long_term_liabilities` | Total non-current / long-term liabilities |
| `equity` | Total shareholders' equity (including minority interest) |
| `share_capital` | Share capital |
| `surplus_reserve` | Surplus reserve |
| `undistributed_profit` | Undistributed profit |
| `cash` | Cash and bank balances |
| `trading_financial_assets` | Trading / fair-value financial assets |
| `receivables` | Trade receivables; EXCLUDE contract assets, other receivables, prepayments, long-term receivables, and receivables financing |
| `inventory` | Inventories |
| `accounts_payable` | Trade payables; EXCLUDE notes payable, other payables, and long-term payables |
| `operating_cash_flow` | Net cash from operating activities |
| `capex` | Cash paid for fixed assets, intangibles, and other long-term assets |
| `depreciation_fixed` | Depreciation of fixed assets |
| `depreciation_right_of_use` | Depreciation of right-of-use assets |
| `depreciation_investment_property` | Depreciation of investment property |
| `amortization_intangible` | Amortization of intangibles |
| `amortization_long_term_deferred` | Amortization of long-term deferred expenses |

Derived keys (computed later by `tools/ratio_extractor.py`, not by you):
gross profit, operating expenses, retained earnings, cash and
short-term investments, working capital, constant capital,
depreciation, and EBIT.

## CRITICAL rules

1. Consolidated statements only, not parent-company statements.
2. `receivables` = trade receivables only. Exclude contract assets, other
   receivables, prepayments, long-term receivables, and receivables
   financing.
3. Extract the value exactly as printed; preserve its sign and unit.
4. If a line item is not found, OMIT it from `line_items`. Never
   zero-fill, never substitute a different period, never use external
   knowledge.
5. If values appear with different units (e.g., thousands vs millions),
   normalize to the statement unit and record `unit`.
6. Every line item MUST carry the page number of its source. Page
   markers appear in the tagged text as `--- Page N [text] ---`; scan
   backwards from the value to the nearest marker and record `N`. If no
   marker can be determined, set `page: null`.

## Output schema

Write to `output/{Company}/{version}/Y{yyyy}/ratios/raw_line_items.json`:

```json
{
  "company": "DemoEV",
  "version": "v1",
  "fiscal_year": 2025,
  "currency": "CNY",
  "unit": "thousands",
  "source": "output/DemoEV/v1/Y2025/tagged/finance.md",
  "extracted_by": "extract-ratios agent",
  "line_items": [
    {"name": "revenue", "value": 803964958.0, "page": 126, "source_label": "Operating revenue (as printed)"},
    {"name": "cogs", "value": 661305161.0, "page": 126, "source_label": "Cost of sales (as printed)"}
  ]
}
```

## Self-check list (before finishing)

- [ ] All items are from the target fiscal year (comparative column only
      for `revenue_prior_year`).
- [ ] `receivables`, `inventory`, `cash`, `equity`, `total_assets`,
      `total_liabilities` match the balance sheet section.
- [ ] Every item has a page citation or an explicit `null`.
- [ ] No item was calculated, zero-filled, or taken from another period.
- [ ] Balance sheet + income statement + cash flow items are all present
      where the statements contain them.

## Output files

- `output/{Company}/{version}/Y{yyyy}/ratios/raw_line_items.json` — extracted values
- `output/{Company}/{version}/Y{yyyy}/ratios/parse_log.md` — extraction notes,
  unit used, and any items omitted with reasons


