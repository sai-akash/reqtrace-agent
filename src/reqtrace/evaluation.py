"""Load labelled cases, run experiments, and calculate metrics."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence

import yaml

from reqtrace.assessment import ABSTAIN, Assessor, Finding, check_citations, citation_is_verbatim
from reqtrace.documents import ROOT, Rule, Section, load_change_request, load_rules
from reqtrace.retrieval import Retriever, build_query

DATASETS_DIR = ROOT / "eval" / "datasets" / "healthcare_it"
VERDICTS = ("supported", "contradicted", "insufficient_evidence", "not_applicable")


def load_cases(split: str, confirm_held_out: bool = False) -> list[dict]:
    """Load one split. The held-out split needs an explicit confirmation."""
    if split == "held_out" and not confirm_held_out:
        raise PermissionError("The held-out split is reserved for the final evaluation.")
    path = DATASETS_DIR / f"{split}.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))["cases"]


def gold_sections(case: dict) -> set[str]:
    return {item["section"] for item in case["gold_evidence"]}


def score_ranking(ranking: Sequence[Section], gold: set[str], cutoffs: Iterable[int]) -> dict[str, float]:
    titles = [section.title for section in ranking]
    scores = {
        f"recall@{k}": len(gold & set(titles[:k])) / len(gold) if gold else 0.0
        for k in cutoffs
    }
    first = next((i for i, title in enumerate(titles, start=1) if title in gold), None)
    scores["mrr"] = 1 / first if first else 0.0
    return scores


def mean_scores(rows: Sequence[dict[str, float]]) -> dict[str, float]:
    if not rows:
        return {}
    return {key: sum(row[key] for row in rows) / len(rows) for key in rows[0]}


def evaluate_retrieval(
    cases: Sequence[dict],
    retriever: Retriever,
    rules: dict[str, Rule] | None = None,
    cutoffs: Iterable[int] = (1, 3),
) -> dict:
    """Rank each change request's sections using the rule text as the query."""
    rules = rules or load_rules()
    cutoffs = tuple(cutoffs)
    rows, by_change_request = [], defaultdict(list)
    for case in cases:
        sections = load_change_request(case["change_request"])
        ranking = retriever.rank(build_query(rules[case["rule"]]), sections)
        row = score_ranking(ranking, gold_sections(case), cutoffs)
        rows.append(row)
        by_change_request[case["change_request"]].append(row)
    return {
        "cases": len(rows),
        "overall": mean_scores(rows),
        "by_change_request": {cr: mean_scores(r) for cr, r in sorted(by_change_request.items())},
    }


def macro_f1(gold: Sequence[str], predicted: Sequence[str]) -> float:
    """Average F1 across the classes present in the gold labels."""
    classes = [verdict for verdict in VERDICTS if verdict in gold]
    if not classes:
        return 0.0
    scores = []
    for verdict in classes:
        tp = sum(g == verdict and p == verdict for g, p in zip(gold, predicted))
        fp = sum(g != verdict and p == verdict for g, p in zip(gold, predicted))
        fn = sum(g == verdict and p != verdict for g, p in zip(gold, predicted))
        scores.append(2 * tp / (2 * tp + fp + fn) if tp else 0.0)
    return sum(scores) / len(scores)


def _safe_ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _verdict_scores(gold: Sequence[str], predicted: Sequence[str]) -> dict:
    abstained = sum(p == ABSTAIN for p in predicted)
    correct_abstentions = sum(g == ABSTAIN and p == ABSTAIN for g, p in zip(gold, predicted))
    return {
        "verdict_accuracy": sum(g == p for g, p in zip(gold, predicted)) / len(gold),
        "verdict_macro_f1": macro_f1(gold, predicted),
        "abstention_precision": _safe_ratio(correct_abstentions, abstained),
        "abstention_recall": _safe_ratio(correct_abstentions, gold.count(ABSTAIN)),
    }


def evidence_coverage(case: dict, citations: Sequence[dict]) -> tuple[int, int]:
    """Count the gold facts covered by verified quotes from the same section.

    Quotes match if one contains the other. This approximates completeness: it
    can't recognise a different quote that states the same fact.
    """
    verified = [c for c in citations if c["verbatim"]]
    covered = sum(
        any(
            c["section"] == gold["section"]
            and (c["quote"].strip() in gold["quote"] or gold["quote"] in c["quote"])
            for c in verified
        )
        for gold in case["gold_evidence"]
    )
    return covered, len(case["gold_evidence"])


def evaluate_assessor(
    cases: Sequence[dict],
    assessor: Assessor,
    experiment: str,
    retriever: Retriever | None = None,
    top_k: int = 3,
    rules: dict[str, Rule] | None = None,
) -> dict:
    """Score verdicts before and after the citation check, plus the citations.

    `oracle` gives the assessor the gold sections, which measures reasoning with
    perfect retrieval. `semantic` gives it the top-ranked sections instead.
    """
    if experiment not in {"oracle", "semantic"}:
        raise ValueError(f"Unknown experiment: {experiment}")
    if experiment == "semantic" and retriever is None:
        raise ValueError("The semantic experiment needs a retriever.")

    rules = rules or load_rules()
    gold, raw, checked, details = [], [], [], []
    verbatim = cited = sections_found = sections_expected = 0
    facts_covered = facts_expected = complete_cases = correct_and_complete = 0
    input_tokens = output_tokens = 0
    served_by: Counter[str] = Counter()
    downgrades: Counter[str] = Counter()

    for case in cases:
        all_sections = load_change_request(case["change_request"])
        expected = gold_sections(case)
        rule = rules[case["rule"]]
        if experiment == "oracle":
            context = [section for section in all_sections if section.title in expected]
        else:
            context = retriever.rank(build_query(rule), all_sections)[:top_k]

        error = None
        try:
            finding = assessor.assess(rule, context)
        except RuntimeError as exc:
            # A failed call stays in the denominator, so failures can't raise the score.
            finding, error = Finding("error"), str(exc)
        input_tokens += finding.input_tokens
        output_tokens += finding.output_tokens
        if finding.served_by:
            served_by[finding.served_by] += 1
        check = check_citations(finding, context)
        gold.append(case["gold_verdict"])
        raw.append(finding.verdict)
        checked.append(check.verdict)
        if check.downgrade_reason:
            downgrades[check.downgrade_reason] += 1
        citations = [
            {"section": c.section, "quote": c.quote, "verbatim": citation_is_verbatim(c, context)}
            for c in finding.citations
        ]
        verbatim += sum(c["verbatim"] for c in citations)
        cited += len(citations)
        # An invented quote doesn't count as finding the section.
        sections_found += len(expected & {c["section"] for c in citations if c["verbatim"]})
        sections_expected += len(expected)
        covered, total = evidence_coverage(case, citations)
        facts_covered += covered
        facts_expected += total
        complete_cases += covered == total
        correct_and_complete += covered == total and check.verdict == case["gold_verdict"]
        details.append(
            {
                "case_id": case["case_id"],
                "gold": case["gold_verdict"],
                "raw_verdict": finding.verdict,
                "checked_verdict": check.verdict,
                "downgrade_reason": check.downgrade_reason,
                "context_has_gold": expected <= {section.title for section in context},
                "citations": citations,
                "gold_facts_covered": covered,
                "gold_facts_expected": total,
                "error": error,
            }
        )

    changed = [(g, r, c) for g, r, c in zip(gold, raw, checked) if r != c]
    return {
        "experiment": experiment,
        "cases": len(cases),
        "raw": _verdict_scores(gold, raw),
        "checked": _verdict_scores(gold, checked),
        "citation_check": {
            "downgraded": len(changed),
            "no_citations": downgrades["no_citations"],
            "unverified_quote": downgrades["unverified_quote"],
            "fixed_wrong_verdict": sum(g == c for g, _, c in changed),
            "changed_correct_verdict": sum(g == r for g, r, _ in changed),
        },
        "citation_verbatim_rate": _safe_ratio(verbatim, cited),
        "gold_section_citation_recall": _safe_ratio(sections_found, sections_expected),
        "gold_fact_recall": _safe_ratio(facts_covered, facts_expected),
        "complete_evidence_rate": complete_cases / len(cases),
        "correct_with_complete_evidence": correct_and_complete / len(cases),
        "failed_calls": sum(row["error"] is not None for row in details),
        "served_by": dict(served_by),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "details": details,
    }
