import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from openai import APIConnectionError, APIStatusError, APITimeoutError

from excel_inspector import inspect_workbook
from integrations.llm_gateway_client import (
    LlmGatewayClient,
    LlmGatewayError,
    build_mapping_payload,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SAMPLE_FILE = PROJECT_ROOT / "Upload_Excel.xlsx"
CANONICAL_FIELDS_PATH = PROJECT_ROOT / "canonical_fields.json"


def _canonical_fields_payload_items():
    with open(CANONICAL_FIELDS_PATH, encoding="utf-8") as f:
        data = json.load(f)
    return [
        {
            "key": field["key"],
            "aliases_th": field["aliases_th"],
            "expected_group": field["expected_group"],
            "polarity": field["polarity"],
        }
        for field in data["fields"]
    ]


def _columns_payload_items(columns):
    return [{"index": c.index, "group": c.group, "name": c.name} for c in columns]


def test_payload_shape_from_real_domnick_columns():
    metadata = inspect_workbook(str(SAMPLE_FILE))
    columns = _columns_payload_items(metadata.columns)
    canonical_fields = _canonical_fields_payload_items()

    payload = build_mapping_payload(columns, canonical_fields)

    assert set(payload.keys()) == {"columns", "canonical_fields"}
    assert payload["columns"] == columns
    assert payload["canonical_fields"] == canonical_fields

    for column in payload["columns"]:
        assert set(column.keys()) == {"index", "group", "name"}
    for field in payload["canonical_fields"]:
        assert set(field.keys()) == {"key", "aliases_th", "expected_group", "polarity"}

    income_leave = next(c for c in payload["columns"] if c["name"] == "ชดเชยวันลา (บาท)")
    deduct_leave = next(c for c in payload["columns"] if c["name"] == "หักชดเชยวันลา (บาท)")
    assert income_leave["group"] == "ชดเชยวันลา"
    assert deduct_leave["group"] == "ชดเชยวันลา (หัก)"
    assert income_leave["group"] != deduct_leave["group"]

    payload_str = json.dumps(payload, ensure_ascii=False)
    assert "<masked>" not in payload_str


def _mock_openai_client(fake_output_text):
    fake_response = MagicMock()
    fake_response.output_text = fake_output_text
    mock_client_instance = MagicMock()
    mock_client_instance.responses.create.return_value = fake_response
    return mock_client_instance


def test_map_columns_parses_gateway_response_without_network():
    canned = {
        "mappings": [
            {
                "column_index": 21,
                "column_name": "เงินเดือนต่องวด",
                "canonical_field": "salary_per_period",
                "confidence": 0.98,
            }
        ]
    }

    with patch("integrations.llm_gateway_client.OpenAI") as mock_openai_cls:
        mock_client_instance = _mock_openai_client(json.dumps(canned, ensure_ascii=False))
        mock_openai_cls.return_value = mock_client_instance

        client = LlmGatewayClient(api_key="test-key", base_url="https://gateway.example.com")
        result = client.map_columns(
            columns=[{"index": 21, "group": "เงินเดือน", "name": "เงินเดือนต่องวด"}],
            canonical_fields=[
                {
                    "key": "salary_per_period",
                    "aliases_th": ["เงินเดือนต่องวด"],
                    "expected_group": "เงินเดือน",
                    "polarity": "income",
                }
            ],
        )

    assert result == canned

    _, init_kwargs = mock_openai_cls.call_args
    assert init_kwargs["base_url"] == "https://gateway.example.com/v1"

    mock_client_instance.responses.create.assert_called_once()
    _, kwargs = mock_client_instance.responses.create.call_args
    assert kwargs["text"]["format"]["strict"] is True
    assert kwargs["text"]["format"]["name"] == "column_mapping_result"
    sent_payload = json.loads(kwargs["input"])
    assert sent_payload["columns"][0]["index"] == 21


@pytest.mark.parametrize(
    "exc",
    [
        APITimeoutError(request=MagicMock()),
        APIConnectionError(request=MagicMock()),
        APIStatusError("boom", response=MagicMock(status_code=503, headers={}), body=None),
    ],
)
def test_map_columns_raises_gateway_error_on_failure_without_fabricating(exc):
    with patch("integrations.llm_gateway_client.OpenAI") as mock_openai_cls:
        mock_client_instance = MagicMock()
        mock_client_instance.responses.create.side_effect = exc
        mock_openai_cls.return_value = mock_client_instance

        client = LlmGatewayClient(api_key="test-key", base_url="https://gateway.example.com")

        with pytest.raises(LlmGatewayError):
            client.map_columns(columns=[], canonical_fields=[])


def test_client_requires_credentials(monkeypatch):
    monkeypatch.delenv("LLM_GATEWAY_API_KEY", raising=False)
    monkeypatch.delenv("LLM_GATEWAY_BASE_URL", raising=False)
    with pytest.raises(LlmGatewayError):
        LlmGatewayClient(api_key=None, base_url=None)
