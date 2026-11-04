"""The tools an agent can call during a review, and the approval state they enforce."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

from reqtrace.assessment import ABSTAIN, Citation, Finding, check_citations, citation_is_verbatim
from reqtrace.audit import AuditLog
from reqtrace.documents import (
    CHANGE_REQUESTS_DIR,
    Rule,
    Section,
    load_change_request,
    load_rules,
)
from reqtrace.retrieval import Bm25Retriever

VERDICTS = ("supported", "contradicted", ABSTAIN, "not_applicable")
NEEDS_FOLLOW_UP = frozenset({"contradicted", ABSTAIN})
AGENT = "agent"


class UnknownChangeRequestError(ValueError):
    """The requested change request doesn't exist, so no review can start."""


class ToolRefused(Exception):
    """A tool call isn't allowed. The refusal is logged and returned to the caller."""


@dataclass(frozen=True)
class SavedFinding:
    rule_id: str
    raw_verdict: str
    verdict: str
    downgrade_reason: str | None
    citations: tuple[dict, ...]
    follow_up_question: str


def _digest(content: object) -> str:
    encoded = json.dumps(content, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def known_change_requests(directory: Path = CHANGE_REQUESTS_DIR) -> set[str]:
    return {path.stem for path in directory.glob("CR-*.md")}


class ReviewSession:
    """One review of one change request against a fixed set of rules.

    Only `call_tool` is available to the model. `record_decision` is for a person and
    isn't in the tool registry, so the model has no way to reach it.
    """

    def __init__(
        self,
        change_request_id: str,
        audit: AuditLog,
        export_dir: Path,
        rules: dict[str, Rule] | None = None,
        sections: Sequence[Section] | None = None,
    ) -> None:
        if sections is None:
            if change_request_id not in known_change_requests():
                raise UnknownChangeRequestError(f"Unknown change request: {change_request_id!r}")
            sections = load_change_request(change_request_id)
        self.change_request_id = change_request_id
        self.audit = audit
        self.export_dir = export_dir
        self.rules = rules or load_rules()
        self.sections = list(sections)
        self.document_digest = _digest([asdict(section) for section in self.sections])
        self.findings: dict[str, SavedFinding] = {}
        self.state = "drafting"
        self.document_read = False
        self.approved_digest: str | None = None
        self.calls: list[dict] = []

    def findings_digest(self) -> str:
        return _digest(
            {
                "change_request": self.change_request_id,
                "document": self.document_digest,
                "findings": [asdict(self.findings[rule_id]) for rule_id in sorted(self.findings)],
            }
        )

    def missing_rules(self) -> list[str]:
        return [rule_id for rule_id in self.rules if rule_id not in self.findings]

    def missing_follow_ups(self) -> list[str]:
        return [
            rule_id
            for rule_id, finding in self.findings.items()
            if finding.verdict in NEEDS_FOLLOW_UP and not finding.follow_up_question
        ]

    def call_tool(self, name: str, arguments: object) -> dict:
        """Run a tool call from the model. Anything not allowed comes back as a refusal."""
        try:
            result = self._dispatch(name, arguments)
        except ToolRefused as refusal:
            self.calls.append({"tool": name, "arguments": arguments, "ok": False})
            self.audit.record(AGENT, name, {"arguments": arguments, "reason": str(refusal)}, "refused")
            return {"ok": False, "error": str(refusal)}
        self.calls.append({"tool": name, "arguments": arguments, "ok": True})
        self.audit.record(AGENT, name, {"arguments": arguments}, "ok")
        return {"ok": True} | result

    def _dispatch(self, name: str, arguments: object) -> dict:
        tool = TOOL_METHODS.get(name)
        if tool is None:
            raise ToolRefused(f"Unknown tool: {name}")
        if not isinstance(arguments, dict):
            raise ToolRefused(f"Arguments for {name} must be an object.")
        properties = TOOL_PARAMETERS[name]
        unexpected = set(arguments) - set(properties["properties"])
        missing = set(properties.get("required", [])) - set(arguments)
        if unexpected or missing:
            raise ToolRefused(
                f"Bad arguments for {name}: missing {sorted(missing)}, unexpected {sorted(unexpected)}."
            )
        return tool(self, **arguments)

    def _require_drafting(self, action: str) -> None:
        if self.state != "drafting":
            raise ToolRefused(f"Can't {action} while the review is {self.state}.")

    def read_change_request(self, change_request_id: str) -> dict:
        if change_request_id != self.change_request_id:
            raise ToolRefused(
                f"This review is for {self.change_request_id}, not {change_request_id!r}."
            )
        self.document_read = True
        return {
            "change_request_id": self.change_request_id,
            "document_digest": self.document_digest,
            "sections": [{"title": section.title, "text": section.text} for section in self.sections],
        }

    def search_policy(self, query: str) -> dict:
        query = str(query).strip()
        if not query:
            raise ToolRefused("The query can't be empty.")
        if query in self.rules:
            matches = [self.rules[query]]
        else:
            documents = [
                Section("policy", rule.rule_id, f"{rule.title}. {rule.text}") for rule in self.rules.values()
            ]
            matches = [self.rules[doc.title] for doc in Bm25Retriever().rank(query, documents)[:3]]
        return {"rules": [asdict(rule) for rule in matches]}

    def verify_quote(self, section: str, quote: str) -> dict:
        return {"verified": citation_is_verbatim(Citation(str(section), str(quote)), self.sections)}

    def save_finding(
        self,
        rule_id: str,
        verdict: str,
        citations: list,
        follow_up_question: str = "",
    ) -> dict:
        self._require_drafting("save a finding")
        if not self.document_read:
            raise ToolRefused("Read the change request before saving a finding.")
        if rule_id not in self.rules:
            raise ToolRefused(f"Unknown rule: {rule_id!r}. Expected one of {sorted(self.rules)}.")
        if verdict not in VERDICTS:
            raise ToolRefused(f"Invalid verdict: {verdict!r}. Expected one of {list(VERDICTS)}.")
        parsed = _parse_citations(citations)
        check = check_citations(Finding(verdict, parsed), self.sections)
        question = str(follow_up_question).strip()
        self.findings[rule_id] = SavedFinding(
            rule_id=rule_id,
            raw_verdict=verdict,
            verdict=check.verdict,
            downgrade_reason=check.downgrade_reason,
            citations=tuple(
                {
                    "section": citation.section,
                    "quote": citation.quote,
                    "verbatim": citation_is_verbatim(citation, self.sections),
                }
                for citation in parsed
            ),
            follow_up_question=question,
        )
        result = {
            "rule_id": rule_id,
            "saved_verdict": check.verdict,
            "downgrade_reason": check.downgrade_reason,
            "follow_up_required": check.verdict in NEEDS_FOLLOW_UP and not question,
            "rules_remaining": self.missing_rules(),
        }
        return result

    def request_approval(self) -> dict:
        self._require_drafting("request approval")
        if self.missing_rules():
            raise ToolRefused(f"Findings are missing for: {self.missing_rules()}.")
        if self.missing_follow_ups():
            raise ToolRefused(f"Follow-up questions are missing for: {self.missing_follow_ups()}.")
        self.state = "pending_approval"
        return {
            "status": self.state,
            "findings_digest": self.findings_digest(),
            "message": "A person will now review the findings. Stop here.",
        }

    def export_report(self) -> dict:
        if self.state != "approved":
            raise ToolRefused(f"Export needs human approval. The review is {self.state}.")
        if self.findings_digest() != self.approved_digest:
            raise ToolRefused("The findings changed after approval.")
        self.export_dir.mkdir(parents=True, exist_ok=True)
        path = self.export_dir / f"{self.change_request_id}_review.md"
        path.write_text(self._render_report(), encoding="utf-8")
        self.state = "exported"
        return {"status": self.state, "report": str(path)}

    def record_decision(self, decision: str, reviewer: str, note: str = "") -> str:
        """Record a person's decision. This must never be exposed as a model tool."""
        if decision not in {"approved", "rejected"}:
            raise ValueError(f"Invalid decision: {decision!r}")
        if not reviewer.strip():
            raise ValueError("A decision needs the reviewer's name.")
        if self.state != "pending_approval":
            raise ValueError(f"Can't record a decision while the review is {self.state}.")
        digest = self.findings_digest()
        self.state = decision
        self.approved_digest = digest if decision == "approved" else None
        self.audit.record(
            reviewer.strip(),
            "record_decision",
            {"decision": decision, "findings_digest": digest, "note": note},
            "ok",
        )
        return self.state

    def _render_report(self) -> str:
        lines = [
            f"# Preliminary review: {self.change_request_id}",
            "",
            "**This is a preliminary review approved for export, not a compliance decision.**",
            "",
            f"- Document digest: `{self.document_digest}`",
            f"- Findings digest: `{self.approved_digest}`",
            "",
        ]
        for rule_id in self.rules:
            finding = self.findings[rule_id]
            lines += [f"## {rule_id}: `{finding.verdict}`", ""]
            if finding.downgrade_reason:
                lines += [
                    f"Downgraded from `{finding.raw_verdict}`: {finding.downgrade_reason}.",
                    "",
                ]
            for citation in finding.citations:
                status = "verified" if citation["verbatim"] else "not verified"
                lines.append(f"- {citation['section']} ({status}): \"{citation['quote']}\"")
            if finding.follow_up_question:
                lines += ["", f"Follow-up: {finding.follow_up_question}"]
            lines.append("")
        return "\n".join(lines)


def _parse_citations(citations: object) -> tuple[Citation, ...]:
    if not isinstance(citations, list):
        raise ToolRefused("citations must be a list.")
    parsed = []
    for item in citations:
        if not isinstance(item, dict) or not {"section", "quote"} <= set(item):
            raise ToolRefused("Each citation needs a section and a quote.")
        parsed.append(Citation(str(item["section"]), str(item["quote"])))
    return tuple(parsed)


TOOL_METHODS = {
    "read_change_request": ReviewSession.read_change_request,
    "search_policy": ReviewSession.search_policy,
    "verify_quote": ReviewSession.verify_quote,
    "save_finding": ReviewSession.save_finding,
    "request_approval": ReviewSession.request_approval,
    "export_report": ReviewSession.export_report,
}

TOOL_DESCRIPTIONS = {
    "read_change_request": "Read every section of the change request under review.",
    "search_policy": "Get a policy rule by its exact ID, or search the rules by keyword.",
    "verify_quote": "Check whether a quote appears word for word in a change request section.",
    "save_finding": (
        "Save a draft finding for one rule. Saving the same rule again replaces it. "
        "Unverified citations downgrade the verdict to insufficient_evidence."
    ),
    "request_approval": "Submit all findings for human review. Call this once, after every rule is saved.",
    "export_report": "Export the report. This is refused unless a person has approved the findings.",
}

_STRING = {"type": "string"}
TOOL_PARAMETERS = {
    "read_change_request": {
        "type": "object",
        "properties": {"change_request_id": _STRING},
        "required": ["change_request_id"],
    },
    "search_policy": {"type": "object", "properties": {"query": _STRING}, "required": ["query"]},
    "verify_quote": {
        "type": "object",
        "properties": {"section": _STRING, "quote": _STRING},
        "required": ["section", "quote"],
    },
    "save_finding": {
        "type": "object",
        "properties": {
            "rule_id": _STRING,
            "verdict": {"type": "string", "enum": list(VERDICTS)},
            "citations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"section": _STRING, "quote": _STRING},
                    "required": ["section", "quote"],
                },
            },
            "follow_up_question": {
                "type": "string",
                "description": "Required when the verdict is contradicted or insufficient_evidence.",
            },
        },
        "required": ["rule_id", "verdict", "citations"],
    },
    "request_approval": {"type": "object", "properties": {}},
    "export_report": {"type": "object", "properties": {}},
}


def tool_definitions() -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": name,
                "description": TOOL_DESCRIPTIONS[name],
                "parameters": TOOL_PARAMETERS[name],
            },
        }
        for name in TOOL_METHODS
    ]
