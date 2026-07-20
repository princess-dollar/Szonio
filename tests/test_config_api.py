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
# Admins never send company_id — the server generates an opaque one and
# enforces uniqueness on the Thai display_name instead.


def _create_company_body(display_name, components=None):
    return {
        "display_name": display_name,
        "components": components
        or [{"field": "salary_per_period", "sign": "+", "required": True}],
    }


def test_post_creates_new_company_with_generated_id(client, store_dir):
    resp = client.post("/api/companies", json=_create_company_body("New Co"))
    assert resp.status_code == 201
    body = resp.json()

    company_id = body["company_id"]
    assert company_id.startswith("company_")
    assert body["display_name"] == "New Co"
    assert body["version"] == 1
    assert (store_dir / "configs" / f"{company_id}.json").exists()


def test_created_company_is_retrievable_by_generated_id(client):
    created = client.post("/api/companies", json=_create_company_body("Retrievable Co")).json()
    company_id = created["company_id"]

    fetched = client.get(f"/api/companies/{company_id}")
    assert fetched.status_code == 200
    assert fetched.json()["company_id"] == company_id
    assert fetched.json()["display_name"] == "Retrievable Co"


def test_post_request_body_ignores_any_client_supplied_company_id(client):
    # Even if a client sneaks company_id into the body, it is not honored:
    # the server always mints its own opaque id.
    resp = client.post(
        "/api/companies",
        json={
            "company_id": "attacker_chosen_id",
            "display_name": "Ignore My Id",
            "components": [{"field": "salary_per_period", "sign": "+", "required": True}],
        },
    )
    assert resp.status_code == 201
    assert resp.json()["company_id"] != "attacker_chosen_id"
    assert resp.json()["company_id"].startswith("company_")


def test_post_duplicate_display_name_is_409(client):
    # "Domnick" already exists; a case/whitespace variant must be rejected.
    resp = client.post("/api/companies", json=_create_company_body("  domnick  "))
    assert resp.status_code == 409


def test_post_blank_display_name_is_400(client):
    resp = client.post("/api/companies", json=_create_company_body("   "))
    assert resp.status_code == 400


def test_post_company_generates_unique_id_on_collision(client, store_dir, monkeypatch):
    # First mint collides with an id that already exists on disk; the store must
    # detect the collision and retry rather than clobber the existing file.
    first = client.post("/api/companies", json=_create_company_body("First Co")).json()
    taken_suffix = first["company_id"].removeprefix("company_")

    import services.config_store as cs

    seq = iter([taken_suffix, taken_suffix, "abcdef"])
    monkeypatch.setattr(cs.secrets, "token_hex", lambda n: next(seq))

    resp = client.post("/api/companies", json=_create_company_body("Second Co"))
    assert resp.status_code == 201
    assert resp.json()["company_id"] == "company_abcdef"
    # The colliding company's file was left intact.
    assert (store_dir / "configs" / f"{first['company_id']}.json").exists()


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


def test_post_adds_canonical_field_with_generated_key(client, store_dir):
    resp = client.post(
        "/api/canonical-fields",
        json={
            "name_th_primary": "เบี้ยพิเศษ",
            "aliases_th": ["ค่าพิเศษ"],
            "expected_group": None,
            "polarity": "income",
        },
    )
    assert resp.status_code == 201
    field = resp.json()["canonical_field"]

    key = field["key"]
    assert key.startswith("field_")
    # The primary Thai name is stored first, so aliases_th[0] is always a
    # human-facing label; extra aliases follow.
    assert field["aliases_th"] == ["เบี้ยพิเศษ", "ค่าพิเศษ"]

    # It re-parses from disk and is retrievable by its generated key.
    raw = json.loads((store_dir / "canonical_fields.json").read_text(encoding="utf-8"))
    assert any(f["key"] == key for f in raw["fields"])
    listed = {f["key"] for f in client.get("/api/canonical-fields").json()["canonical_fields"]}
    assert key in listed


def test_post_field_body_ignores_any_client_supplied_key(client):
    resp = client.post(
        "/api/canonical-fields",
        json={
            "key": "attacker_chosen_key",
            "name_th_primary": "ชื่อใหม่ล่าสุด",
            "aliases_th": [],
            "expected_group": None,
            "polarity": "income",
        },
    )
    assert resp.status_code == 201
    assert resp.json()["canonical_field"]["key"] != "attacker_chosen_key"
    assert resp.json()["canonical_field"]["key"].startswith("field_")


def test_post_duplicate_canonical_name_is_409(client):
    # "เงินเดือนต่องวด" is an existing alias of salary_per_period. A
    # whitespace variant as the primary name must be rejected by Thai name.
    resp = client.post(
        "/api/canonical-fields",
        json={
            "name_th_primary": "  เงินเดือนต่องวด  ",
            "aliases_th": [],
            "expected_group": None,
            "polarity": "income",
        },
    )
    assert resp.status_code == 409


def test_post_duplicate_via_alias_is_409(client):
    # New primary name is unique, but one of its aliases collides with an
    # existing field's alias — dedup is on every Thai name, not just the primary.
    resp = client.post(
        "/api/canonical-fields",
        json={
            "name_th_primary": "ชื่อที่ไม่ซ้ำแน่นอน",
            "aliases_th": ["หักชดเชยวันลา (บาท)"],
            "expected_group": None,
            "polarity": "deduction",
        },
    )
    assert resp.status_code == 409


def test_post_duplicate_name_is_case_insensitive_409(client):
    first = client.post(
        "/api/canonical-fields",
        json={
            "name_th_primary": "Special Bonus",
            "aliases_th": [],
            "expected_group": None,
            "polarity": "income",
        },
    )
    assert first.status_code == 201

    dup = client.post(
        "/api/canonical-fields",
        json={
            "name_th_primary": "special bonus",
            "aliases_th": [],
            "expected_group": None,
            "polarity": "income",
        },
    )
    assert dup.status_code == 409


def test_post_blank_primary_name_is_400(client):
    resp = client.post(
        "/api/canonical-fields",
        json={"name_th_primary": "   ", "aliases_th": [], "expected_group": None, "polarity": "income"},
    )
    assert resp.status_code == 400


def test_post_field_generates_unique_key_on_collision(client, monkeypatch):
    first = client.post(
        "/api/canonical-fields",
        json={"name_th_primary": "ฟิลด์แรก", "aliases_th": [], "expected_group": None, "polarity": "income"},
    ).json()["canonical_field"]
    taken_suffix = first["key"].removeprefix("field_")

    import services.config_store as cs

    seq = iter([taken_suffix, "beefee"])
    monkeypatch.setattr(cs.secrets, "token_hex", lambda n: next(seq))

    resp = client.post(
        "/api/canonical-fields",
        json={"name_th_primary": "ฟิลด์สอง", "aliases_th": [], "expected_group": None, "polarity": "income"},
    )
    assert resp.status_code == 201
    assert resp.json()["canonical_field"]["key"] == "field_beefee"


def test_post_identity_polarity_is_rejected_400(client):
    resp = client.post(
        "/api/canonical-fields",
        json={
            "name_th_primary": "ตัวตนใหม่",
            "aliases_th": [],
            "expected_group": None,
            "polarity": "identity",
        },
    )
    assert resp.status_code == 400


def test_canonical_fields_have_no_edit_or_delete_route(client):
    # ADD-ONLY: editing/deleting an existing field is not exposed at all.
    assert client.put("/api/canonical-fields", json={}).status_code == 405
    assert client.delete("/api/canonical-fields").status_code == 405
    # And no per-key route exists to target an existing field.
    assert client.delete("/api/canonical-fields/salary_per_period").status_code in (404, 405)
