"""Phase 5: the one function that runs the whole pipeline end to end,
wiring Phases 1-4 in order. Python owns the whole flow — the LLM's only
involvement is the single column-mapping call in step 3 (Phase 2).
"""

import json
from pathlib import Path
from typing import Optional, Literal

from pydantic import BaseModel

from excel_inspector import inspect_workbook, read_employee_rows
from integrations.llm_gateway_client import LlmGatewayClient
from models import (
    load_canonical_keys,
    load_company_config,
    load_mapping_rules,
    load_sso_rule,
    validate_column_mapping_response,
)
from services.mapping_validator import format_report_th, validate_mapping
from services.result_builder import CompanyResult, build_company_result

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CANONICAL_FIELDS_PATH = PROJECT_ROOT / "canonical_fields.json"
SSO_RULE_PATH = PROJECT_ROOT / "sso_rule.json"
MAPPING_RULES_PATH = PROJECT_ROOT / "mapping_rules.json"
CONFIGS_DIR = PROJECT_ROOT / "configs"


class PipelineResult(BaseModel):
    status: Literal["calculated", "needs_review"]
    company_result: Optional[CompanyResult] = None
    review_report_th: Optional[str] = None


def _canonical_fields_payload_items(canonical_fields_path: Path) -> list[dict]:
    with open(canonical_fields_path, encoding="utf-8") as f:
        data = json.load(f)
    return [
        {
            "key": field["key"],
            "aliases_th": field["aliases_th"],
            "expected_group": field["expected_group"],
            "polarity": field["polarity"],
        }
        for field in data["fields"]
    ]


def process_file(
    excel_path: str,
    company_id: str,
    llm_client: Optional[LlmGatewayClient] = None,
) -> PipelineResult:
    # 1. Excel Inspector: workbook structure + real employee rows (trailing
    #    Total row already excluded by both calls).
    metadata = inspect_workbook(excel_path)
    employee_rows = read_employee_rows(excel_path)

    # 2. This company's formula + the shared rule configs.
    canonical_keys = load_canonical_keys(CANONICAL_FIELDS_PATH)
    company_config = load_company_config(CONFIGS_DIR / f"{company_id}.json", canonical_keys)
    sso_rule = load_sso_rule(SSO_RULE_PATH)
    mapping_rules = load_mapping_rules(MAPPING_RULES_PATH)

    # 3. LLM column mapping (Phase 2), then validate the response shape.
    if llm_client is None:
        llm_client = LlmGatewayClient()

    columns_payload = [{"index": c.index, "group": c.group, "name": c.name} for c in metadata.columns]
    canonical_fields_payload = _canonical_fields_payload_items(CANONICAL_FIELDS_PATH)

    raw_mapping = llm_client.map_columns(columns_payload, canonical_fields_payload)
    mapping_result = validate_column_mapping_response(
        raw_mapping,
        valid_column_indexes={c["index"] for c in columns_payload},
        canonical_keys=canonical_keys,
    )

    # 4. Mapping validation gate (Phase 3). needs_review stops here -- no
    #    calculation, no output file.
    validation_report = validate_mapping(mapping_result, company_config, mapping_rules)
    if validation_report.decision == "needs_review":
        return PipelineResult(
            status="needs_review",
            review_report_th=format_report_th(validation_report),
        )

    # 5-6. Calculate every employee (Phase 4) and aggregate (Result Builder).
    company_result = build_company_result(employee_rows, company_config, mapping_result, sso_rule)

    return PipelineResult(status="calculated", company_result=company_result)
