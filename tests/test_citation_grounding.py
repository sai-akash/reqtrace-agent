"""Regression tests for known citation failures, using small synthetic fixtures."""

from reqtrace.assessment import Citation, Finding, check_citations
from reqtrace.documents import Rule, Section
from reqtrace.evaluation import evaluate_assessor, evidence_coverage, load_cases
from reqtrace.prompting import MAX_CITATIONS, build_output_schema

SYSTEM = Section("CR-X", "2. System", "Classification: Tier 1.")
ROLLBACK = Section("CR-X", "5. Rollback", "Restore the package. Estimated rollback time: 45 minutes.")
SECTIONS = [SYSTEM, ROLLBACK]


def supported(*citations):
    return Finding("supported", tuple(citations))


def test_correct_quote_in_the_wrong_section_is_rejected():
    finding = supported(Citation("2. System", "Estimated rollback time: 45 minutes."))
    assert check_citations(finding, SECTIONS).downgrade_reason == "unverified_quote"


def test_correct_section_with_an_invented_quote_is_rejected():
    finding = supported(Citation("5. Rollback", "Estimated rollback time: 30 minutes."))
    assert check_citations(finding, SECTIONS).downgrade_reason == "unverified_quote"


def test_quote_from_the_rule_text_is_rejected():
    finding = supported(Citation("CHG-2", "Rollback must not exceed 60 minutes."))
    assert check_citations(finding, SECTIONS).downgrade_reason == "unverified_quote"


def test_citations_from_several_sections_are_accepted():
    finding = supported(
        Citation("2. System", "Classification: Tier 1."),
        Citation("5. Rollback", "Estimated rollback time: 45 minutes."),
    )
    check = check_citations(finding, SECTIONS)
    assert (check.verdict, check.downgrade_reason) == ("supported", None)


def test_no_relevant_evidence_is_allowed_only_when_abstaining():
    assert check_citations(Finding("insufficient_evidence"), SECTIONS).downgrade_reason is None
    assert check_citations(supported(), SECTIONS).downgrade_reason == "no_citations"


def gold_case():
    return {
        "gold_evidence": [
            {"section": "5. Rollback", "quote": "Estimated rollback time: 45 minutes."},
            {"section": "2. System", "quote": "Classification: Tier 1."},
        ]
    }


def cited(section, quote, verbatim=True):
    return {"section": section, "quote": quote, "verbatim": verbatim}


def test_missing_tier_evidence_passes_the_check_but_lowers_coverage():
    citation = Citation("5. Rollback", "Estimated rollback time: 45 minutes.")
    assert check_citations(supported(citation), SECTIONS).downgrade_reason is None
    rows = [cited(citation.section, citation.quote)]
    assert evidence_coverage(gold_case(), rows) == (1, 2)


def test_coverage_accepts_quotes_that_contain_or_shorten_the_gold_quote():
    rows = [
        cited("5. Rollback", "Restore the package. Estimated rollback time: 45 minutes."),
        cited("2. System", "Tier 1"),
    ]
    assert evidence_coverage(gold_case(), rows) == (2, 2)


def test_coverage_ignores_unverified_quotes_and_wrong_sections():
    rows = [
        cited("5. Rollback", "Estimated rollback time: 45 minutes.", verbatim=False),
        cited("5. Rollback", "Classification: Tier 1."),
    ]
    assert evidence_coverage(gold_case(), rows) == (0, 2)


def test_real_quote_that_doesnt_justify_the_verdict_is_scored_as_wrong():
    class Assessor:
        def assess(self, rule, sections):
            return Finding("contradicted", (Citation(sections[0].title, sections[0].text),))

    case = next(c for c in load_cases("dev") if c["gold_verdict"] == "supported")
    report = evaluate_assessor([case], Assessor(), "oracle")
    assert report["citation_verbatim_rate"] == 1
    assert report["citation_check"]["downgraded"] == 0
    assert report["checked"]["verdict_accuracy"] == 0


def test_schema_limits_sections_and_citation_count():
    for branch in build_output_schema(SECTIONS)["anyOf"]:
        citations = branch["properties"]["citations"]
        assert citations["items"]["properties"]["section"]["enum"] == ["2. System", "5. Rollback"]
        assert citations["maxItems"] == MAX_CITATIONS


def test_schema_requires_citations_unless_abstaining():
    needs_evidence, abstain = build_output_schema(SECTIONS)["anyOf"]
    assert needs_evidence["properties"]["citations"]["minItems"] == 1
    assert "insufficient_evidence" not in needs_evidence["properties"]["verdict"]["enum"]
    assert "minItems" not in abstain["properties"]["citations"]
    assert abstain["properties"]["verdict"] == {"const": "insufficient_evidence"}


def test_schema_with_no_sections_can_only_abstain():
    schema = build_output_schema([])
    assert schema["properties"]["verdict"] == {"const": "insufficient_evidence"}
    assert schema["properties"]["citations"]["maxItems"] == 0
