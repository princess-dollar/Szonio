"""Pydantic models for Phase 4's calculation output. Decimal fields keep
full precision in Python (model_dump()) and serialize as strings in JSON
mode (model_dump(mode="json") / model_dump_json()) — pydantic's default
behavior for Decimal, verified rather than assumed, so a contribution never
picks up float drift on the way out.
"""

from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel


class ComponentAmount(BaseModel):
    """One line of the audit trail: which canonical field, which real column
    it came from (None if the field had no mapped column and was treated as
    0), its sign in the company's formula, and the unsigned magnitude read
    from the cell.
    """

    canonical_field: str
    column_index: Optional[int]
    column_name: Optional[str]
    sign: Literal["+", "-"]
    amount: Decimal


class EmployeeResult(BaseModel):
    base: Decimal
    contribution: Decimal
    breakdown: list[ComponentAmount]
