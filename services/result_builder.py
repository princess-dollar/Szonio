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
    employee_name: Optional[str] = None  # identity metadata; read by Python only, never sent to the LLM.
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


def _find_mapping(mapping_result: ColumnMappingResult, key: str) -> Optional[ColumnMapping]:
    for m in mapping_result.mappings:
        if m.canonical_field == key:
            return m
    return None


def _read_text_cell(row: dict[int, Any], column_index: Optional[int]) -> Optional[str]:
    """Read a cell as trimmed text, or None if unmapped/blank. Used for
    identity fields (employee_id, employee_name) — never summed, only shown."""
    if column_index is None:
        return None
    raw = row.get(column_index)
    if raw is None:
        return None
    text = str(raw).strip()
    return text or None


def _build_audit_snapshot(
    company_config: CompanyConfig,
    mapping_result: ColumnMappingResult,
    sso_rule: SsoRule,
) -> AuditSnapshot:
    field_to_mapping = {
        m.canonical_field: m for m in mapping_result.mappings if m.canonical_field is not None
    }
    component_keys = {c.key for c in company_config.components}

    # Identity / non-formula mapped fields first (employee_id, employee_name,
    # and any future identity field), in the order the mapping returned them —
    # no hardcoding of which or how many. Then the formula components in order.
    column_mapping = [
        ColumnMappingUsed(
            canonical_field=m.canonical_field,
            column_index=m.column_index,
            column_name=m.column_name,
        )
        for m in mapping_result.mappings
        if m.canonical_field is not None and m.canonical_field not in component_keys
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
    employee_id_mapping = _find_mapping(mapping_result, "employee_id")
    if employee_id_mapping is None:
        raise ValueError(
            "no column was mapped to the 'employee_id' canonical field — cannot identify employee rows"
        )
    employee_id_column = employee_id_mapping.column_index

    # employee_name is optional identity metadata: if unmapped, names are simply
    # blank — never an error, and the numbers are unaffected either way.
    employee_name_mapping = _find_mapping(mapping_result, "employee_name")
    employee_name_column = employee_name_mapping.column_index if employee_name_mapping else None

    employees: list[EmployeeRowResult] = []
    error_rows: list[ErrorRow] = []
    total_base = Decimal("0")
    total_contribution = Decimal("0")

    for position, row in enumerate(employee_rows, start=1):
        employee_id = _read_text_cell(row, employee_id_column)

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
                employee_name=_read_text_cell(row, employee_name_column),
                base=result.base,
                contribution=result.contribution,
                breakdown=result.breakdown,
            )
        )
        total_base += result.base
        total_contribution += result.contribution

    audit = _build_audit_snapshot(company_config, mapping_result, sso_rule)

    return CompanyResult(
        employees=employees,
        total_base=total_base,
        total_contribution=total_contribution,
        error_rows=error_rows,
        audit=audit,
    )
