import copy
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("validate_cases", ROOT / "eval" / "validate_cases.py")
validate_cases = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validate_cases)


@pytest.fixture
def splits():
    return copy.deepcopy(validate_cases.load_splits())


@pytest.fixture
def rule_ids():
    return validate_cases.load_rule_ids()


def test_dataset_is_valid(splits, rule_ids):
    assert validate_cases.validate(splits, rule_ids) == []


def test_dataset_covers_every_rule_for_every_change_request(splits, rule_ids):
    assert len(rule_ids) == 8
    assert len(splits["dev"]) == 24
    assert len(splits["held_out"]) == 16


def test_rejects_quote_not_in_document(splits, rule_ids):
    splits["dev"][0]["gold_evidence"][0]["quote"] = "This sentence isn't in the document."
    assert any("quote not found" in e for e in validate_cases.validate(splits, rule_ids))


def test_rejects_quote_from_wrong_section(splits, rule_ids):
    splits["dev"][0]["gold_evidence"][0]["section"] = "5. Rollback"
    assert any("quote not found" in e for e in validate_cases.validate(splits, rule_ids))


def test_rejects_unknown_verdict(splits, rule_ids):
    splits["dev"][0]["gold_verdict"] = "compliant"
    assert any("unknown verdict" in e for e in validate_cases.validate(splits, rule_ids))


def test_rejects_held_out_document_in_dev(splits, rule_ids):
    splits["dev"].append(copy.deepcopy(splits["held_out"][0]))
    errors = validate_cases.validate(splits, rule_ids)
    assert any("doesn't belong in split" in e for e in errors)


def test_rejects_missing_case(splits, rule_ids):
    splits["dev"].pop()
    assert any("missing case" in e for e in validate_cases.validate(splits, rule_ids))


def test_rejects_verdict_without_citation(splits, rule_ids):
    splits["dev"][0]["gold_evidence"] = []
    assert any("needs at least one citation" in e for e in validate_cases.validate(splits, rule_ids))
