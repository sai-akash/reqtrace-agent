"""The interface an assessor must meet, plus a non-LLM floor baseline."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol

from reqtrace.documents import Rule, Section

ABSTAIN = "insufficient_evidence"
VERDICTS_NEEDING_EVIDENCE = frozenset({"supported", "contradicted", "not_applicable"})


@dataclass(frozen=True)
class Citation:
    section: str
    quote: str


@dataclass(frozen=True)
class Finding:
    verdict: str
    citations: tuple[Citation, ...] = field(default_factory=tuple)
    served_by: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass(frozen=True)
class CitationCheck:
    verdict: str
    downgrade_reason: str | None = None
    unverified_quotes: int = 0


class Assessor(Protocol):
    def assess(self, rule: Rule, sections: Sequence[Section]) -> Finding:
        ...


class AbstainAssessor:
    """Always abstain. Any real assessor should beat this score."""

    def assess(self, rule: Rule, sections: Sequence[Section]) -> Finding:
        return Finding(ABSTAIN)


def citation_is_verbatim(citation: Citation, sections: Sequence[Section]) -> bool:
    """Check that the quote appears in the section it cites."""
    quote = citation.quote.strip()
    return bool(quote) and any(
        section.title == citation.section and quote in section.text for section in sections
    )


def check_citations(finding: Finding, sections: Sequence[Section]) -> CitationCheck:
    """Downgrade a verdict that has no citations or has a quote not found in its section.

    Only `insufficient_evidence` may have no citations. It can't be downgraded further,
    so its unverified quotes are counted instead. This shows that the quotes exist,
    not that they prove the verdict or cover every fact it relies on.
    """
    unverified = sum(not citation_is_verbatim(c, sections) for c in finding.citations)
    if finding.verdict not in VERDICTS_NEEDING_EVIDENCE:
        return CitationCheck(finding.verdict, unverified_quotes=unverified)
    if not finding.citations:
        return CitationCheck(ABSTAIN, "no_citations")
    if unverified:
        return CitationCheck(ABSTAIN, "unverified_quote", unverified)
    return CitationCheck(finding.verdict)
