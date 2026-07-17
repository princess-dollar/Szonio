"""Phase 4: the calculation engine. Pure, deterministic Python arithmetic —
no LLM anywhere in this phase (its one job finished in Phase 2). All money
math uses Decimal, never float.

Layer 1 (BASE): apply the company's signed formula to one employee row.
Layer 2 (CONTRIBUTION): base capped at the SSO ceiling, times the rate,
rounded to 2 decimal places with ROUND_HALF_UP.
"""

from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Optional

from models.calculation import ComponentAmount, EmployeeResult
from models.column_mapping import ColumnMapping, ColumnMappingResult
from models.company_config import CompanyConfig, SsoRule

_TWO_PLACES = Decimal("0.01")


def _to_decimal(value: Any) -> Decimal:
    """Read one cell value into Decimal. None/blank -> 0. Floats always go
    through their string representation first (SKILL.md rule 4) so a value
    like 19.1 becomes Decimal("19.1"), never the binary-imprecise
    Decimal(19.1)."""
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        return Decimal(stripped) if stripped else Decimal("0")
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, int):
        return Decimal(value)
    raise ValueError(f"cannot convert cell value {value!r} to Decimal")


def _field_to_column_mapping(mapping: ColumnMappingResult) -> dict[str, ColumnMapping]:
    return {m.canonical_field: m for m in mapping.mappings if m.canonical_field is not None}


def _compute_base_and_breakdown(
    row: dict[int, Any],
    company_config: CompanyConfig,
    mapping: ColumnMappingResult,
) -> tuple[Decimal, list[ComponentAmount]]:
    field_to_column = _field_to_column_mapping(mapping)

    base = Decimal("0")
    breakdown: list[ComponentAmount] = []

    for component in company_config.components:
        column_mapping = field_to_column.get(component.key)

        column_index: Optional[int]
        column_name: Optional[str]
        if column_mapping is None:
            if component.required:
                raise ValueError(
                    f"required field {component.key!r} has no mapped column — "
                    f"cannot calculate {company_config.company_id!r} (Phase 3 should have blocked this)"
                )
            amount = Decimal("0")
            column_index = None
            column_name = None
        else:
            amount = _to_decimal(row.get(column_mapping.column_index))
            column_index = column_mapping.column_index
            column_name = column_mapping.column_name

        base = base + amount if component.sign == "+" else base - amount

        breakdown.append(
            ComponentAmount(
                canonical_field=component.key,
                column_index=column_index,
                column_name=column_name,
                sign=component.sign,
                amount=amount,
            )
        )

    return max(base, Decimal("0")), breakdown


def calculate_base(
    row: dict[int, Any],
    company_config: CompanyConfig,
    mapping: ColumnMappingResult,
) -> Decimal:
    """Apply the company's signed formula to one employee row. Returns the
    negative-clamped base (never below Decimal("0"))."""
    base, _ = _compute_base_and_breakdown(row, company_config, mapping)
    return base


def calculate_contribution(base: Decimal, sso_rule: SsoRule) -> Decimal:
    """capped_base = min(base, ceiling); contribution = capped_base * rate,
    rounded to 2dp with ROUND_HALF_UP. Equivalent to min(base*rate,
    ceiling*rate) since rate > 0 — see tests/test_sso_calculator.py for the
    proof."""
    capped_base = min(base, sso_rule.ceiling)
    raw = capped_base * sso_rule.rate
    return raw.quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)


def calculate_employee(
    row: dict[int, Any],
    company_config: CompanyConfig,
    mapping: ColumnMappingResult,
    sso_rule: SsoRule,
) -> EmployeeResult:
    base, breakdown = _compute_base_and_breakdown(row, company_config, mapping)
    contribution = calculate_contribution(base, sso_rule)
    return EmployeeResult(base=base, contribution=contribution, breakdown=breakdown)
