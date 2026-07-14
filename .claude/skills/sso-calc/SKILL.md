---
name: sso-calc
description: Durable architecture rules for the Thai SSO (social security) calculation service. Load this before writing or reviewing any code in this project.
---

# SSO Calculation Service — Project Conventions

This project computes Thai Social Security Office (SSO) contributions from payroll
Excel exports. These rules are architectural constraints, not suggestions — any
change that violates them needs to be raised with the user explicitly, not silently
worked around.

## 1. Python owns the entire workflow

Python is responsible for **all** business logic, **all** number crunching, and
**all** control flow: reading the Excel file, applying SSO formulas, validating
results against ground truth, and exporting output. There is no step where an LLM
calculates a number, applies a business rule, or decides an outcome.

## 2. The LLM's role is exactly one step: column-name mapping

The LLM is invoked at exactly one point in the pipeline: interpreting the real
(often Thai, often ambiguous) column headers found in a customer's Excel file and
mapping them to canonical field names defined in `canonical_fields.json`. That's it.

- The LLM never sees full data — only masked sample rows for context.
- The LLM never computes a value, never applies the 5% SSO rule, never decides a
  business rule, and never has a role anywhere else in the pipeline.
- If a future task proposes using the LLM for anything else (validation, decisions,
  calculations, edge-case handling), stop and flag it — that's a deviation from this
  architecture and needs explicit user sign-off.

## 3. No database, no CRUD API, no admin UI

The system's entire shape is: **read Excel file → calculate → export output → done.**
Nothing is persisted at runtime. Don't introduce a database, an ORM, REST/CRUD
endpoints, or any kind of admin UI — none of that is in scope, ever, unless the user
explicitly changes the architecture.

The only persistent artifacts are per-company config files on disk:

- `configs/<company>.json` — one JSON file per company encoding that company's
  specific SSO formula/quirks.
- `canonical_fields.json` — the shared dictionary of canonical field names, shared
  across all companies.
- `sso_rule.json` — the shared 5% SSO contribution rule (rate, ceiling, floor, etc.).

Adding a new company means adding a new JSON config file — not a database row.

## 4. Money math uses `Decimal`, never `float`

Every SSO/salary/contribution calculation must use Python's `decimal.Decimal`.
Never use `float` for money — floating-point rounding errors are unacceptable when
the output is compared against ground-truth columns (`BASE SSO`, `CAL SSO`, `CHECK`,
`BASE TAX`, `TAX`) and ultimately affects real employee withholding.

- Construct `Decimal` from strings or ints, never from a `float` literal
  (`Decimal("1234.56")`, not `Decimal(1234.56)`).
- Rounding must use explicit `Decimal.quantize()` with a defined rounding mode
  (e.g. `ROUND_HALF_UP`), matching whatever convention SSO/payroll rounding uses —
  don't rely on implicit rounding.

## 5. Never guess column names — always open the real Excel file first

Customer Excel exports are inconsistent: merged group headers, Thai column names,
near-duplicate names distinguished only by their group (e.g. `ชดเชยวันลา (บาท)` under
the income group vs `หักชดเชยวันลา (บาท)` under the deduction group `รายหัก`). Never
hardcode assumed column names, header row indices, or column counts.

- Before writing or modifying any code that parses a workbook, open the actual
  sample/customer file and inspect its real structure (sheet names, header row,
  group headers, column names, row count).
- Header row position, group headers, and column order are not assumed to be
  stable across files — auto-detect them (see `excel_inspector.py`).
- When in doubt about what a column means, that's precisely the ambiguity the LLM
  mapping step (§2) exists to resolve — don't guess in Python, and don't hardcode a
  guess either.

## 6. PII must be masked before anything leaves Python's calculation boundary

Employee personal data — full name (`ชื่อ-นามสกุล`), bank account number
(`เลขบัญชี`), bank name (`บัญชีธนาคาร`), and any other directly identifying columns —
must never be exposed in:

- Sample rows produced for the LLM mapping step.
- Logs, error messages, or debug output.
- Any intermediate artifact that isn't the final calculated export the user asked for.

Mask PII columns before they leave the trusted boundary (e.g. redact/replace with a
placeholder such as `"<masked>"` or a truncated hash) — never pass raw PII values
into an LLM prompt or a non-essential output.

## Ground-truth columns are read-only references, not inputs

Sample files may already contain expected-answer columns (`BASE SSO`, `CAL SSO`,
`CHECK`, `BASE TAX`, `TAX`). These exist for testing/validation — to confirm the
Python calculation matches the known-correct answer. They are never treated as
input to the calculation, and they must be kept structurally separate from the
input column list (see `WorkbookMetadata.ground_truth` in `excel_inspector.py`).
