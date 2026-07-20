"""F2b: read/write access to the on-disk config files (company formulas and
the shared canonical-field dictionary). This is the ONLY module that writes
config data, so every write here goes through two guarantees:

1. VALIDATE BEFORE WRITE — a proposed company config is validated with the
   existing Phase 1 loader (models.company_config.load_company_config), which
   enforces valid signs, no duplicate fields, exactly one required
   salary_per_period, and the cross-file check that every referenced field
   exists in canonical_fields.json. Nothing is written unless it passes.
2. ATOMIC WRITE — content is written to a temp file in the same directory and
   os.replace()'d onto the target, so a crash mid-write can never leave a
   half-written/corrupt JSON file.

Canonical fields are ADD-ONLY through this store: there is no method to edit
or delete an existing field (that stays a manual dev task), and only
income/deduction polarities may be created — never a new identity field.

No LLM/gateway dependency: this is pure file read / validate / write.
"""

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Optional

from models.company_config import CompanyConfig, load_canonical_keys, load_company_config

PROJECT_ROOT = Path(__file__).resolve().parent.parent

_COMPANY_ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_FIELD_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_ADDABLE_POLARITIES = {"income", "deduction"}


class ConfigError(Exception):
    """Base for config-store errors, each carrying a short Thai message."""


class ConfigNotFound(ConfigError):
    pass


class ConfigConflict(ConfigError):
    pass


class ConfigValidation(ConfigError):
    pass


def resolve_base_dir() -> Path:
    """Directory holding configs/ + canonical_fields.json. Configurable via
    SSO_CONFIG_DIR so tests can point at a temp copy without ever mutating the
    real repo files; defaults to the project root."""
    return Path(os.environ.get("SSO_CONFIG_DIR", str(PROJECT_ROOT)))


class ConfigStore:
    def __init__(self, base_dir: Optional[Path] = None) -> None:
        self.base_dir = Path(base_dir) if base_dir is not None else resolve_base_dir()
        self.config_dir = self.base_dir / "configs"
        self.canonical_fields_path = self.base_dir / "canonical_fields.json"

    # --- atomic write -----------------------------------------------------

    def _atomic_write_json(self, target: Path, data: Any) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(dir=str(target.parent), suffix=".json.tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.write("\n")
            os.replace(tmp_path, target)  # atomic on same filesystem
        except BaseException:
            _safe_remove(tmp_path)
            raise

    # --- companies --------------------------------------------------------

    def _company_path(self, company_id: str) -> Path:
        return self.config_dir / f"{company_id}.json"

    def list_companies(self) -> list[dict]:
        if not self.config_dir.exists():
            return []
        canonical_keys = load_canonical_keys(self.canonical_fields_path)
        companies = []
        for path in sorted(self.config_dir.glob("*.json")):
            try:
                config = load_company_config(path, canonical_keys)
            except Exception:
                continue
            if not config.components:
                continue
            companies.append({"company_id": config.company_id, "display_name": config.display_name})
        return companies

    def get_company(self, company_id: str) -> CompanyConfig:
        path = self._company_path(company_id)
        if not path.exists():
            raise ConfigNotFound(f"ไม่พบบริษัท '{company_id}'")
        canonical_keys = load_canonical_keys(self.canonical_fields_path)
        return load_company_config(path, canonical_keys)

    def _validate_and_write_company(self, company_id: str, raw: dict) -> CompanyConfig:
        """Write `raw` to a temp file, validate it with the Phase 1 loader,
        and only os.replace() it onto the target if valid. The target file is
        never touched unless validation passes."""
        canonical_keys = load_canonical_keys(self.canonical_fields_path)

        # Precise message for the cross-file case before the generic gate.
        referenced = [c.get("key") for c in raw.get("components", [])]
        unknown = sorted({k for k in referenced if k} - canonical_keys)
        if unknown:
            raise ConfigValidation(
                f"ฟิลด์ต่อไปนี้ไม่มีใน canonical_fields.json: {', '.join(unknown)}"
            )

        self.config_dir.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(dir=str(self.config_dir), suffix=".json.tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(raw, f, ensure_ascii=False, indent=2)
                f.write("\n")
            try:
                config = load_company_config(tmp_path, canonical_keys)
            except ValueError:
                raise ConfigValidation(
                    "สูตรไม่ถูกต้อง: ต้องมี salary_per_period ที่ required เพียงหนึ่งเดียว, "
                    "เครื่องหมายต้องเป็น + หรือ - เท่านั้น และห้ามมีฟิลด์ซ้ำ"
                )
        except BaseException:
            _safe_remove(tmp_path)
            raise

        os.replace(tmp_path, self._company_path(company_id))
        return config

    def save_company(
        self, company_id: str, display_name: str, components: list[dict]
    ) -> CompanyConfig:
        """Edit an existing company's formula. Increments version. 404 if the
        company does not exist (use create_company for new ones)."""
        path = self._company_path(company_id)
        if not path.exists():
            raise ConfigNotFound(f"ไม่พบบริษัท '{company_id}'")

        current = self.get_company(company_id)
        raw = {
            "company_id": company_id,
            "display_name": display_name,
            "version": current.version + 1,
            "components": components,
        }
        return self._validate_and_write_company(company_id, raw)

    def create_company(
        self, company_id: str, display_name: str, components: list[dict]
    ) -> CompanyConfig:
        if not _COMPANY_ID_RE.match(company_id):
            raise ConfigValidation(
                "รหัสบริษัทต้องเป็นตัวพิมพ์เล็ก a-z, ตัวเลข หรือ _ เท่านั้น และห้ามขึ้นต้นด้วยตัวเลข"
            )
        if self._company_path(company_id).exists():
            raise ConfigConflict(f"มีบริษัท '{company_id}' อยู่แล้ว")

        raw = {
            "company_id": company_id,
            "display_name": display_name,
            "version": 1,
            "components": components,
        }
        return self._validate_and_write_company(company_id, raw)

    # --- canonical fields (ADD-ONLY) --------------------------------------

    def _read_canonical_raw(self) -> dict:
        with open(self.canonical_fields_path, encoding="utf-8") as f:
            return json.load(f)

    def list_canonical_fields(self, include_identity: bool = False) -> list[dict]:
        raw = self._read_canonical_raw()
        fields = []
        for field in raw["fields"]:
            if not include_identity and field.get("polarity") == "identity":
                continue
            fields.append(
                {
                    "key": field["key"],
                    "aliases_th": field.get("aliases_th", []),
                    "expected_group": field.get("expected_group"),
                    "polarity": field.get("polarity"),
                }
            )
        return fields

    def add_canonical_field(
        self,
        key: str,
        aliases_th: list[str],
        expected_group: Optional[str],
        polarity: str,
    ) -> dict:
        if not _FIELD_KEY_RE.match(key):
            raise ConfigValidation("key ต้องเป็น snake_case (a-z, ตัวเลข, _) และห้ามขึ้นต้นด้วยตัวเลข")
        if polarity not in _ADDABLE_POLARITIES:
            raise ConfigValidation("polarity ต้องเป็น income หรือ deduction เท่านั้น")

        raw = self._read_canonical_raw()
        existing_keys = {f["key"] for f in raw["fields"]}
        if key in existing_keys:
            raise ConfigConflict(f"มี canonical field '{key}' อยู่แล้ว")

        new_field = {
            "key": key,
            "aliases_th": list(aliases_th),
            "expected_group": expected_group,
            "polarity": polarity,
            "notes": None,
        }
        raw["fields"].append(new_field)
        self._atomic_write_json(self.canonical_fields_path, raw)
        return {
            "key": new_field["key"],
            "aliases_th": new_field["aliases_th"],
            "expected_group": new_field["expected_group"],
            "polarity": new_field["polarity"],
        }


def _safe_remove(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass
