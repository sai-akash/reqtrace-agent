"""The interface an assessor must meet, plus a non-LLM floor baseline."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol

from reqtrace.documents import Rule, Section


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


class Assessor(Protocol):
    def assess(self, rule: Rule, sections: Sequence[Section]) -> Finding:
        ...


class AbstainAssessor:
    """Always abstain. Any real assessor should beat this score."""

    def assess(self, rule: Rule, sections: Sequence[Section]) -> Finding:
        return Finding("insufficient_evidence")


def citation_is_verbatim(citation: Citation, sections: Sequence[Section]) -> bool:
    """Check that the quote appears in the section it cites."""
    return bool(citation.quote) and any(
        section.title == citation.section and citation.quote in section.text
        for section in sections
    )
