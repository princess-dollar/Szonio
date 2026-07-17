from decimal import ROUND_HALF_EVEN, ROUND_HALF_UP, Decimal
from pathlib import Path

import pytest

from models import (
    Component,
    CompanyConfig,
    ColumnMapping,
    ColumnMappingResult,
    load_canonical_keys,
    load_company_config,
    load_sso_rule,
)
from services.sso_calculator import calculate_base, calculate_contribution, calculate_employee

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DOMNICK_CONFIG_PATH = PROJECT_ROOT / "configs" / "domnick.json"
SSO_RULE_PATH = PROJECT_ROOT / "sso_rule.json"

# Domnick's real formula (configs/domnick.json): +salary_per_period
# -deduct_unpaid_leave -deduct_late_early. Real columns from Upload_Excel.xlsx:
# index 21 -> salary_per_period, index 64 -> deduct_unpaid_leave, index 61 -> deduct_late_early.


@pytest.fixture(scope="module")
def canonical_keys():
    return load_canonical_keys()


@pytest.fixture(scope="module")
def domnick_config(canonical_keys):
    return load_company_config(DOMNICK_CONFIG_PATH, canonical_keys)


@pytest.fixture(scope="module")
def sso_rule():
    return load_sso_rule(SSO_RULE_PATH)


@pytest.fixture
def domnick_full_mapping():
    return ColumnMappingResult(
        mappings=[
            ColumnMapping(
                column_index=21,
                column_name="เงินเดือนต่องวด",
                canonical_field="salary_per_period",
                confidence=0.97,
            ),
            ColumnMapping(
                column_index=64,
                column_name="หักลาไม่รับค่าจ้าง (บาท)",
                canonical_field="deduct_unpaid_leave",
                confidence=0.95,
            ),
            ColumnMapping(
                column_index=61,
                column_name="หักมาสาย/กลับก่อน (บาท)",
                canonical_field="deduct_late_early",
                confidence=0.93,
            ),
        ]
    )


# --- calculate_contribution: ceiling, rounding, cap-equivalence -----------


def test_base_above_ceiling_caps_at_max_contribution(sso_rule):
    assert calculate_contribution(Decimal("20000"), sso_rule) == Decimal("875.00")


def test_base_below_ceiling(sso_rule):
    assert calculate_contribution(Decimal("10000"), sso_rule) == Decimal("500.00")


def test_base_exactly_at_ceiling(sso_rule):
    assert calculate_contribution(Decimal("17500"), sso_rule) == Decimal("875.00")


def test_round_half_up_at_a_point_005_boundary(sso_rule):
    # 242.5 * 0.05 = 12.125 exactly, a genuine tie at the 3rd decimal place.
    # ROUND_HALF_UP must give 12.13; Python Decimal's default ROUND_HALF_EVEN
    # would instead give 12.12 (rounds to even) -- this proves we're not
    # relying on the default.
    contribution = calculate_contribution(Decimal("242.5"), sso_rule)
    assert contribution == Decimal("12.13")

    default_rounded = Decimal("12.125").quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)
    assert default_rounded == Decimal("12.12")
    assert contribution != default_rounded


@pytest.mark.parametrize("base_value", ["10000", "17500", "20000"])
def test_cap_equivalence_min_base_then_rate_equals_min_of_products(base_value, sso_rule):
    base = Decimal(base_value)

    cap_base_first = (min(base, sso_rule.ceiling) * sso_rule.rate).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    min_of_products = min(base * sso_rule.rate, sso_rule.ceiling * sso_rule.rate).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )

    assert cap_base_first == min_of_products == calculate_contribution(base, sso_rule)


# --- calculate_base / calculate_employee: real domnick formula ------------


def test_domnick_formula_with_real_subtractions(domnick_config, domnick_full_mapping, sso_rule):
    row = {21: 30000, 64: 5000, 61: 1000}

    base = calculate_base(row, domnick_config, domnick_full_mapping)
    assert base == Decimal("24000")

    result = calculate_employee(row, domnick_config, domnick_full_mapping, sso_rule)
    assert result.base == Decimal("24000")
    assert result.contribution == Decimal("875.00")  # 24000 > ceiling, capped


def test_negative_base_clamps_to_zero(domnick_config, domnick_full_mapping, sso_rule):
    row = {21: 1000, 64: 5000, 61: 0}

    assert calculate_base(row, domnick_config, domnick_full_mapping) == Decimal("0")

    result = calculate_employee(row, domnick_config, domnick_full_mapping, sso_rule)
    assert result.base == Decimal("0")
    assert result.contribution == Decimal("0.00")


def test_blank_cell_on_mapped_column_treated_as_zero(domnick_config, domnick_full_mapping):
    row = {21: Decimal("14000"), 64: None, 61: 0}

    base = calculate_base(row, domnick_config, domnick_full_mapping)
    assert base == Decimal("14000")


def test_optional_field_with_no_mapping_at_all_treated_as_zero(domnick_config):
    # deduct_late_early has no ColumnMapping entry at all -- not just a blank cell.
    mapping = ColumnMappingResult(
        mappings=[
            ColumnMapping(
                column_index=21,
                column_name="เงินเดือนต่องวด",
                canonical_field="salary_per_period",
                confidence=0.97,
            ),
            ColumnMapping(
                column_index=64,
                column_name="หักลาไม่รับค่าจ้าง (บาท)",
                canonical_field="deduct_unpaid_leave",
                confidence=0.95,
            ),
        ]
    )
    row = {21: 14000, 64: 500}

    result = calculate_employee(row, domnick_config, mapping, load_sso_rule(SSO_RULE_PATH))
    assert result.base == Decimal("13500")

    late_component = next(c for c in result.breakdown if c.canonical_field == "deduct_late_early")
    assert late_component.amount == Decimal("0")
    assert late_component.column_index is None
    assert late_component.column_name is None


def test_required_field_without_mapping_raises_clear_error(domnick_config, sso_rule):
    mapping = ColumnMappingResult(
        mappings=[
            ColumnMapping(
                column_index=64,
                column_name="หักลาไม่รับค่าจ้าง (บาท)",
                canonical_field="deduct_unpaid_leave",
                confidence=0.95,
            ),
        ]
    )
    row = {64: 500}

    with pytest.raises(ValueError, match="salary_per_period"):
        calculate_base(row, domnick_config, mapping)


# --- Decimal precision --------------------------------------------------


def test_no_float_drift_in_base_sum():
    # 0.1 + 0.2 != 0.3 in binary float. A correct Decimal(str(value))
    # conversion must not inherit that drift.
    config = CompanyConfig(
        company_id="synthetic",
        display_name="Synthetic",
        version=1,
        components=[
            Component(key="salary_per_period", sign="+", required=True),
            Component(key="cost_of_living", sign="+", required=False),
        ],
    )
    mapping = ColumnMappingResult(
        mappings=[
            ColumnMapping(
                column_index=1, column_name="a", canonical_field="salary_per_period", confidence=0.99
            ),
            ColumnMapping(
                column_index=2, column_name="b", canonical_field="cost_of_living", confidence=0.99
            ),
        ]
    )
    row = {1: 0.1, 2: 0.2}

    base = calculate_base(row, config, mapping)
    assert base == Decimal("0.3")
    assert str(base) == "0.3"


def test_employee_result_serializes_decimals_as_strings(domnick_config, domnick_full_mapping, sso_rule):
    row = {21: 30000, 64: 5000, 61: 1000}
    result = calculate_employee(row, domnick_config, domnick_full_mapping, sso_rule)

    assert isinstance(result.base, Decimal)
    assert isinstance(result.contribution, Decimal)
    assert all(isinstance(c.amount, Decimal) for c in result.breakdown)

    dumped = result.model_dump(mode="json")
    assert isinstance(dumped["base"], str)
    assert isinstance(dumped["contribution"], str)
    for item in dumped["breakdown"]:
        assert isinstance(item["amount"], str)
