"""Phase 5's Result Builder: turns per-employee Phase 4 calculations into
one company-level result — totals, an audit snapshot of exactly what
produced them, and any rows that couldn't be processed (never silently
dropped).
"""

from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, Field

from models.calculation import ComponentAmount
from models.column_mapping import ColumnMapping, ColumnMappingResult
from models.company_config import CompanyConfig, SsoRule
from services.sso_calculator import calculate_employee


class EmployeeRowResult(BaseModel):
    employee_id: str
    base: Decimal
    contribution: Decimal
    breakdown: list[ComponentAmount]


class ErrorRow(BaseModel):
    row_number: int  # 1-based position among employee data rows, not the raw worksheet row.
    employee_id: Optional[str]
    reason: str


class ColumnMappingUsed(BaseModel):
    canonical_field: str
    column_index: Optional[int]
    column_name: Optional[str]
    sign: Optional[str] = None  # None for employee_id, which isn't a signed formula component.


class AuditSnapshot(BaseModel):
    company_id: str
    display_name: str
    config_version: int
    sso_rate: Decimal
    sso_ceiling: Decimal
    column_mapping: list[ColumnMappingUsed] = Field(default_factory=list)


class CompanyResult(BaseModel):
    employees: list[EmployeeRowResult]
    total_base: Decimal
    total_contribution: Decimal
    error_rows: list[ErrorRow]
    audit: AuditSnapshot


def _resolve_employee_id_mapping(mapping_result: ColumnMappingResult) -> ColumnMapping:
    for m in mapping_result.mappings:
        if m.canonical_field == "employee_id":
            return m
    raise ValueError(
        "no column was mapped to the 'employee_id' canonical field — cannot identify employee rows"
    )


def _build_audit_snapshot(
    company_config: CompanyConfig,
    mapping_result: ColumnMappingResult,
    sso_rule: SsoRule,
    employee_id_mapping: ColumnMapping,
) -> AuditSnapshot:
    field_to_mapping = {
        m.canonical_field: m for m in mapping_result.mappings if m.canonical_field is not None
    }

    column_mapping = [
        ColumnMappingUsed(
            canonical_field="employee_id",
            column_index=employee_id_mapping.column_index,
            column_name=employee_id_mapping.column_name,
        )
    ]
    for component in company_config.components:
        m = field_to_mapping.get(component.key)
        column_mapping.append(
            ColumnMappingUsed(
                canonical_field=component.key,
                column_index=m.column_index if m else None,
                column_name=m.column_name if m else None,
                sign=component.sign,
            )
        )

    return AuditSnapshot(
        company_id=company_config.company_id,
        display_name=company_config.display_name,
        config_version=company_config.version,
        sso_rate=sso_rule.rate,
        sso_ceiling=sso_rule.ceiling,
        column_mapping=column_mapping,
    )


def build_company_result(
    employee_rows: list[dict[int, Any]],
    company_config: CompanyConfig,
    mapping_result: ColumnMappingResult,
    sso_rule: SsoRule,
) -> CompanyResult:
    employee_id_mapping = _resolve_employee_id_mapping(mapping_result)
    employee_id_column = employee_id_mapping.column_index

    employees: list[EmployeeRowResult] = []
    error_rows: list[ErrorRow] = []
    total_base = Decimal("0")
    total_contribution = Decimal("0")

    for position, row in enumerate(employee_rows, start=1):
        raw_employee_id = row.get(employee_id_column)
        employee_id = str(raw_employee_id).strip() if raw_employee_id is not None else ""

        if not employee_id:
            error_rows.append(
                ErrorRow(
                    row_number=position,
                    employee_id=None,
                    reason="employee_id ว่างเปล่าหรือไม่มีข้อมูล",
                )
            )
            continue

        try:
            result = calculate_employee(row, company_config, mapping_result, sso_rule)
        except Exception as exc:
            error_rows.append(
                ErrorRow(row_number=position, employee_id=employee_id, reason=f"คำนวณไม่สำเร็จ: {exc}")
            )
            continue

        employees.append(
            EmployeeRowResult(
                employee_id=employee_id,
                base=result.base,
                contribution=result.contribution,
                breakdown=result.breakdown,
            )
        )
        total_base += result.base
        total_contribution += result.contribution

    audit = _build_audit_snapshot(company_config, mapping_result, sso_rule, employee_id_mapping)

    return CompanyResult(
        employees=employees,
        total_base=total_base,
        total_contribution=total_contribution,
        error_rows=error_rows,
        audit=audit,
    )
