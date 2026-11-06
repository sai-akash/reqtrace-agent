import pytest

from reqtrace.assessment import (
    AbstainAssessor,
    Citation,
    Finding,
    check_citations,
    citation_is_verbatim,
)
from reqtrace.documents import Rule, Section, load_change_request, load_rules
from reqtrace.evaluation import (
    evaluate_assessor,
    evaluate_retrieval,
    load_cases,
    macro_f1,
    score_ranking,
)
from reqtrace.retrieval import Bm25Retriever, EmbeddingRetriever, build_query

A = Section("D", "a", "alpha")
B = Section("D", "b", "beta")
C = Section("D", "c", "gamma")


class ReverseRetriever:
    def rank(self, query, sections):
        return list(reversed(sections))


class PerfectAssessor:
    """Answer from the labels, to test the scoring code."""

    def __init__(self, cases):
        self.answers = {c["rule"] + c["change_request"]: c for c in cases}

    def assess(self, rule, sections):
        case = self.answers[rule.rule_id + sections[0].doc_id]
        citations = tuple(Citation(e["section"], e["quote"]) for e in case["gold_evidence"])
        return Finding(case["gold_verdict"], citations)


def test_rules_and_change_requests_load():
    assert len(load_rules()) == 8
    assert len(load_change_request("CR-101")) == 9


def test_query_uses_rule_wording_without_its_id():
    for rule in load_rules().values():
        assert rule.rule_id not in build_query(rule)
        assert rule.title in build_query(rule)


def test_held_out_needs_confirmation():
    with pytest.raises(PermissionError):
        load_cases("held_out")
    assert len(load_cases("held_out", confirm_held_out=True)) == 16


def test_score_ranking_values():
    scores = score_ranking([A, B, C], {"b", "c"}, (1, 3))
    assert scores == {"recall@1": 0.0, "recall@3": 1.0, "mrr": 0.5}


def test_bm25_ranks_matching_section_first():
    assert Bm25Retriever().rank("beta", [A, B, C])[0] == B


def test_embedding_retriever_ranks_closest_section_first():
    vectors = {"q": [1.0, 0.0], "a\nalpha": [0.0, 1.0], "b\nbeta": [0.9, 0.1], "c\ngamma": [0.5, 0.5]}
    retriever = EmbeddingRetriever(embed=lambda texts: [vectors[t] for t in texts])
    assert [s.title for s in retriever.rank("q", [A, B, C])] == ["b", "c", "a"]


def test_retrieval_report_groups_by_change_request():
    report = evaluate_retrieval(load_cases("dev"), Bm25Retriever())
    assert report["cases"] == 24
    assert set(report["by_change_request"]) == {"CR-101", "CR-102", "CR-103"}
    assert 0 <= report["overall"]["recall@1"] <= report["overall"]["recall@3"] <= 1


def test_macro_f1_values():
    assert macro_f1(["supported", "contradicted"], ["supported", "contradicted"]) == 1.0
    assert macro_f1(["supported", "contradicted"], ["supported", "supported"]) == pytest.approx(1 / 3)


def test_citation_must_be_in_the_cited_section():
    assert citation_is_verbatim(Citation("a", "alpha"), [A, B])
    assert not citation_is_verbatim(Citation("b", "alpha"), [A, B])
    assert not citation_is_verbatim(Citation("a", ""), [A, B])


def test_citation_check_ignores_surrounding_whitespace_but_not_blank_quotes():
    assert citation_is_verbatim(Citation("a", " alpha\n"), [A])
    assert not citation_is_verbatim(Citation("a", "   "), [A])


@pytest.mark.parametrize("verdict", ["supported", "contradicted", "not_applicable"])
def test_verdict_without_citations_is_downgraded(verdict):
    check = check_citations(Finding(verdict), [A])
    assert (check.verdict, check.downgrade_reason) == ("insufficient_evidence", "no_citations")


def test_one_unverified_quote_downgrades_the_verdict():
    citations = (Citation("a", "alpha"), Citation("b", "invented"))
    check = check_citations(Finding("supported", citations), [A, B])
    assert (check.verdict, check.downgrade_reason) == ("insufficient_evidence", "unverified_quote")


def test_quote_from_a_section_outside_the_context_is_unverified():
    check = check_citations(Finding("supported", (Citation("b", "beta"),)), [A])
    assert check.downgrade_reason == "unverified_quote"


def test_verified_citation_keeps_the_verdict():
    check = check_citations(Finding("contradicted", (Citation("a", "alpha"),)), [A])
    assert (check.verdict, check.downgrade_reason) == ("contradicted", None)


@pytest.mark.parametrize("verdict", ["insufficient_evidence", "error"])
def test_abstention_and_failed_calls_pass_through(verdict):
    check = check_citations(Finding(verdict), [A])
    assert (check.verdict, check.downgrade_reason) == (verdict, None)


def test_gold_evidence_passes_the_citation_check_on_both_splits():
    cases = load_cases("dev") + load_cases("held_out", confirm_held_out=True)
    for case in cases:
        citations = tuple(Citation(e["section"], e["quote"]) for e in case["gold_evidence"])
        check = check_citations(
            Finding(case["gold_verdict"], citations), load_change_request(case["change_request"])
        )
        assert check.verdict == case["gold_verdict"], case["case_id"]


class FixedAssessor:
    def __init__(self, finding):
        self.finding = finding

    def assess(self, rule, sections):
        return self.finding


def test_report_shows_raw_and_checked_scores_and_downgrade_effects():
    dev = load_cases("dev")
    cases = [
        next(case for case in dev if case["gold_verdict"] == "supported"),
        next(case for case in dev if case["gold_verdict"] == "insufficient_evidence"),
    ]
    report = evaluate_assessor(cases, FixedAssessor(Finding("supported")), "oracle")
    assert report["raw"]["verdict_accuracy"] == 0.5
    assert report["checked"]["verdict_accuracy"] == 0.5
    assert report["citation_check"] == {
        "downgraded": 2,
        "no_citations": 2,
        "unverified_quote": 0,
        "abstentions_with_unverified_quotes": 0,
        "fixed_wrong_verdict": 1,
        "changed_correct_verdict": 1,
    }
    row = report["details"][0]
    assert (row["raw_verdict"], row["checked_verdict"]) == ("supported", "insufficient_evidence")
    assert row["downgrade_reason"] == "no_citations"


def test_invented_quote_is_flagged_and_earns_no_section_credit():
    case = load_cases("dev")[0]
    section = case["gold_evidence"][0]["section"]
    finding = Finding(case["gold_verdict"], (Citation(section, "An invented quote."),))
    report = evaluate_assessor([case], FixedAssessor(finding), "oracle")
    assert report["citation_verbatim_rate"] == 0
    assert report["gold_section_citation_recall"] == 0
    assert report["details"][0]["citations"][0]["verbatim"] is False
    assert report["citation_check"]["unverified_quote"] == 1


def test_abstain_floor_scores_only_abstentions():
    cases = load_cases("dev")
    report = evaluate_assessor(cases, AbstainAssessor(), "oracle")
    assert report["checked"]["verdict_accuracy"] == pytest.approx(4 / 24)
    assert report["checked"]["abstention_recall"] == 1.0
    assert report["citation_check"]["downgraded"] == 0
    assert report["citation_verbatim_rate"] is None


def test_oracle_context_contains_gold_and_perfect_answers_score_fully():
    cases = load_cases("dev")
    report = evaluate_assessor(cases, PerfectAssessor(cases), "oracle")
    assert report["raw"]["verdict_macro_f1"] == 1.0
    assert report["checked"]["verdict_macro_f1"] == 1.0
    assert report["citation_check"]["downgraded"] == 0
    assert report["citation_verbatim_rate"] == 1.0
    assert report["gold_section_citation_recall"] == 1.0
    assert all(row["context_has_gold"] for row in report["details"])


def test_semantic_context_is_limited_to_top_k():
    seen = []

    class Recording(AbstainAssessor):
        def assess(self, rule, sections):
            seen.append(len(sections))
            return super().assess(rule, sections)

    evaluate_assessor(load_cases("dev")[:2], Recording(), "semantic", ReverseRetriever(), top_k=3)
    assert seen == [3, 3]


def test_semantic_needs_a_retriever():
    with pytest.raises(ValueError):
        evaluate_assessor(load_cases("dev"), AbstainAssessor(), "semantic")
