"""Live smoke test against the real LLM Gateway. Skipped by default so the
normal suite never touches the network — only runs when real Gateway
credentials are present in the environment (via .env or the shell), not the
.env.example placeholders.

Run just this file, verbose, with output capturing off so the printed mapping
table is visible:

    pytest tests/test_llm_gateway_integration.py -v -s
"""

import json
import os
from pathlib import Path

import pytest

from integrations.llm_gateway_client import LlmGatewayClient
from models import validate_column_mapping_response

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CANONICAL_FIELDS_PATH = PROJECT_ROOT / "canonical_fields.json"

# Must match .env.example exactly — an unfilled .env has these values, not
# real credentials, and should still be treated as "not configured."
_PLACEHOLDER_API_KEY = "sk-..."
_PLACEHOLDER_BASE_URL = "https://..."


def _looks_configured(value, placeholder):
    return bool(value) and value != placeholder


pytestmark = pytest.mark.skipif(
    not (
        _looks_configured(os.environ.get("LLM_GATEWAY_API_KEY"), _PLACEHOLDER_API_KEY)
        and _looks_configured(os.environ.get("LLM_GATEWAY_BASE_URL"), _PLACEHOLDER_BASE_URL)
    ),
    reason="requires real LLM_GATEWAY_API_KEY and LLM_GATEWAY_BASE_URL (fill in .env, not the placeholders)",
)


def test_gateway_maps_the_unambiguous_salary_column():
    with open(CANONICAL_FIELDS_PATH, encoding="utf-8") as f:
        data = json.load(f)
    fields_by_key = {field["key"]: field for field in data["fields"]}

    canonical_fields = [
        {
            "key": key,
            "aliases_th": fields_by_key[key]["aliases_th"],
            "expected_group": fields_by_key[key]["expected_group"],
            "polarity": fields_by_key[key]["polarity"],
        }
        for key in ("salary_per_period", "leave_compensation_income", "deduct_leave_compensation")
    ]
    columns = [
        {"index": 21, "group": "เงินเดือน", "name": "เงินเดือนต่องวด"},
        {"index": 35, "group": "ชดเชยวันลา", "name": "ชดเชยวันลา (บาท)"},
        {"index": 69, "group": "ชดเชยวันลา (หัก)", "name": "หักชดเชยวันลา (บาท)"},
    ]

    client = LlmGatewayClient()
    raw = client.map_columns(columns, canonical_fields)

    result = validate_column_mapping_response(
        raw,
        valid_column_indexes={c["index"] for c in columns},
        canonical_keys={f["key"] for f in canonical_fields},
    )

    print("\ncolumn_index  column_name                    canonical_field              confidence")
    for mapping in result.mappings:
        print(
            f"{mapping.column_index:<13} {mapping.column_name:<30} "
            f"{str(mapping.canonical_field):<28} {mapping.confidence}"
        )
    if result.unmapped_fields:
        print("unmapped_fields:", result.unmapped_fields)

    assert len(result.mappings) == 3
    salary_mapping = next(m for m in result.mappings if m.column_index == 21)
    assert salary_mapping.canonical_field == "salary_per_period"

    income_leave = next(m for m in result.mappings if m.column_index == 35)
    deduct_leave = next(m for m in result.mappings if m.column_index == 69)
    print(
        f"\nชดเชยวันลา (income, idx 35) -> {income_leave.canonical_field}\n"
        f"หักชดเชยวันลา (deduct, idx 69) -> {deduct_leave.canonical_field}"
    )
