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
import secrets
import tempfile
from pathlib import Path
from typing import Any, Iterator, Optional

from models.company_config import CompanyConfig, load_canonical_keys, load_company_config

PROJECT_ROOT = Path(__file__).resolve().parent.parent

_ADDABLE_POLARITIES = {"income", "deduction"}

# company_id / field key are opaque internal references, never shown to or
# entered by admins (they type only Thai display names). We mint a short
# random slug and collision-check it; 3 bytes -> 6 hex chars.
_GENERATED_ID_HEX_BYTES = 3
_MAX_ID_ATTEMPTS = 10000


def _normalize_thai_name(value: Optional[str]) -> str:
    """Fold a human name for duplicate detection: trim ends, collapse internal
    whitespace, and casefold. Uniqueness is enforced on this, not on the id."""
    return " ".join((value or "").split()).casefold()


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

    def _iter_company_raw(self) -> Iterator[dict]:
        """Yield the raw JSON of every company config, skipping unreadable
        ones. Used for name-based duplicate detection across ALL configs,
        including ones list_companies() hides (e.g. component-less drafts)."""
        if not self.config_dir.exists():
            return
        for path in sorted(self.config_dir.glob("*.json")):
            try:
                with open(path, encoding="utf-8") as f:
                    yield json.load(f)
            except (OSError, json.JSONDecodeError):
                continue

    def _generate_company_id(self) -> str:
        for _ in range(_MAX_ID_ATTEMPTS):
            candidate = "company_" + secrets.token_hex(_GENERATED_ID_HEX_BYTES)
            if not self._company_path(candidate).exists():
                return candidate
        raise ConfigError("ไม่สามารถสร้างรหัสบริษัทที่ไม่ซ้ำได้ กรุณาลองใหม่")

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

    def rename_company(self, company_id: str, display_name: str) -> CompanyConfig:
        """Change ONLY the display_name (a label). Does NOT bump version
        (version tracks formula changes that affect calculation), does NOT
        change company_id, and does NOT rename the file. The duplicate-name
        check excludes the company being renamed, so renaming to its own
        current name (or a case/whitespace variant) is allowed."""
        path = self._company_path(company_id)
        if not path.exists():
            raise ConfigNotFound(f"ไม่พบบริษัท '{company_id}'")

        normalized = _normalize_thai_name(display_name)
        if not normalized:
            raise ConfigValidation("กรุณาระบุชื่อบริษัท")

        for raw_existing in self._iter_company_raw():
            if raw_existing.get("company_id") == company_id:
                continue  # exclude the company being renamed itself
            if _normalize_thai_name(raw_existing.get("display_name", "")) == normalized:
                raise ConfigConflict("มีบริษัทชื่อนี้อยู่แล้ว")

        current = self.get_company(company_id)
        raw = {
            "company_id": company_id,
            "display_name": display_name.strip(),
            "version": current.version,  # unchanged: a rename is not a formula change
            "components": [
                {"key": c.key, "sign": c.sign, "required": c.required}
                for c in current.components
            ],
        }
        return self._validate_and_write_company(company_id, raw)

    def create_company(self, display_name: str, components: list[dict]) -> CompanyConfig:
        """Create a new company. The company_id is generated internally (an
        opaque reference, never shown to admins); uniqueness is enforced on the
        human display_name instead, case/whitespace-insensitively."""
        normalized = _normalize_thai_name(display_name)
        if not normalized:
            raise ConfigValidation("กรุณาระบุชื่อบริษัท")

        for raw_existing in self._iter_company_raw():
            if _normalize_thai_name(raw_existing.get("display_name", "")) == normalized:
                raise ConfigConflict("มีบริษัทชื่อนี้อยู่แล้ว")

        company_id = self._generate_company_id()
        raw = {
            "company_id": company_id,
            "display_name": display_name.strip(),
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

    def _generate_field_key(self, existing_keys: set[str]) -> str:
        for _ in range(_MAX_ID_ATTEMPTS):
            candidate = "field_" + secrets.token_hex(_GENERATED_ID_HEX_BYTES)
            if candidate not in existing_keys:
                return candidate
        raise ConfigError("ไม่สามารถสร้าง key ที่ไม่ซ้ำได้ กรุณาลองใหม่")

    def add_canonical_field(
        self,
        name_th_primary: str,
        aliases_th: list[str],
        expected_group: Optional[str],
        polarity: str,
    ) -> dict:
        """Add a canonical field. The key is generated internally (opaque, never
        shown to admins); the field is identified to humans by its Thai name.
        Uniqueness is enforced on the Thai name(s) — the primary name and every
        alias — case/whitespace-insensitively, against all existing aliases."""
        if polarity not in _ADDABLE_POLARITIES:
            raise ConfigValidation("polarity ต้องเป็น income หรือ deduction เท่านั้น")

        primary = (name_th_primary or "").strip()
        if not primary:
            raise ConfigValidation("กรุณาระบุชื่อฟิลด์ (ภาษาไทย)")

        # Primary name first, then extra aliases; trimmed, blanks dropped,
        # de-duplicated. This guarantees aliases_th[0] is always a human-facing
        # Thai label (the frontend and mapper both read aliases_th[0]).
        merged_aliases: list[str] = []
        seen_norm: set[str] = set()
        for name in [primary, *aliases_th]:
            cleaned = (name or "").strip()
            norm = _normalize_thai_name(cleaned)
            if not cleaned or norm in seen_norm:
                continue
            seen_norm.add(norm)
            merged_aliases.append(cleaned)

        raw = self._read_canonical_raw()

        existing_norm_aliases = {
            _normalize_thai_name(alias)
            for field in raw["fields"]
            for alias in field.get("aliases_th", [])
        }
        conflict = next(
            (a for a in merged_aliases if _normalize_thai_name(a) in existing_norm_aliases),
            None,
        )
        if conflict is not None:
            raise ConfigConflict(f"มีฟิลด์ที่ใช้ชื่อ '{conflict}' อยู่แล้ว")

        key = self._generate_field_key({f["key"] for f in raw["fields"]})
        new_field = {
            "key": key,
            "aliases_th": merged_aliases,
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
