import io
import os
from pathlib import Path

import openpyxl
import pytest
from fastapi.testclient import TestClient

import api.app as api_app
from api.app import app, get_llm_client

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SAMPLE_FILE = PROJECT_ROOT / "Upload_Excel.xlsx"

# Real columns from Upload_Excel.xlsx: index 1 -> employee_id, index 21 ->
# salary_per_period, index 64 -> deduct_unpaid_leave, index 61 -> deduct_late_early.


class _StubLlmClient:
    """Stands in for LlmGatewayClient — no network in any test."""

    def __init__(self, raw_response):
        self._raw_response = raw_response

    def map_columns(self, columns, canonical_fields):
        return self._raw_response


def _domnick_full_raw_mapping():
    return {
        "mappings": [
            {"column_index": 1, "column_name": "รหัสพนักงาน", "canonical_field": "employee_id", "confidence": 0.99},
            {"column_index": 2, "column_name": "ชื่อ-นามสกุล", "canonical_field": "employee_name", "confidence": 0.97},
            {"column_index": 21, "column_name": "เงินเดือนต่องวด", "canonical_field": "salary_per_period", "confidence": 0.97},
            {"column_index": 64, "column_name": "หักลาไม่รับค่าจ้าง (บาท)", "canonical_field": "deduct_unpaid_leave", "confidence": 0.95},
            {"column_index": 61, "column_name": "หักมาสาย/กลับก่อน (บาท)", "canonical_field": "deduct_late_early", "confidence": 0.93},
        ]
    }


def _domnick_mapping_without_name():
    return {"mappings": [m for m in _domnick_full_raw_mapping()["mappings"]
                         if m["canonical_field"] != "employee_name"]}


def _override_llm(raw_response):
    app.dependency_overrides[get_llm_client] = lambda: _StubLlmClient(raw_response)


@pytest.fixture
def client():
    c = TestClient(app)
    yield c
    app.dependency_overrides.clear()


def _sample_upload():
    return ("Upload_Excel.xlsx", SAMPLE_FILE.read_bytes(),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


# --- GET /api/companies ---------------------------------------------------


def test_list_companies_returns_configs_and_excludes_formula_less(client):
    resp = client.get("/api/companies")
    assert resp.status_code == 200
    companies = resp.json()["companies"]

    ids = {c["company_id"] for c in companies}
    # Every real config is present...
    assert {"domnick", "gmtx", "b2b", "apollo_wealth", "apollo_associate", "apollo_advisory"} <= ids
    # ...and KVIS (no config file) is not.
    assert "kvis" not in ids

    for c in companies:
        assert set(c.keys()) == {"company_id", "display_name"}


# --- POST /api/calculate: happy path -------------------------------------


def test_calculate_ok_returns_summary_rows_and_working_download(client):
    _override_llm(_domnick_full_raw_mapping())

    resp = client.post(
        "/api/calculate",
        files={"file": _sample_upload()},
        data={"company_id": "domnick"},
    )
    assert resp.status_code == 200
    body = resp.json()

    assert body["status"] == "ok"
    assert body["summary"]["company"]["company_id"] == "domnick"
    assert body["summary"]["employee_count"] == 33
    assert len(body["employees"]) == 33

    # Decimals serialized as strings.
    assert isinstance(body["summary"]["total_base"], str)
    assert isinstance(body["summary"]["total_contribution"], str)
    assert isinstance(body["employees"][0]["base"], str)
    assert isinstance(body["employees"][0]["contribution"], str)

    # employee_name present on every row; the mocked mapping points it at the
    # real name column, so at least one row has an actual name.
    assert all("employee_name" in e for e in body["employees"])
    assert any(e["employee_name"] for e in body["employees"])

    token = body["download_token"]
    assert token

    dl = client.get(f"/api/download/{token}")
    assert dl.status_code == 200
    assert dl.headers["content-type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert "attachment" in dl.headers["content-disposition"]

    wb = openpyxl.load_workbook(io.BytesIO(dl.content))
    assert wb.sheetnames == ["ผลรายคน", "สรุป"]


def test_calculate_ok_yields_null_names_when_no_name_column_mapped(client):
    _override_llm(_domnick_mapping_without_name())

    resp = client.post(
        "/api/calculate",
        files={"file": _sample_upload()},
        data={"company_id": "domnick"},
    )
    assert resp.status_code == 200
    body = resp.json()

    assert body["status"] == "ok"
    assert len(body["employees"]) == 33
    # Name column absent from the mapping -> null names, run still succeeds.
    assert all(e["employee_name"] is None for e in body["employees"])
    # Numbers are unaffected by the missing name column.
    assert body["summary"]["employee_count"] == 33


def test_download_token_is_single_use(client):
    _override_llm(_domnick_full_raw_mapping())
    resp = client.post("/api/calculate", files={"file": _sample_upload()}, data={"company_id": "domnick"})
    token = resp.json()["download_token"]

    assert client.get(f"/api/download/{token}").status_code == 200
    # Served once, then cleaned up.
    assert client.get(f"/api/download/{token}").status_code == 404


# --- POST /api/calculate: needs_review -----------------------------------


def test_calculate_needs_review_returns_report_and_no_download(client):
    raw = _domnick_full_raw_mapping()
    raw["mappings"] = [m for m in raw["mappings"] if m["canonical_field"] != "salary_per_period"]
    _override_llm(raw)

    resp = client.post(
        "/api/calculate",
        files={"file": _sample_upload()},
        data={"company_id": "domnick"},
    )
    assert resp.status_code == 200
    body = resp.json()

    assert body["status"] == "needs_review"
    assert "REQUIRED_FIELD_UNMAPPED" in body["report_th"]
    assert "salary_per_period" in body["report_th"]
    assert "download_token" not in body
    assert "employees" not in body


# --- validation errors ----------------------------------------------------


def test_bad_company_id_is_400(client):
    _override_llm(_domnick_full_raw_mapping())
    resp = client.post(
        "/api/calculate",
        files={"file": _sample_upload()},
        data={"company_id": "no_such_company"},
    )
    assert resp.status_code == 400


def test_non_xlsx_upload_is_400(client):
    _override_llm(_domnick_full_raw_mapping())
    resp = client.post(
        "/api/calculate",
        files={"file": ("notes.txt", b"hello", "text/plain")},
        data={"company_id": "domnick"},
    )
    assert resp.status_code == 400


# --- cleanup --------------------------------------------------------------


def test_upload_tempfile_is_deleted_after_request(client, monkeypatch):
    _override_llm(_domnick_full_raw_mapping())

    created = []
    original = api_app._save_upload_tempfile

    def spy(content):
        path = original(content)
        created.append(path)
        return path

    monkeypatch.setattr(api_app, "_save_upload_tempfile", spy)

    resp = client.post("/api/calculate", files={"file": _sample_upload()}, data={"company_id": "domnick"})
    assert resp.status_code == 200

    assert len(created) == 1
    assert not os.path.exists(created[0]), "temp upload should be deleted in the finally block"
