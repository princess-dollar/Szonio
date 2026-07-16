import pytest

from models import ColumnMappingResult, validate_column_mapping_response

VALID_INDEXES = {21, 35, 69}
CANONICAL_KEYS = {"salary_per_period", "leave_compensation_income", "deduct_leave_compensation"}


def _good_raw():
    return {
        "mappings": [
            {
                "column_index": 21,
                "column_name": "เงินเดือนต่องวด",
                "canonical_field": "salary_per_period",
                "confidence": 0.98,
            },
            {
                "column_index": 35,
                "column_name": "ชดเชยวันลา (บาท)",
                "canonical_field": "leave_compensation_income",
                "confidence": 0.9,
            },
            {
                "column_index": 69,
                "column_name": "some unrelated column",
                "canonical_field": None,
                "confidence": 0.1,
            },
        ]
    }


def test_accepts_good_response_and_returns_typed_result():
    result = validate_column_mapping_response(_good_raw(), VALID_INDEXES, CANONICAL_KEYS)

    assert isinstance(result, ColumnMappingResult)
    assert len(result.mappings) == 3
    assert result.mappings[0].canonical_field == "salary_per_period"


def test_null_canonical_field_does_not_crash():
    raw = _good_raw()
    result = validate_column_mapping_response(raw, VALID_INDEXES, CANONICAL_KEYS)

    null_mapping = next(m for m in result.mappings if m.column_index == 69)
    assert null_mapping.canonical_field is None


def test_unmapped_fields_is_set_difference_of_canonical_keys_and_matched_fields():
    result = validate_column_mapping_response(_good_raw(), VALID_INDEXES, CANONICAL_KEYS)

    # salary_per_period and leave_compensation_income were matched; deduct_leave_compensation was not.
    assert result.unmapped_fields == ["deduct_leave_compensation"]


def test_all_fields_matched_yields_empty_unmapped_fields():
    raw = _good_raw()
    raw["mappings"][2]["canonical_field"] = "deduct_leave_compensation"
    raw["mappings"][2]["confidence"] = 0.7

    result = validate_column_mapping_response(raw, VALID_INDEXES, CANONICAL_KEYS)

    assert result.unmapped_fields == []


def test_rejects_unknown_column_index():
    raw = _good_raw()
    raw["mappings"][0]["column_index"] = 9999

    with pytest.raises(ValueError, match="9999"):
        validate_column_mapping_response(raw, VALID_INDEXES, CANONICAL_KEYS)


def test_rejects_unknown_canonical_field():
    raw = _good_raw()
    raw["mappings"][0]["canonical_field"] = "totally_made_up_key"

    with pytest.raises(ValueError, match="totally_made_up_key"):
        validate_column_mapping_response(raw, VALID_INDEXES, CANONICAL_KEYS)


@pytest.mark.parametrize("bad_confidence", [-0.1, 1.1, 2, -5])
def test_rejects_confidence_out_of_range(bad_confidence):
    raw = _good_raw()
    raw["mappings"][0]["confidence"] = bad_confidence

    with pytest.raises(ValueError):
        validate_column_mapping_response(raw, VALID_INDEXES, CANONICAL_KEYS)


@pytest.mark.parametrize(
    "broken_raw",
    [
        {},
        {"mappings": "not-a-list"},
        {"mappings": [{"column_index": 21}]},
    ],
)
def test_rejects_malformed_shape(broken_raw):
    with pytest.raises(ValueError):
        validate_column_mapping_response(broken_raw, VALID_INDEXES, CANONICAL_KEYS)
