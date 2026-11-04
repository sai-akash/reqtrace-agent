"""Compare two evaluation reports and list the cases that changed."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from reqtrace.evaluation import evidence_coverage, load_cases


def summarise(report: dict, cases: dict[str, dict]) -> dict:
    """Recalculate evidence metrics, so reports from before they existed still compare."""
    rows = report["details"]
    coverage = [evidence_coverage(cases[row["case_id"]], row["citations"]) for row in rows]
    complete = [covered == total for covered, total in coverage]
    no_citations = sum(not row["citations"] for row in rows)
    return {
        "Accuracy before check": report["raw"]["verdict_accuracy"],
        "Accuracy after check": report["checked"]["verdict_accuracy"],
        "Macro-F1 before check": report["raw"]["verdict_macro_f1"],
        "Macro-F1 after check": report["checked"]["verdict_macro_f1"],
        "Abstention precision after check": report["checked"]["abstention_precision"],
        "Abstention recall after check": report["checked"]["abstention_recall"],
        "Quotes found in the cited section": report["citation_verbatim_rate"],
        "Gold sections cited": report["gold_section_citation_recall"],
        "Gold facts covered": sum(c for c, _ in coverage) / sum(t for _, t in coverage),
        "Cases with all gold facts": sum(complete) / len(rows),
        "Correct after check with all gold facts": sum(
            done and row["checked_verdict"] == row["gold"] for done, row in zip(complete, rows)
        )
        / len(rows),
        "Cases with no citations": no_citations,
        "Downgraded: no citations": report["citation_check"]["no_citations"],
        "Downgraded: unverified quote": report["citation_check"]["unverified_quote"],
        "Downgrades that changed a correct verdict": report["citation_check"]["changed_correct_verdict"],
        "Downgrades that fixed a wrong verdict": report["citation_check"]["fixed_wrong_verdict"],
        "Failed calls": report["failed_calls"],
    }


def render(value) -> str:
    if value is None:
        return "n/a"
    return f"{value:.2f}" if isinstance(value, float) else str(value)


def compare(before: dict, after: dict) -> str:
    if before["split"] != "dev" or after["split"] != "dev":
        raise ValueError("Only dev reports can be compared.")
    cases = {case["case_id"]: case for case in load_cases("dev")}
    first, second = summarise(before, cases), summarise(after, cases)
    lines = ["| Metric | Before | After |", "|---|---:|---:|"]
    lines += [f"| {key} | {render(first[key])} | {render(second[key])} |" for key in first]
    changes = [
        f"- `{old['case_id']}` (gold `{old['gold']}`): `{old['raw_verdict']}` -> `{new['raw_verdict']}`"
        for old, new in zip(before["details"], after["details"])
        if old["raw_verdict"] != new["raw_verdict"]
    ]
    lines += ["", "Raw verdicts that changed:", *(changes or ["- None"])]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("before", type=Path)
    parser.add_argument("after", type=Path)
    args = parser.parse_args()
    print(compare(*(json.loads(path.read_text(encoding="utf-8")) for path in (args.before, args.after))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
