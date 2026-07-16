"""Pydantic models + loaders for configs/<company>.json and sso_rule.json.

Validating on load means a typo in a config (bad sign, unknown canonical key,
duplicate field, missing salary_per_period) fails immediately at load time
instead of surfacing later as a silent miscalculation.
"""

import json
from decimal import Decimal
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, ValidationInfo, field_validator, model_validator

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CANONICAL_FIELDS_PATH = _PROJECT_ROOT / "canonical_fields.json"


class Component(BaseModel):
    key: str
    sign: Literal["+", "-"]
    required: bool


class CompanyConfig(BaseModel):
    company_id: str
    display_name: str
    version: int
    components: list[Component]

    @model_validator(mode="after")
    def _check_components(self) -> "CompanyConfig":
        keys = [c.key for c in self.components]
        duplicates = {k for k in keys if keys.count(k) > 1}
        if duplicates:
            raise ValueError(
                f"{self.company_id!r} config has duplicate component key(s): {sorted(duplicates)}"
            )

        salary_components = [c for c in self.components if c.key == "salary_per_period"]
        if len(salary_components) != 1:
            raise ValueError(
                f"{self.company_id!r} config must have exactly one 'salary_per_period' "
                f"component, found {len(salary_components)}"
            )
        if not salary_components[0].required:
            raise ValueError(
                f"{self.company_id!r} config's 'salary_per_period' component must be required: true"
            )
        return self


class SsoRule(BaseModel):
    rate: Decimal
    ceiling: Decimal

    @field_validator("rate", "ceiling")
    @classmethod
    def _must_be_positive(cls, value: Decimal, info: ValidationInfo) -> Decimal:
        if value <= 0:
            raise ValueError(f"sso_rule.{info.field_name} must be a positive number, got {value}")
        return value


def load_canonical_keys(path: Path = DEFAULT_CANONICAL_FIELDS_PATH) -> set[str]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return {field["key"] for field in data["fields"]}


def load_company_config(
    path: str | Path,
    canonical_keys: Optional[set[str]] = None,
) -> CompanyConfig:
    """Read one configs/<company>.json, validate it, and cross-check every
    component key against canonical_fields.json. Raises ValueError with a
    clear message on any structural or referential problem."""
    path = Path(path)
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)

    try:
        config = CompanyConfig.model_validate(raw)
    except Exception as exc:
        raise ValueError(f"invalid company config {path}: {exc}") from exc

    if canonical_keys is None:
        canonical_keys = load_canonical_keys()

    unknown = sorted({c.key for c in config.components} - canonical_keys)
    if unknown:
        raise ValueError(
            f"{path}: component key(s) {unknown} are not defined in canonical_fields.json"
        )

    return config


def load_sso_rule(path: str | Path) -> SsoRule:
    path = Path(path)
    with open(path, encoding="utf-8") as f:
        raw = json.load(f, parse_float=Decimal)

    try:
        return SsoRule.model_validate(raw)
    except Exception as exc:
        raise ValueError(f"invalid sso rule {path}: {exc}") from exc
