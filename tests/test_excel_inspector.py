from pathlib import Path

import pytest

from excel_inspector import PII_COLUMN_NAMES
from excel_inspector import inspect_workbook

SAMPLE_FILE = Path(__file__).resolve().parent.parent / "Upload_Excel.xlsx"


@pytest.fixture(scope="module")
def metadata():
    return inspect_workbook(str(SAMPLE_FILE))


def _column_by_name(metadata, name):
    for col in metadata.columns:
        if col.name == name:
            return col
    raise AssertionError(f"column {name!r} not found")


def test_detects_all_88_columns(metadata):
    assert len(metadata.columns) + len(metadata.ground_truth) == 88


def test_detects_header_row_3(metadata):
    assert metadata.header_row_index == 3


def test_disambiguates_the_two_compensation_leave_columns(metadata):
    income_side = _column_by_name(metadata, "ชดเชยวันลา (บาท)")
    deduction_side = _column_by_name(metadata, "หักชดเชยวันลา (บาท)")

    assert income_side.group == "ชดเชยวันลา"
    assert deduction_side.group == "ชดเชยวันลา (หัก)"
    assert income_side.group != deduction_side.group


def test_pii_is_masked_in_sample_rows(metadata):
    pii_indexes = {col.index for col in metadata.columns if col.name in PII_COLUMN_NAMES}
    assert pii_indexes, "expected at least one PII column to be detected"

    for row in metadata.sample_rows:
        for idx in pii_indexes:
            assert row[idx] == "<masked>"


def test_ground_truth_columns_are_extracted_separately(metadata):
    ground_truth_names = {col.name for col in metadata.ground_truth}
    assert ground_truth_names == {"BASE SSO", "CAL SSO", "CHECK", "BASE TAX", "TAX"}

    normal_names = {col.name for col in metadata.columns}
    assert normal_names.isdisjoint(ground_truth_names)


def test_trailing_total_row_is_excluded_from_row_count(metadata):
    # Row 37 in the sample file is a grand-total row ("Total"), not an
    # employee — real employee data is rows 4-36 (33 rows).
    assert metadata.row_count == 33
