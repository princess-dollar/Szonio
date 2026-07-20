import json
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.app import app, get_config_store
from services.config_store import ConfigStore

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REAL_CONFIGS = PROJECT_ROOT / "configs"
REAL_CANONICAL = PROJECT_ROOT / "canonical_fields.json"


@pytest.fixture
def store_dir(tmp_path):
    """A throwaway copy of configs/ + canonical_fields.json. Tests mutate this,
    never the real repo files."""
    shutil.copytree(REAL_CONFIGS, tmp_path / "configs")
    shutil.copy(REAL_CANONICAL, tmp_path / "canonical_fields.json")
    return tmp_path


@pytest.fixture
def client(store_dir):
    store = ConfigStore(store_dir)
    app.dependency_overrides[get_config_store] = lambda: store
    yield TestClient(app)
    app.dependency_overrides.clear()


def _valid_domnick_components():
    return [
        {"field": "salary_per_period", "sign": "+", "required": True},
        {"field": "deduct_unpaid_leave", "sign": "-", "required": False},
        {"field": "deduct_late_early", "sign": "-", "required": False},
    ]


# --- GET company config ---------------------------------------------------


def test_get_company_returns_editable_shape(client):
    resp = client.get("/api/companies/domnick")
    assert resp.status_code == 200
    body = resp.json()
    assert body["company_id"] == "domnick"
    assert body["display_name"] == "Domnick"
    assert isinstance(body["version"], int)
    fields = {c["field"] for c in body["components"]}
    assert "salary_per_period" in fields
    for c in body["components"]:
        assert set(c.keys()) == {"field", "sign", "required"}


def test_get_unknown_company_is_404(client):
    assert client.get("/api/companies/does_not_exist").status_code == 404


# --- PUT edit -------------------------------------------------------------


def test_put_valid_edit_increments_version_and_persists(client, store_dir):
    before = client.get("/api/companies/domnick").json()
    old_version = before["version"]

    resp = client.put(
        "/api/companies/domnick",
        json={"display_name": "Domnick Edited", "components": _valid_domnick_components()},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["version"] == old_version + 1
    assert body["display_name"] == "Domnick Edited"

    # The file on disk re-parses and matches the returned version.
    on_disk = json.loads((store_dir / "configs" / "domnick.json").read_text(encoding="utf-8"))
    assert on_disk["version"] == old_version + 1
    assert on_disk["display_name"] == "Domnick Edited"

    # Atomic write leaves no temp files behind.
    assert list((store_dir / "configs").glob("*.tmp")) == []


@pytest.mark.parametrize(
    "components,label",
    [
        (
            [{"field": "deduct_unpaid_leave", "sign": "-", "required": False}],
            "missing salary_per_period",
        ),
        (
            [
                {"field": "salary_per_period", "sign": "+", "required": True},
                {"field": "totally_made_up_field", "sign": "-", "required": False},
            ],
            "nonexistent canonical field",
        ),
        (
            [
                {"field": "salary_per_period", "sign": "+", "required": True},
                {"field": "deduct_late_early", "sign": "-", "required": False},
                {"field": "deduct_late_early", "sign": "-", "required": False},
            ],
            "duplicate field",
        ),
        (
            [{"field": "salary_per_period", "sign": "x", "required": True}],
            "bad sign",
        ),
    ],
)
def test_put_invalid_is_400_and_leaves_file_unchanged(client, store_dir, components, label):
    target = store_dir / "configs" / "domnick.json"
    original_bytes = target.read_bytes()

    resp = client.put(
        "/api/companies/domnick",
        json={"display_name": "Should Not Persist", "components": components},
    )
    assert resp.status_code == 400, label

    # Nothing was written: the file is byte-for-byte unchanged, no temp leftovers.
    assert target.read_bytes() == original_bytes, label
    assert list((store_dir / "configs").glob("*.tmp")) == []


def test_put_unknown_company_is_404(client):
    resp = client.put(
        "/api/companies/ghost",
        json={"display_name": "Ghost", "components": _valid_domnick_components()},
    )
    assert resp.status_code == 404


# --- POST create company --------------------------------------------------


def test_post_creates_new_company(client, store_dir):
    resp = client.post(
        "/api/companies",
        json={
            "company_id": "newco",
            "display_name": "New Co",
            "components": [{"field": "salary_per_period", "sign": "+", "required": True}],
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["company_id"] == "newco"
    assert body["version"] == 1
    assert (store_dir / "configs" / "newco.json").exists()


def test_post_duplicate_company_is_409(client):
    resp = client.post(
        "/api/companies",
        json={
            "company_id": "domnick",
            "display_name": "Dup",
            "components": [{"field": "salary_per_period", "sign": "+", "required": True}],
        },
    )
    assert resp.status_code == 409


@pytest.mark.parametrize("bad_id", ["New Co", "UPPER", "1leading", "has-dash", "space id"])
def test_post_bad_company_id_format_is_400(client, bad_id):
    resp = client.post(
        "/api/companies",
        json={
            "company_id": bad_id,
            "display_name": "X",
            "components": [{"field": "salary_per_period", "sign": "+", "required": True}],
        },
    )
    assert resp.status_code == 400


# --- canonical fields -----------------------------------------------------


def test_get_canonical_fields_excludes_identity(client):
    resp = client.get("/api/canonical-fields")
    assert resp.status_code == 200
    fields = resp.json()["canonical_fields"]
    keys = {f["key"] for f in fields}
    assert "salary_per_period" in keys
    assert "employee_id" not in keys
    assert "employee_name" not in keys
    assert all(f["polarity"] != "identity" for f in fields)


def test_post_adds_canonical_field(client, store_dir):
    resp = client.post(
        "/api/canonical-fields",
        json={
            "key": "special_allowance",
            "aliases_th": ["เบี้ยพิเศษ"],
            "expected_group": None,
            "polarity": "income",
        },
    )
    assert resp.status_code == 201

    # It re-parses from disk and now appears in the list.
    raw = json.loads((store_dir / "canonical_fields.json").read_text(encoding="utf-8"))
    assert any(f["key"] == "special_allowance" for f in raw["fields"])
    listed = {f["key"] for f in client.get("/api/canonical-fields").json()["canonical_fields"]}
    assert "special_allowance" in listed


def test_post_duplicate_canonical_key_is_409(client):
    resp = client.post(
        "/api/canonical-fields",
        json={"key": "salary_per_period", "aliases_th": [], "expected_group": None, "polarity": "income"},
    )
    assert resp.status_code == 409


def test_post_identity_polarity_is_rejected_400(client):
    resp = client.post(
        "/api/canonical-fields",
        json={"key": "another_identity", "aliases_th": [], "expected_group": None, "polarity": "identity"},
    )
    assert resp.status_code == 400


def test_canonical_fields_have_no_edit_or_delete_route(client):
    # ADD-ONLY: editing/deleting an existing field is not exposed at all.
    assert client.put("/api/canonical-fields", json={}).status_code == 405
    assert client.delete("/api/canonical-fields").status_code == 405
    # And no per-key route exists to target an existing field.
    assert client.delete("/api/canonical-fields/salary_per_period").status_code in (404, 405)
