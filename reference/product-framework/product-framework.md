# Wholesale Banking Group — Coverage & Product Framework

> Domain skeleton injected into the **Synthesize & Review** agent at run time (mechanism:
> [knowledge-injection.md](knowledge-injection.md)). Compiled from
> public-information-level banking knowledge only: no specific bank is named, no branded
> products, no portfolio figures. In production this skeleton is instantiated per bank with
> its own policy flags and disclosure facts — that instance stays out of this repository.

## 1. Positioning & client geography

A group wholesale-banking franchise serving corporates, financial institutions and
government-linked entities across **Greater China and ASEAN — 9 markets organised into
4 reference groups** (groups exist because companies in the same group share disclosure
ecosystems and comparable-industry baselines):

| Reference group | Markets | Why grouped |
|---|---|---|
| Greater China | China A-share, Hong Kong | Deep disclosure ecosystem, cross-listing links |
| SEA Manufacturing Export | Thailand, Vietnam | Export-oriented manufacturing, comparable listed-company ecology |
| SEA Regional / Diversified | Singapore, Malaysia | Regional HQ presence + diversified domestic demand |
| Independent | Indonesia, South Korea, Japan | Idiosyncratic cycles, standalone benchmarks |

## 2. Industry coverage (6 verticals + FIG)

**Signal strength** = depth of publicly available disclosure for the sector (dedicated
financing frameworks, sustainability policies, risk disclosure) — it calibrates how deep the
report's industry analysis goes. It does **not** mean whether the bank lends to the sector.

- **HIGH signal** — Construction & Infrastructure, Energy & Chemicals, Real Estate &
  Hospitality (dedicated public financing frameworks exist)
- **MEDIUM signal** — Industrials, Consumer Goods & Healthcare, Telecom/Media/Technology
- **FIG** (financial institutions) as a core client segment

## 3. Product lines (pain point → followable opportunity)

The framework's job is to turn a **disclosed pain point** in the annual report into a
**concrete, followable opportunity** for a relationship manager:

| Client pain point (disclosed) | Product family | Typical trigger events |
|---|---|---|
| Working-capital strain (DSO/DIO/DPO drift) | Regional cash management; receivables / supply-chain finance | Working-capital deterioration, supplier-payment extension |
| Expansion capex / new plant | Project finance; green capex loans | Capacity-exp announcements, land/plant commitments |
| Cross-border supply-chain reconfiguration | Supply-chain finance; cross-border FX hedging | New overseas subsidiaries, shifting production bases |
| Refinancing / interest-rate exposure | DCM, syndicated lending; rates hedging | Bond maturities, floating-rate debt share |
| Sustainability transition | Green / sustainability-linked finance | Decarbonisation capex, transition targets |
| Market entry / M&A | FDI advisory; investment banking | Acquisition announcements, JV formation |

## 4. Financing-policy flags (structure only)

Each bank instantiates its own flag set; the framework reserves slots for:

- **Hard prohibitions** — activities the bank will not finance → any lead touching them
  becomes `NO_GO`;
- **Phase-out timelines** — sector exit horizons and stopped-financing dates → companies in
  these sectors must be flagged for phase-out risk;
- **Eligibility criteria** — what qualifies as green/transition-eligible in that sector.

## 5. Injection contract

- The synthesizer treats **this framework** as authoritative for *what counts as a relevant
  opportunity*; the **annual-report text** remains authoritative for *everything about the
  company*.
- If the injected context is empty, the synthesizer proceeds with the standard report and
  skips opportunity matching.
