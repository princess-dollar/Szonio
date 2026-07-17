from decimal import Decimal

from models.column_mapping import ColumnMapping, ColumnMappingResult
from models.company_config import Component, CompanyConfig, SsoRule
from services.result_builder import build_company_result

_CONFIG = CompanyConfig(
    company_id="synthetic",
    display_name="Synthetic",
    version=1,
    components=[
        Component(key="salary_per_period", sign="+", required=True),
    ],
)

_MAPPING = ColumnMappingResult(
    mappings=[
        ColumnMapping(column_index=1, column_name="employee code", canonical_field="employee_id", confidence=0.99),
        ColumnMapping(column_index=2, column_name="salary", canonical_field="salary_per_period", confidence=0.99),
    ]
)

_SSO_RULE = SsoRule(rate=Decimal("0.05"), ceiling=Decimal("17500"))


def test_blank_employee_id_becomes_an_error_row_not_a_crash():
    employee_rows = [
        {1: "E001", 2: 10000},
        {1: None, 2: 5000},  # blank employee_id
        {1: "E003", 2: 20000},
    ]

    result = build_company_result(employee_rows, _CONFIG, _MAPPING, _SSO_RULE)

    assert len(result.employees) == 2
    assert {e.employee_id for e in result.employees} == {"E001", "E003"}

    assert len(result.error_rows) == 1
    error = result.error_rows[0]
    assert error.row_number == 2
    assert error.employee_id is None
    assert "employee_id" in error.reason


def test_blank_employee_id_row_does_not_corrupt_totals():
    employee_rows = [
        {1: "E001", 2: 10000},
        {1: "", 2: 999999},  # blank (empty string) employee_id, would badly skew totals if included
        {1: "E003", 2: 20000},
    ]

    result = build_company_result(employee_rows, _CONFIG, _MAPPING, _SSO_RULE)

    assert len(result.error_rows) == 1
    expected_total_base = Decimal("10000") + Decimal("20000")
    assert result.total_base == expected_total_base
    assert result.total_contribution == sum((e.contribution for e in result.employees), Decimal("0"))


def test_audit_snapshot_names_the_mapping_and_config_used():
    employee_rows = [{1: "E001", 2: 10000}]

    result = build_company_result(employee_rows, _CONFIG, _MAPPING, _SSO_RULE)

    assert result.audit.company_id == "synthetic"
    assert result.audit.config_version == 1
    assert result.audit.sso_rate == Decimal("0.05")
    assert result.audit.sso_ceiling == Decimal("17500")

    by_field = {item.canonical_field: item for item in result.audit.column_mapping}
    assert by_field["employee_id"].column_index == 1
    assert by_field["salary_per_period"].column_index == 2
    assert by_field["salary_per_period"].sign == "+"
