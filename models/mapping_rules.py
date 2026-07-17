"""Pydantic model + loader for mapping_rules.json — the confidence
threshold that gates Phase 3's mapping validation. Kept separate from
sso_rule.json: this is about trusting a column mapping, not about money.
"""

import json
from pathlib import Path

from pydantic import BaseModel, Field


class MappingRules(BaseModel):
    min_confidence: float = Field(ge=0.0, le=1.0)


def load_mapping_rules(path: str | Path) -> MappingRules:
    path = Path(path)
    if not path.exists():
        raise ValueError(f"mapping rules file not found: {path}")

    with open(path, encoding="utf-8") as f:
        raw = json.load(f)

    try:
        return MappingRules.model_validate(raw)
    except Exception as exc:
        raise ValueError(f"invalid mapping rules {path}: {exc}") from exc
