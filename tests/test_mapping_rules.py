import json
from pathlib import Path

import pytest

from models import load_mapping_rules

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MAPPING_RULES_PATH = PROJECT_ROOT / "mapping_rules.json"


def test_loads_the_real_mapping_rules_file():
    rules = load_mapping_rules(MAPPING_RULES_PATH)
    assert rules.min_confidence == 0.80


def test_rejects_out_of_range_min_confidence(tmp_path):
    bad_path = tmp_path / "mapping_rules.json"
    bad_path.write_text(json.dumps({"min_confidence": 1.5}), encoding="utf-8")

    with pytest.raises(ValueError):
        load_mapping_rules(bad_path)


def test_rejects_negative_min_confidence(tmp_path):
    bad_path = tmp_path / "mapping_rules.json"
    bad_path.write_text(json.dumps({"min_confidence": -0.1}), encoding="utf-8")

    with pytest.raises(ValueError):
        load_mapping_rules(bad_path)


def test_rejects_missing_key(tmp_path):
    bad_path = tmp_path / "mapping_rules.json"
    bad_path.write_text(json.dumps({}), encoding="utf-8")

    with pytest.raises(ValueError):
        load_mapping_rules(bad_path)


def test_rejects_missing_file(tmp_path):
    missing_path = tmp_path / "does_not_exist.json"

    with pytest.raises(ValueError):
        load_mapping_rules(missing_path)
