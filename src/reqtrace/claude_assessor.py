"""Assess one policy rule against change request sections using the Claude API."""

from __future__ import annotations

from collections.abc import Sequence

import anthropic

from reqtrace.assessment import Citation, Finding
from reqtrace.documents import Rule, Section
from reqtrace.prompting import SYSTEM_PROMPT, AssessmentError, FindingOutput, build_user_message

DEFAULT_MODEL = "claude-opus-5-5"
DEFAULT_EFFORT = "medium"
FALLBACK_BETA = "server-side-fallback-2026-07-01"


class ClaudeAssessor:
    """A single-call assessor: no tools, retries on bad citations, or agent loop."""

    def __init__(
        self,
        client: anthropic.Anthropic | None = None,
        model: str = DEFAULT_MODEL,
        effort: str = DEFAULT_EFFORT,
    ) -> None:
        self.client = client or anthropic.Anthropic()
        self.model = model
        self.effort = effort

    def assess(self, rule: Rule, sections: Sequence[Section]) -> Finding:
        response = self.client.beta.messages.parse(
            model=self.model,
            max_tokens=16000,
            betas=[FALLBACK_BETA],
            fallbacks="default",
            output_config={"effort": self.effort},
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": build_user_message(rule, sections)}],
            output_format=FindingOutput,
        )
        if response.stop_reason != "end_turn" or response.parsed_output is None:
            raise AssessmentError(
                f"No usable finding for {rule.rule_id}: stop_reason={response.stop_reason}, "
                f"request_id={response._request_id}"
            )
        output = response.parsed_output
        return Finding(
            verdict=output.verdict,
            citations=tuple(Citation(c.section, c.quote) for c in output.citations),
            served_by=response.model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )
