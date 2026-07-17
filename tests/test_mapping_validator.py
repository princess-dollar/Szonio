from pathlib import Path

import pytest

from models import ColumnMapping, ColumnMappingResult, MappingRules, load_canonical_keys, load_company_config
from services.mapping_validator import validate_mapping

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DOMNICK_CONFIG_PATH = PROJECT_ROOT / "configs" / "domnick.json"

# Domnick's real formula (configs/domnick.json): +salary_per_period
# -deduct_unpaid_leave -deduct_late_early. Real columns from Upload_Excel.xlsx:
# index 21 -> salary_per_period, index 64 -> deduct_unpaid_leave, index 61 -> deduct_late_early.


@pytest.fixture(scope="module")
def canonical_keys():
    return load_canonical_keys()


@pytest.fixture(scope="module")
def domnick_config(canonical_keys):
    return load_company_config(DOMNICK_CONFIG_PATH, canonical_keys)


def _mapping(column_index, column_name, canonical_field, confidence):
    return ColumnMapping(
        column_index=column_index,
        column_name=column_name,
        canonical_field=canonical_field,
        confidence=confidence,
    )


def _result(mappings):
    return ColumnMappingResult(mappings=mappings)


def test_clean_full_mapping_passes_with_no_blocking_reasons(domnick_config):
    mapping_result = _result(
        [
            _mapping(21, "เงินเดือนต่องวด", "salary_per_period", 0.97),
            _mapping(64, "หักลาไม่รับค่าจ้าง (บาท)", "deduct_unpaid_leave", 0.95),
            _mapping(61, "หักมาสาย/กลับก่อน (บาท)", "deduct_late_early", 0.93),
        ]
    )
    rules = MappingRules(min_confidence=0.80)

    report = validate_mapping(mapping_result, domnick_config, rules)

    assert report.decision == "pass"
    assert report.reasons == []
    assert report.notes == []


def test_salary_per_period_unmapped_forces_needs_review(domnick_config):
    mapping_result = _result(
        [
            _mapping(21, "เงินเดือนต่องวด", None, 0.4),
            _mapping(64, "หักลาไม่รับค่าจ้าง (บาท)", "deduct_unpaid_leave", 0.95),
            _mapping(61, "หักมาสาย/กลับก่อน (บาท)", "deduct_late_early", 0.93),
        ]
    )
    rules = MappingRules(min_confidence=0.80)

    report = validate_mapping(mapping_result, domnick_config, rules)

    assert report.decision == "needs_review"
    codes = {r.code for r in report.reasons}
    assert "REQUIRED_FIELD_UNMAPPED" in codes
    reason = next(r for r in report.reasons if r.code == "REQUIRED_FIELD_UNMAPPED")
    assert reason.fields == ["salary_per_period"]


def test_column_below_min_confidence_forces_needs_review_and_names_it(domnick_config):
    mapping_result = _result(
        [
            _mapping(21, "เงินเดือนต่องวด", "salary_per_period", 0.97),
            _mapping(64, "หักลาไม่รับค่าจ้าง (บาท)", "deduct_unpaid_leave", 0.55),
            _mapping(61, "หักมาสาย/กลับก่อน (บาท)", "deduct_late_early", 0.93),
        ]
    )
    rules = MappingRules(min_confidence=0.80)

    report = validate_mapping(mapping_result, domnick_config, rules)

    assert report.decision == "needs_review"
    reason = next(r for r in report.reasons if r.code == "LOW_CONFIDENCE")
    assert len(reason.columns) == 1
    flagged = reason.columns[0]
    assert flagged.column_index == 64
    assert flagged.column_name == "หักลาไม่รับค่าจ้าง (บาท)"
    assert flagged.confidence == 0.55


def test_two_columns_mapped_to_same_field_forces_needs_review(domnick_config):
    mapping_result = _result(
        [
            _mapping(21, "เงินเดือนต่องวด", "salary_per_period", 0.97),
            _mapping(64, "หักลาไม่รับค่าจ้าง (บาท)", "deduct_unpaid_leave", 0.95),
            _mapping(999, "some other column also about unpaid leave", "deduct_unpaid_leave", 0.9),
        ]
    )
    rules = MappingRules(min_confidence=0.80)

    report = validate_mapping(mapping_result, domnick_config, rules)

    assert report.decision == "needs_review"
    reason = next(r for r in report.reasons if r.code == "DUPLICATE_MAPPING")
    assert reason.fields == ["deduct_unpaid_leave"]
    flagged_indexes = {c.column_index for c in reason.columns}
    assert flagged_indexes == {64, 999}


def test_optional_field_unmapped_still_passes_with_a_note(domnick_config):
    mapping_result = _result(
        [
            _mapping(21, "เงินเดือนต่องวด", "salary_per_period", 0.97),
            # deduct_unpaid_leave and deduct_late_early: no column mapped at all
        ]
    )
    rules = MappingRules(min_confidence=0.80)

    report = validate_mapping(mapping_result, domnick_config, rules)

    assert report.decision == "pass"
    assert report.reasons == []
    note = next(n for n in report.notes if n.code == "OPTIONAL_FIELD_UNMAPPED")
    assert note.fields == ["deduct_late_early", "deduct_unpaid_leave"]


@pytest.mark.parametrize(
    "min_confidence,expect_low_confidence",
    [
        (0.80, False),
        (0.85, True),
    ],
)
def test_threshold_is_read_from_mapping_rules_not_hardcoded(
    domnick_config, min_confidence, expect_low_confidence
):
    # A single borderline column at 0.82: passes a 0.80 threshold, fails a
    # 0.85 one. If mapping_validator hardcoded its own number instead of
    # using mapping_rules.min_confidence, this would not vary with the input.
    mapping_result = _result(
        [
            _mapping(21, "เงินเดือนต่องวด", "salary_per_period", 0.97),
            _mapping(64, "หักลาไม่รับค่าจ้าง (บาท)", "deduct_unpaid_leave", 0.82),
            _mapping(61, "หักมาสาย/กลับก่อน (บาท)", "deduct_late_early", 0.93),
        ]
    )
    rules = MappingRules(min_confidence=min_confidence)

    report = validate_mapping(mapping_result, domnick_config, rules)

    codes = {r.code for r in report.reasons}
    assert ("LOW_CONFIDENCE" in codes) == expect_low_confidence
    assert (report.decision == "needs_review") == expect_low_confidence
