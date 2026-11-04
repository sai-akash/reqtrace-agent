"""Set aside document text that looks like instructions to an AI system.

This is a rule-based first layer, not a complete defence. It misses paraphrases and
obfuscated text, and a false claim written as ordinary prose looks like evidence.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from reqtrace.documents import Section

PATTERNS = {
    "override_instruction": (
        r"\b(ignore|disregard|forget|override|bypass)\b.{0,40}"
        r"\b(instructions?|prompts?|rules?|polic(y|ies)|guidelines?)\b"
    ),
    "addressed_to_ai": (
        r"\b(system|developer)\s+(note|prompt|message|instructions?)\b"
        r"|\b(note|message|instructions?)\s+(to|for)\s+(the\s+)?"
        r"(ai|llm|model|assistant|agent|automated|chatbot|reviewer)\b"
        r"|\b(as|you are)\s+an?\s+(ai|llm|language model|assistant)\b"
    ),
    "tool_name": (
        r"\b(read_change_request|search_policy|verify_quote|save_finding"
        r"|request_approval|export_report|record_decision)\b"
    ),
    "verdict_command": (
        r"\b(mark|treat|label|classify|rate|report|consider)\b.{0,50}"
        r"\b(rules?|requirements?|findings?|verdicts?|checks?)\b.{0,50}"
        r"\b(supported|met|satisfied|passed|compliant|not[_ ]applicable)\b"
        r"|\b(insufficient_evidence|not_applicable)\b"
    ),
    "approval_command": r"\b(approve|export)\s+(this|the)\s+(change|request|report|review)\b",
}
COMPILED = {reason: re.compile(pattern, re.IGNORECASE) for reason, pattern in PATTERNS.items()}


@dataclass(frozen=True)
class QuarantinedText:
    section: str
    text: str
    reasons: tuple[str, ...]


def _sentences(text: str) -> list[str]:
    return [part for part in re.split(r"(?<=[.!?])\s+|\n+", text) if part.strip()]


def screen_sections(sections: Sequence[Section]) -> tuple[list[Section], list[QuarantinedText]]:
    """Return sections without flagged sentences. Unflagged sections stay byte-identical."""
    screened, quarantined = [], []
    for section in sections:
        text = section.text
        for sentence in _sentences(section.text):
            reasons = tuple(name for name, pattern in COMPILED.items() if pattern.search(sentence))
            if reasons:
                quarantined.append(QuarantinedText(section.title, sentence.strip(), reasons))
                text = text.replace(sentence, "", 1)
        if text != section.text:
            text = re.sub(r"[ \t]{2,}", " ", re.sub(r"\n{3,}", "\n\n", text)).strip()
        screened.append(Section(section.doc_id, section.title, text))
    return screened, quarantined
