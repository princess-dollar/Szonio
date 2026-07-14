from typing import Any, Literal, Optional

from pydantic import BaseModel


class ColumnInfo(BaseModel):
    """One column as found in the real Excel header row.

    `index` is the 1-based column position in the sheet. It is the join key
    back into `WorkbookMetadata.sample_rows`, and is what lets near-duplicate
    column names (e.g. two "ชดเชยวันลา" columns in different groups) stay
    unambiguous downstream.
    """

    index: int
    group: Optional[str]
    name: str
    inferred_type: Literal["numeric", "text", "date"]


class WorkbookMetadata(BaseModel):
    """Frozen shape produced by excel_inspector.py. Phase 2 (LLM column
    mapping) consumes this directly, so changes here are a breaking change.
    """

    sheet_name: str
    header_row_index: int
    columns: list[ColumnInfo]
    sample_rows: list[dict[int, Any]]
    row_count: int
    ground_truth: list[ColumnInfo]
