"""Talks to the LLM Gateway's OpenAI-compatible Responses API for exactly one
job: mapping real Excel column names to canonical field keys (see
.claude/skills/sso-calc/SKILL.md, rule 2). The LLM never calculates a value or
decides a business rule — this client only moves data across the wire.

Column names and group headers are the only things sent; no sample cell
values ever leave the process, so there is no PII to mask here.
"""

import json
import os
from typing import Any, Optional

from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI

DEFAULT_MODEL = "openai/gpt-4.1-mini"
DEFAULT_TIMEOUT_SECONDS = 60.0

COLUMN_MAPPING_INSTRUCTIONS = """\
You are a column-mapping assistant for a Thai payroll SSO (Social Security Office) \
calculation system.

You will receive a JSON payload with two lists:
1. "columns": the real columns found in a customer's Excel payroll export. Each has an
   "index" (1-based position in the sheet), a "group" (the merged header above it, or
   null), and a "name" (the literal Thai/English column header text).
2. "canonical_fields": the fixed dictionary of canonical field keys this system
   understands. Each has a "key" (the canonical identifier), "aliases_th" (known Thai
   names for this field), "expected_group" (the group header this field is normally
   found under, or null if unverified), and "polarity" ("income" or "deduction").

Your job: for every column in "columns", decide which single canonical field it
represents, if any.

Rules:
- Match primarily on the column's "name" against each canonical field's "aliases_th".
  Use "group" to disambiguate when multiple canonical fields have similar or identical
  Thai names.
- Example: a column named "ชดเชยวันลา (บาท)" under group "ชดเชยวันลา" is the canonical
  field "leave_compensation_income" (income side). A column with the very similar name
  "หักชดเชยวันลา (บาท)" under group "ชดเชยวันลา (หัก)" is "deduct_leave_compensation"
  (deduction side) instead — the group header is what disambiguates these two, not the
  name alone.
- If a column's "group" does not match a canonical field's "expected_group" (when that
  canonical field's expected_group is set), be more cautious about proposing that
  mapping.
- If a column does not correspond to any canonical field (e.g. an identifier, a date, a
  subtotal, or something not in the dictionary), map it to null. Do not invent a
  canonical field that isn't in the provided list.
- Each column maps to at most one canonical field. Do not map two different columns to
  the same canonical field unless they are genuinely duplicated in the source.
- When unsure, prefer mapping to null with a low confidence rather than forcing a match
  — a confident wrong mapping is worse than an honest "no match."
- You are only identifying which field a column name represents. You never calculate a
  value, apply the SSO rate, or decide any business rule — that happens entirely outside
  of you.
- For every mapping, include a "confidence" from 0 (no idea) to 1 (certain) reflecting
  how sure you are.
- Respond with only the mapping JSON. No commentary.
"""

COLUMN_MAPPING_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "json_schema",
    "name": "column_mapping_result",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "mappings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "column_index": {"type": "integer"},
                        "column_name": {"type": "string"},
                        "canonical_field": {"type": ["string", "null"]},
                        "confidence": {"type": "number"},
                    },
                    "required": ["column_index", "column_name", "canonical_field", "confidence"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["mappings"],
        "additionalProperties": False,
    },
}


class LlmGatewayError(RuntimeError):
    """Raised when the Gateway call fails. The mapping is FAILED — callers must
    not fabricate a mapping or fall back to guessing."""


def _resolve_sdk_base_url(raw_base_url: str) -> str:
    base = raw_base_url.rstrip("/")
    if not base.endswith("/v1"):
        base += "/v1"
    return base


def build_mapping_payload(
    columns: list[dict[str, Any]],
    canonical_fields: list[dict[str, Any]],
) -> dict[str, Any]:
    """Pure wire-format construction, no I/O — the one place the request shape
    is defined, so it can be unit-tested without a network call."""
    return {"columns": columns, "canonical_fields": canonical_fields}


class LlmGatewayClient:
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
    ) -> None:
        api_key = api_key or os.environ.get("LLM_GATEWAY_API_KEY")
        base_url = base_url or os.environ.get("LLM_GATEWAY_BASE_URL")
        if not api_key or not base_url:
            raise LlmGatewayError(
                "LLM_GATEWAY_API_KEY and LLM_GATEWAY_BASE_URL must both be set"
            )

        self.model = model or os.environ.get("LLM_GATEWAY_MODEL", DEFAULT_MODEL)
        if timeout_seconds is None:
            timeout_seconds = float(
                os.environ.get("LLM_GATEWAY_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS)
            )

        self._client = OpenAI(
            api_key=api_key,
            base_url=_resolve_sdk_base_url(base_url),
            timeout=timeout_seconds,
            max_retries=2,
        )

    def map_columns(
        self,
        columns: list[dict[str, Any]],
        canonical_fields: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Send columns + canonical fields to the Gateway and return the raw
        parsed JSON dict. Raises LlmGatewayError on any Gateway failure — never
        fabricates a mapping."""
        payload = build_mapping_payload(columns, canonical_fields)

        try:
            response = self._client.responses.create(
                model=self.model,
                instructions=COLUMN_MAPPING_INSTRUCTIONS,
                input=json.dumps(payload, ensure_ascii=False),
                text={"format": COLUMN_MAPPING_RESPONSE_SCHEMA},
            )
        except (APITimeoutError, APIConnectionError, APIStatusError) as exc:
            raise LlmGatewayError(f"LLM Gateway call failed: {type(exc).__name__}") from exc

        return json.loads(response.output_text)
