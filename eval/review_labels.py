"""Create a blind label review sheet and measure agreement with the gold labels."""

from __future__ import annotations

import argparse
import csv
import importlib.util
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "validate_cases", Path(__file__).with_name("validate_cases.py")
)
_validate_cases = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_validate_cases)

VERDICTS = _validate_cases.VERDICTS


def all_cases() -> list[dict]:
    return [case for cases in _validate_cases.load_splits().values() for case in cases]


def sample_cases(cases: list[dict], per_verdict: int = 4, seed: int = 7) -> list[dict]:
    """Sample evenly by verdict, always including the known ambiguous cases."""
    required = {"HIT-103-CHG-1", "HIT-103-SEC-1", "HIT-105-DAT-1"}
    rng = random.Random(seed)
    by_verdict: dict[str, list[dict]] = defaultdict(list)
    chosen = [case for case in cases if case["case_id"] in required]
    for case in cases:
        if case["case_id"] not in required:
            by_verdict[case["gold_verdict"]].append(case)
    for verdict in sorted(by_verdict):
        already = sum(case["gold_verdict"] == verdict for case in chosen)
        pool = by_verdict[verdict]
        chosen.extend(rng.sample(pool, min(max(per_verdict - already, 0), len(pool))))
    rng.shuffle(chosen)
    return chosen


def cohens_kappa(first: list[str], second: list[str]) -> float:
    if len(first) != len(second) or not first:
        raise ValueError("Label lists must be non-empty and the same length.")
    total = len(first)
    observed = sum(a == b for a, b in zip(first, second)) / total
    first_counts, second_counts = Counter(first), Counter(second)
    expected = sum(first_counts[k] * second_counts[k] for k in first_counts) / total**2
    return 1.0 if expected == 1 else (observed - expected) / (1 - expected)


def write_sheet(output: Path) -> int:
    rows = sample_cases(all_cases())
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["case_id", "change_request", "rule", "verdict"])
        for case in rows:
            writer.writerow([case["case_id"], case["change_request"], case["rule"], ""])
    print(f"Wrote {len(rows)} cases to {output}")
    return 0


def sheet_problems(rows: list[dict], expected_ids: set[str]) -> list[str]:
    """Return every reason a filled sheet can't be scored."""
    ids = [row["case_id"].strip() for row in rows]
    problems = [f"{case_id}: appears more than once" for case_id, n in Counter(ids).items() if n > 1]
    problems += [f"{case_id}: missing from the sheet" for case_id in sorted(expected_ids - set(ids))]
    problems += [f"{case_id}: not in the expected sample" for case_id in sorted(set(ids) - expected_ids)]
    problems += [
        f"{row['case_id'].strip()}: invalid verdict {row['verdict']!r}"
        for row in rows
        if row["verdict"].strip() not in VERDICTS
    ]
    return problems


def report_agreement(sheet: Path) -> int:
    cases = all_cases()
    gold = {case["case_id"]: case["gold_verdict"] for case in cases}
    expected_ids = {case["case_id"] for case in sample_cases(cases)}
    with sheet.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    problems = sheet_problems(rows, expected_ids)
    if problems:
        print("\n".join(problems))
        return 1

    for row in rows:
        row["case_id"] = row["case_id"].strip()

    reviewer = [row["verdict"].strip() for row in rows]
    labels = [gold[row["case_id"]] for row in rows]
    matches = sum(a == b for a, b in zip(reviewer, labels))
    print(f"Cases: {len(rows)}")
    print(f"Raw agreement: {matches}/{len(rows)} ({matches / len(rows):.0%})")
    print(f"Cohen's kappa: {cohens_kappa(labels, reviewer):.2f}")
    for row, label in zip(rows, labels):
        if row["verdict"].strip() != label:
            print(f"Disagreement: {row['case_id']}: reviewer={row['verdict'].strip()}, gold={label}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    sheet = commands.add_parser("sheet", help="write a blind review sheet")
    sheet.add_argument("--output", type=Path, default=Path("review_sheet.csv"))
    agreement = commands.add_parser("agreement", help="compare a filled sheet with the gold labels")
    agreement.add_argument("sheet", type=Path)
    args = parser.parse_args()
    return write_sheet(args.output) if args.command == "sheet" else report_agreement(args.sheet)


if __name__ == "__main__":
    sys.exit(main())
