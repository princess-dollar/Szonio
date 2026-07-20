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


# --- employee_name (identity field, optional) -----------------------------

_MAPPING_WITH_NAME = ColumnMappingResult(
    mappings=[
        ColumnMapping(column_index=1, column_name="employee code", canonical_field="employee_id", confidence=0.99),
        ColumnMapping(column_index=3, column_name="ชื่อ-นามสกุล", canonical_field="employee_name", confidence=0.97),
        ColumnMapping(column_index=2, column_name="salary", canonical_field="salary_per_period", confidence=0.99),
    ]
)


def test_employee_name_flows_through_when_mapped():
    employee_rows = [
        {1: "E001", 2: 10000, 3: "สมชาย ใจดี"},
        {1: "E002", 2: 20000, 3: "  สมหญิง รักงาน  "},  # surrounding whitespace trimmed
    ]

    result = build_company_result(employee_rows, _CONFIG, _MAPPING_WITH_NAME, _SSO_RULE)

    assert [e.employee_name for e in result.employees] == ["สมชาย ใจดี", "สมหญิง รักงาน"]
    # Identity field appears in the audit with no formula sign.
    by_field = {item.canonical_field: item for item in result.audit.column_mapping}
    assert by_field["employee_name"].column_index == 3
    assert by_field["employee_name"].sign is None


def test_employee_name_is_none_when_not_mapped_and_numbers_unaffected():
    employee_rows = [{1: "E001", 2: 10000}, {1: "E002", 2: 20000}]

    with_name = build_company_result(employee_rows, _CONFIG, _MAPPING_WITH_NAME, _SSO_RULE)
    without_name = build_company_result(employee_rows, _CONFIG, _MAPPING, _SSO_RULE)

    # No name column mapped -> every name is None, no crash.
    assert all(e.employee_name is None for e in without_name.employees)
    # ...and the money is identical whether or not names were resolved.
    assert without_name.total_base == with_name.total_base
    assert without_name.total_contribution == with_name.total_contribution


def test_blank_name_cell_becomes_none():
    employee_rows = [{1: "E001", 2: 10000, 3: "   "}, {1: "E002", 2: 20000, 3: None}]

    result = build_company_result(employee_rows, _CONFIG, _MAPPING_WITH_NAME, _SSO_RULE)

    assert all(e.employee_name is None for e in result.employees)
