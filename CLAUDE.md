# SSO Calculation Service

A Python service that calculates Thai Social Security Office (SSO) contributions
(and related tax figures) from a company's payroll Excel export. See
[.claude/skills/sso-calc/SKILL.md](.claude/skills/sso-calc/SKILL.md) for the full
architectural rules — read it before touching this codebase.

Core shape: **read Excel file → calculate → export output → done.** No database,
no CRUD API, no admin UI. Python owns all business logic and number crunching; an
LLM is used at exactly one step (Phase 2) to map ambiguous/Thai column headers to
canonical field names — it never calculates anything or decides a business rule.
Per-company SSO formulas live as one JSON file per company; there is no other
persistence. All money math uses `Decimal`, never `float`.

## 5-phase plan

1. **Foundation** *(we are here)* — project scaffolding, the canonical field
   dictionary, the shared SSO rule config, shared Pydantic models, and the Excel
   Inspector that auto-detects a workbook's real structure.
2. **Column Mapping (LLM step)** — feed the Excel Inspector's masked sample rows
   and group/column metadata to an LLM to map each real column to a canonical
   field name. This is the LLM's only role in the whole system.
3. **Calculation Engine** — per-company JSON formula configs (`configs/<company>.json`)
   driving `Decimal`-based SSO and tax calculations over the canonically-mapped data.
4. **Validation** — compare calculated results against the sample file's
   ground-truth columns (`BASE SSO`, `CAL SSO`, `CHECK`, `BASE TAX`, `TAX`) and
   report discrepancies.
5. **Export & Pipeline** — wire the full read → map → calculate → validate →
   export flow into a single runnable entrypoint that produces the final output
   file.

## Folder layout

```
configs/               # one JSON file per company: configs/<company>.json
canonical_fields.json  # shared canonical-field dictionary (all companies)
sso_rule.json          # the shared 5% SSO contribution rule
models/                # shared Pydantic models (e.g. WorkbookMetadata)
excel_inspector.py     # Phase 1: auto-detects workbook structure, masks PII
tests/                 # pytest suite, runs against the real sample file
```

## Current status — Phase 1: Foundation

- [x] Project scaffolding (`configs/`, `models/`, `tests/` folders)
- [ ] `canonical_fields.json` — canonical field dictionary
- [ ] `sso_rule.json` — 5% SSO rule definition
- [ ] `models/` — shared Pydantic models
- [x] `excel_inspector.py` — Excel Inspector (auto-detects header row, groups
      columns, masks PII, separates ground-truth columns, returns
      `WorkbookMetadata`)

Sample file for development/testing: [Upload_Excel.xlsx](Upload_Excel.xlsx)
(repo root). Never assume its structure — always verify by reading it directly
(see `excel_inspector.py` and `tests/`).
