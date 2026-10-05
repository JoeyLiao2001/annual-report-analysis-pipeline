# Wholesale Banking Context Injection — Prompt Modification

> V2.5 | Report_Synthesizer system prompt | 2026-06-15

## Change

Inserted a new section `# Wholesale Banking Lending Context (from Knowledge Base)` into the Report_Synthesizer system prompt, between the Role description and the Formatting Rules section.

## Injected Text

```
# Wholesale Banking Lending Context (from Knowledge Base)

{{#KNOWLEDGE_RETRIEVAL_NODE.text#}}

Use the above bank context to:
- Calibrate industry analysis depth based on signal strength (High/Medium/Low)
- Reference relevant ASEAN corridors when discussing cross-border opportunities
- Map client pain points to specific bank product names from the context
- Flag any risk prohibitions that apply to the company's industry

If the Wholesale Banking Context above is empty (no relevant knowledge found), ignore this section entirely and proceed with the standard report.
```

## Setup Required

1. Upload the bank-specific product framework dossier (compiled from the bank's public disclosures; redacted in this repo — see `reference/product-framework/README.md`) to the Dify knowledge base
2. In Dify workflow editor, add a **Knowledge Retrieval** node:
   - Connect: Semantic_Router (1779112353466) → Knowledge Retrieval → Report_Synthesizer (1779091976804)
   - Query variable: `{{#1779112353466.text#}}`
   - Top K: 3
   - Knowledge Base: the uploaded EN file
3. In Report_Synthesizer prompt, replace `KNOWLEDGE_RETRIEVAL_NODE` with the actual node ID from step 2
