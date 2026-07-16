"""Validates the LLM Gateway's column-mapping response (see
integrations/llm_gateway_client.py). The LLM only proposes which canonical
field a column represents — everything here is plain Python cross-checking
that proposal against what we know to be true (real input columns, real
canonical fields), not a business decision.
"""

from typing import Optional

from pydantic import BaseModel, Field


class ColumnMapping(BaseModel):
    column_index: int
    column_name: str
    canonical_field: Optional[str]
    confidence: float = Field(ge=0.0, le=1.0)


class ColumnMappingResult(BaseModel):
    mappings: list[ColumnMapping]
    unmapped_fields: list[str] = Field(default_factory=list)


def validate_column_mapping_response(
    raw: dict,
    valid_column_indexes: set[int],
    canonical_keys: set[str],
) -> ColumnMappingResult:
    """Validate the Gateway's raw parsed JSON against what we actually sent it:
    every column_index must be one we asked about, every non-null
    canonical_field must be a real canonical key, and confidence must be in
    0..1. Raises ValueError with a clear message on any mismatch — never
    silently repairs a bad response.

    unmapped_fields is a plain set-difference computed here in Python, not
    something the LLM returns: canonical_keys minus every canonical_field the
    LLM actually matched to a column.
    """
    try:
        result = ColumnMappingResult.model_validate(raw)
    except Exception as exc:
        raise ValueError(f"invalid column mapping response: {exc}") from exc

    for mapping in result.mappings:
        if mapping.column_index not in valid_column_indexes:
            raise ValueError(
                f"column_index {mapping.column_index} was not among the columns sent to the Gateway"
            )
        if mapping.canonical_field is not None and mapping.canonical_field not in canonical_keys:
            raise ValueError(
                f"canonical_field {mapping.canonical_field!r} is not defined in canonical_fields.json"
            )

    matched_fields = {m.canonical_field for m in result.mappings if m.canonical_field is not None}
    result.unmapped_fields = sorted(canonical_keys - matched_fields)

    return result
