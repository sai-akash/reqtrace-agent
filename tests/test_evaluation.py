import pytest

from reqtrace.assessment import AbstainAssessor, Citation, Finding, citation_is_verbatim
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


def test_abstain_floor_scores_only_abstentions():
    cases = load_cases("dev")
    report = evaluate_assessor(cases, AbstainAssessor(), "oracle")
    assert report["verdict_accuracy"] == pytest.approx(4 / 24)
    assert report["abstention_recall"] == 1.0
    assert report["citation_verbatim_rate"] is None


def test_oracle_context_contains_gold_and_perfect_answers_score_fully():
    cases = load_cases("dev")
    report = evaluate_assessor(cases, PerfectAssessor(cases), "oracle")
    assert report["verdict_macro_f1"] == 1.0
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
