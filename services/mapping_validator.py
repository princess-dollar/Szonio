"""Phase 3: the gate between Phase 2's LLM column mapping and Phase 4's
calculation engine. Answers one question — is this mapping trustworthy
enough to calculate from, or must a human look first? Two-tier decision
only: "pass" or "needs_review". No UI, no persistence, no calculation, no
business rule about money — only about whether we trust the column
identities enough to hand them to Phase 4.
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field

from models.column_mapping import ColumnMappingResult
from models.company_config import CompanyConfig
from models.mapping_rules import MappingRules


class ColumnRef(BaseModel):
    column_index: int
    column_name: str
    canonical_field: Optional[str] = None
    confidence: Optional[float] = None


class ValidationItem(BaseModel):
    code: str
    message_th: str
    fields: list[str] = Field(default_factory=list)
    columns: list[ColumnRef] = Field(default_factory=list)


class ValidationReport(BaseModel):
    company_id: str
    display_name: str
    decision: Literal["pass", "needs_review"]
    reasons: list[ValidationItem] = Field(default_factory=list)
    notes: list[ValidationItem] = Field(default_factory=list)


def validate_mapping(
    mapping_result: ColumnMappingResult,
    company_config: CompanyConfig,
    mapping_rules: MappingRules,
) -> ValidationReport:
    """Pure function: inputs in, ValidationReport out. No I/O."""
    mapped_columns_by_field: dict[str, list] = {}
    for mapping in mapping_result.mappings:
        if mapping.canonical_field is not None:
            mapped_columns_by_field.setdefault(mapping.canonical_field, []).append(mapping)

    required_fields = [c.key for c in company_config.components if c.required]
    referenced_fields = [c.key for c in company_config.components]
    optional_referenced_fields = [f for f in referenced_fields if f not in required_fields]

    reasons: list[ValidationItem] = []
    notes: list[ValidationItem] = []

    unmapped_required = sorted(f for f in required_fields if f not in mapped_columns_by_field)
    if unmapped_required:
        reasons.append(
            ValidationItem(
                code="REQUIRED_FIELD_UNMAPPED",
                message_th=(
                    "พบฟิลด์ที่จำเป็น (required) แต่ไม่มีคอลัมน์ใดแมปมาถึง "
                    "ไม่สามารถคำนวณต่อได้ กรุณาตรวจสอบไฟล์ Excel หรือ mapping ก่อน"
                ),
                fields=unmapped_required,
            )
        )

    low_confidence_columns = [
        ColumnRef(
            column_index=m.column_index,
            column_name=m.column_name,
            canonical_field=m.canonical_field,
            confidence=m.confidence,
        )
        for m in mapping_result.mappings
        if m.canonical_field is not None and m.confidence < mapping_rules.min_confidence
    ]
    if low_confidence_columns:
        reasons.append(
            ValidationItem(
                code="LOW_CONFIDENCE",
                message_th=(
                    f"พบ {len(low_confidence_columns)} คอลัมน์ที่ความมั่นใจในการแมป (confidence) "
                    f"ต่ำกว่าเกณฑ์ที่กำหนด ({mapping_rules.min_confidence:.2f})"
                ),
                columns=low_confidence_columns,
            )
        )

    duplicated_fields = sorted(
        field for field, cols in mapped_columns_by_field.items() if len(cols) > 1
    )
    if duplicated_fields:
        duplicate_columns = [
            ColumnRef(
                column_index=m.column_index,
                column_name=m.column_name,
                canonical_field=m.canonical_field,
                confidence=m.confidence,
            )
            for field in duplicated_fields
            for m in mapped_columns_by_field[field]
        ]
        reasons.append(
            ValidationItem(
                code="DUPLICATE_MAPPING",
                message_th=(
                    "พบฟิลด์ที่ถูกแมปมาจากหลายคอลัมน์พร้อมกัน "
                    "ต้องมีคอลัมน์เดียวต่อหนึ่งฟิลด์เท่านั้น"
                ),
                fields=duplicated_fields,
                columns=duplicate_columns,
            )
        )

    unmapped_optional = sorted(
        f for f in optional_referenced_fields if f not in mapped_columns_by_field
    )
    if unmapped_optional:
        notes.append(
            ValidationItem(
                code="OPTIONAL_FIELD_UNMAPPED",
                message_th=(
                    "ฟิลด์ที่บริษัทนี้อ้างถึงแต่ไม่บังคับ (optional) ต่อไปนี้ไม่มีคอลัมน์แมปมาถึง "
                    "จะถูกคำนวณเป็น 0 ในขั้นตอนคำนวณ"
                ),
                fields=unmapped_optional,
            )
        )

    decision: Literal["pass", "needs_review"] = "needs_review" if reasons else "pass"

    return ValidationReport(
        company_id=company_config.company_id,
        display_name=company_config.display_name,
        decision=decision,
        reasons=reasons,
        notes=notes,
    )


def _format_column(col: ColumnRef) -> str:
    field_str = f" -> {col.canonical_field}" if col.canonical_field else ""
    conf_str = f", confidence={col.confidence:.2f}" if col.confidence is not None else ""
    return f"'{col.column_name}' (index {col.column_index}){field_str}{conf_str}"


def _format_item(item: ValidationItem, index: int) -> list[str]:
    lines = [f"[{index}] {item.code}", item.message_th]
    if item.fields:
        lines.append(f"  ฟิลด์: {', '.join(item.fields)}")

    if item.code == "DUPLICATE_MAPPING":
        by_field: dict[str, list[ColumnRef]] = {}
        for col in item.columns:
            by_field.setdefault(col.canonical_field or "", []).append(col)
        for field, cols in by_field.items():
            col_list = ", ".join(f"'{c.column_name}' (index {c.column_index})" for c in cols)
            lines.append(f"    {field}: {col_list}")
    else:
        for col in item.columns:
            lines.append(f"  - {_format_column(col)}")

    lines.append("")
    return lines


def format_report_th(report: ValidationReport) -> str:
    """Turn a ValidationReport into a clear Thai text block a human can read
    when the pipeline stops: what happened, grouped by reason, with the
    specific columns/fields and confidence scores involved."""
    status_th = "ผ่าน (PASS)" if report.decision == "pass" else "ต้องตรวจสอบก่อนคำนวณ (NEEDS_REVIEW)"

    lines: list[str] = []
    lines.append("=== ผลการตรวจสอบ Column Mapping ===")
    lines.append(f"บริษัท: {report.company_id} ({report.display_name})")
    lines.append(f"สถานะ: {status_th}")
    lines.append("")

    lines.append("--- เหตุผลที่ต้องหยุด (บังคับต้องแก้ก่อนคำนวณ) ---")
    if not report.reasons:
        lines.append("(ไม่มี)")
        lines.append("")
    else:
        for i, reason in enumerate(report.reasons, start=1):
            lines.extend(_format_item(reason, i))

    lines.append("--- หมายเหตุ (ไม่บังคับต้องแก้ ไม่กระทบสถานะ) ---")
    if not report.notes:
        lines.append("(ไม่มี)")
    else:
        for i, note in enumerate(report.notes, start=1):
            lines.extend(_format_item(note, i))

    return "\n".join(lines).rstrip() + "\n"
