from decimal import Decimal
from pathlib import Path

from excel_inspector import read_employee_rows
from services.orchestrator import process_file

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SAMPLE_FILE = PROJECT_ROOT / "Upload_Excel.xlsx"

# Real columns from Upload_Excel.xlsx: index 1 -> employee_id, index 21 ->
# salary_per_period, index 64 -> deduct_unpaid_leave, index 61 -> deduct_late_early.
# Domnick's real formula (configs/domnick.json): +salary_per_period
# -deduct_unpaid_leave -deduct_late_early.


class _StubLlmClient:
    """Stands in for integrations.llm_gateway_client.LlmGatewayClient — no
    network, no LLM call, in any test."""

    def __init__(self, raw_response):
        self._raw_response = raw_response
        self.call_count = 0

    def map_columns(self, columns, canonical_fields):
        self.call_count += 1
        return self._raw_response


def _domnick_full_raw_mapping():
    return {
        "mappings": [
            {
                "column_index": 1,
                "column_name": "รหัสพนักงาน",
                "canonical_field": "employee_id",
                "confidence": 0.99,
            },
            {
                "column_index": 21,
                "column_name": "เงินเดือนต่องวด",
                "canonical_field": "salary_per_period",
                "confidence": 0.97,
            },
            {
                "column_index": 64,
                "column_name": "หักลาไม่รับค่าจ้าง (บาท)",
                "canonical_field": "deduct_unpaid_leave",
                "confidence": 0.95,
            },
            {
                "column_index": 61,
                "column_name": "หักมาสาย/กลับก่อน (บาท)",
                "canonical_field": "deduct_late_early",
                "confidence": 0.93,
            },
        ]
    }


def test_pipeline_flows_end_to_end_with_mocked_gateway():
    client = _StubLlmClient(_domnick_full_raw_mapping())

    result = process_file(str(SAMPLE_FILE), "domnick", llm_client=client)

    assert client.call_count == 1
    assert result.status == "calculated"
    company_result = result.company_result
    assert company_result is not None
    assert result.review_report_th is None

    # 33 real employees, trailing Total row excluded (see test_excel_inspector.py).
    assert len(company_result.employees) == 33
    assert company_result.error_rows == []

    for employee in company_result.employees:
        assert employee.base >= Decimal("0")
        assert employee.contribution >= Decimal("0")
        assert employee.contribution <= Decimal("875.00")  # ceiling 17500 * rate 0.05

    assert company_result.total_contribution == sum(
        (e.contribution for e in company_result.employees), Decimal("0")
    )
    assert company_result.total_base == sum((e.base for e in company_result.employees), Decimal("0"))


def test_pipeline_stops_at_needs_review_and_does_not_calculate():
    raw = _domnick_full_raw_mapping()
    raw["mappings"] = [m for m in raw["mappings"] if m["canonical_field"] != "salary_per_period"]
    client = _StubLlmClient(raw)

    result = process_file(str(SAMPLE_FILE), "domnick", llm_client=client)

    assert result.status == "needs_review"
    assert result.company_result is None
    assert result.review_report_th is not None
    assert "REQUIRED_FIELD_UNMAPPED" in result.review_report_th
    assert "salary_per_period" in result.review_report_th


def test_pipeline_stops_at_needs_review_for_low_confidence():
    raw = _domnick_full_raw_mapping()
    for m in raw["mappings"]:
        if m["canonical_field"] == "deduct_unpaid_leave":
            m["confidence"] = 0.3  # below the 0.80 default threshold
    client = _StubLlmClient(raw)

    result = process_file(str(SAMPLE_FILE), "domnick", llm_client=client)

    assert result.status == "needs_review"
    assert result.company_result is None
    assert "LOW_CONFIDENCE" in result.review_report_th


def test_trailing_total_row_excluded_from_employee_rows():
    rows = read_employee_rows(str(SAMPLE_FILE))
    assert len(rows) == 33
    employee_ids = {row[1] for row in rows}
    assert "Total" not in employee_ids
    assert "รวม" not in employee_ids
