import json
from pathlib import Path

import pytest

from models import load_canonical_keys, load_company_config, load_sso_rule

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIGS_DIR = PROJECT_ROOT / "configs"
CANONICAL_FIELDS_PATH = PROJECT_ROOT / "canonical_fields.json"
SSO_RULE_PATH = PROJECT_ROOT / "sso_rule.json"

CONFIG_PATHS = sorted(CONFIGS_DIR.glob("*.json"))


@pytest.fixture(scope="module")
def canonical_keys():
    return load_canonical_keys(CANONICAL_FIELDS_PATH)


def test_at_least_one_config_exists():
    assert CONFIG_PATHS, f"no config files found in {CONFIGS_DIR}"


@pytest.mark.parametrize("path", CONFIG_PATHS, ids=lambda p: p.stem)
def test_config_loads_without_raising(path, canonical_keys):
    load_company_config(path, canonical_keys)


@pytest.mark.parametrize("path", CONFIG_PATHS, ids=lambda p: p.stem)
def test_config_components_reference_real_canonical_keys(path, canonical_keys):
    config = load_company_config(path, canonical_keys)
    for component in config.components:
        assert component.key in canonical_keys, (
            f"{path}: component key {component.key!r} not found in canonical_fields.json"
        )


def test_sso_rule_loads_and_is_positive():
    rule = load_sso_rule(SSO_RULE_PATH)
    assert rule.rate > 0
    assert rule.ceiling > 0


def test_canonical_fields_file_is_well_formed():
    with open(CANONICAL_FIELDS_PATH, encoding="utf-8") as f:
        data = json.load(f)
    keys = [field["key"] for field in data["fields"]]
    assert keys, "canonical_fields.json has no fields"
    assert len(keys) == len(set(keys)), "canonical_fields.json has duplicate keys"
