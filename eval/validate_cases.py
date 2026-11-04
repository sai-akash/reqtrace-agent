"""Check that the labelled cases are complete and match the source documents.

This validates the dataset's structure and citations. It can't tell whether a
label is the right judgment, which still needs human review.
"""

from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
DOMAIN = ROOT / "domains" / "healthcare_it"
DATASETS = ROOT / "eval" / "datasets" / "healthcare_it"
POLICY = DOMAIN / "policy" / "FCN-IT-POL-07.md"
CHANGE_REQUESTS = DOMAIN / "change_requests"

VERDICTS = {"supported", "contradicted", "insufficient_evidence", "not_applicable"}
EXPECTED_SPLITS = {
    "dev": {"CR-101", "CR-102", "CR-103"},
    "held_out": {"CR-104", "CR-105"},
}


def parse_sections(text: str) -> dict[str, str]:
    """Return a mapping of each level-2 heading to its body text."""
    parts = re.split(r"^## (.+)$", text, flags=re.MULTILINE)
    return {parts[i].strip(): parts[i + 1] for i in range(1, len(parts) - 1, 2)}


def load_rule_ids(policy_path: Path = POLICY) -> set[str]:
    sections = parse_sections(policy_path.read_text(encoding="utf-8"))
    return {heading.split()[0] for heading in sections}


def load_splits(datasets_dir: Path = DATASETS) -> dict[str, list[dict]]:
    splits: dict[str, list[dict]] = {}
    for name in EXPECTED_SPLITS:
        data = yaml.safe_load((datasets_dir / f"{name}.yaml").read_text(encoding="utf-8"))
        splits[name] = data["cases"]
    return splits


def validate(
    splits: dict[str, list[dict]],
    rule_ids: set[str],
    change_requests_dir: Path = CHANGE_REQUESTS,
) -> list[str]:
    """Return a list of problems. An empty list means the dataset is valid."""
    errors: list[str] = []
    seen_ids: Counter[str] = Counter()
    seen_pairs: set[tuple[str, str]] = set()

    for split, cases in splits.items():
        for case in cases:
            case_id = case.get("case_id", "<missing id>")
            seen_ids[case_id] += 1
            cr = case.get("change_request")
            rule = case.get("rule")
            verdict = case.get("gold_verdict")
            seen_pairs.add((cr, rule))

            if cr not in EXPECTED_SPLITS[split]:
                errors.append(f"{case_id}: {cr} doesn't belong in split '{split}'")
            if rule not in rule_ids:
                errors.append(f"{case_id}: unknown rule {rule}")
            if verdict not in VERDICTS:
                errors.append(f"{case_id}: unknown verdict {verdict}")
            if not str(case.get("rationale", "")).strip():
                errors.append(f"{case_id}: missing rationale")

            evidence = case.get("gold_evidence") or []
            if not evidence and verdict != "insufficient_evidence":
                errors.append(f"{case_id}: '{verdict}' needs at least one citation")

            path = change_requests_dir / f"{cr}.md"
            if not path.exists():
                errors.append(f"{case_id}: missing document {path.name}")
                continue
            sections = parse_sections(path.read_text(encoding="utf-8"))
            for item in evidence:
                section = item.get("section")
                quote = item.get("quote", "")
                if section not in sections:
                    errors.append(f"{case_id}: section '{section}' not found in {cr}")
                elif not quote or quote not in sections[section]:
                    errors.append(f"{case_id}: quote not found in {cr} '{section}': {quote!r}")

    for case_id, count in seen_ids.items():
        if count > 1:
            errors.append(f"{case_id}: duplicate case ID")

    for split, crs in EXPECTED_SPLITS.items():
        for cr in crs:
            for rule in rule_ids:
                if (cr, rule) not in seen_pairs:
                    errors.append(f"missing case for {cr} and {rule} in split '{split}'")

    return errors


def main() -> int:
    splits = load_splits()
    errors = validate(splits, load_rule_ids())

    for split, cases in splits.items():
        counts = Counter(case["gold_verdict"] for case in cases)
        summary = ", ".join(f"{verdict}={counts[verdict]}" for verdict in sorted(VERDICTS))
        print(f"{split}: {len(cases)} cases ({summary})")

    if errors:
        print(f"\n{len(errors)} problem(s) found:")
        for error in errors:
            print(f"- {error}")
        return 1

    print("\nAll cases are valid.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
