"""Review a change request from the terminal, and stop for a person's decision."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from reqtrace.agent import run_workflow_review
from reqtrace.audit import AuditLog
from reqtrace.documents import ROOT
from reqtrace.evaluation import load_cases
from reqtrace.ollama_assessor import DEFAULT_MODEL, OllamaAssessor, OllamaUnavailableError
from reqtrace.retrieval import EmbeddingRetriever
from reqtrace.review import ReviewSession


def render_findings(session: ReviewSession) -> str:
    lines = [f"Preliminary findings for {session.change_request_id}", ""]
    if session.quarantined:
        lines.append("WARNING: this text looked like instructions to an AI and was hidden from the model:")
        lines += [f"  {item.section}: {item.text}" for item in session.quarantined]
        lines.append("")
    for rule_id in session.rules:
        finding = session.findings[rule_id]
        lines.append(f"{rule_id}: {finding.verdict}")
        if finding.downgrade_reason:
            lines.append(f"  Downgraded from {finding.raw_verdict}: {finding.downgrade_reason}")
        for citation in finding.citations:
            status = "verified" if citation["verbatim"] else "not verified"
            lines.append(f"  [{status}] {citation['section']}: {citation['quote']}")
        if finding.follow_up_question:
            lines.append(f"  Follow-up: {finding.follow_up_question}")
    return "\n".join(lines)


def ask_for_decision(session: ReviewSession, ask: Callable[[str], str]) -> int:
    """Export only after a named person types `approve`. Anything else exports nothing."""
    try:
        answer = ask("Type approve or reject: ").strip().lower()
        reviewer = ask("Your name: ").strip() if answer in {"approve", "reject"} else ""
    except EOFError:
        print("No decision was recorded, so nothing was exported.")
        return 1
    if answer not in {"approve", "reject"} or not reviewer:
        print("No valid decision was recorded, so nothing was exported.")
        return 1
    session.record_decision("approved" if answer == "approve" else "rejected", reviewer)
    if session.state != "approved":
        print("Rejected. Nothing was exported.")
        return 0
    result = session.call_tool("export_report", {})
    if not result["ok"]:
        print(f"Export refused: {result['error']}")
        return 1
    print(f"Report: {result['report']}")
    return 0


def run_cli(session: ReviewSession, assessor, retriever, ask: Callable[[str], str]) -> int:
    run = run_workflow_review(session, assessor, retriever)
    if run.status != "pending_approval":
        print(f"The review couldn't finish: {run.status}. See {session.audit.path}.")
        return 1
    print(render_findings(session))
    print()
    print("This is a preliminary review, not a compliance decision.")
    code = ask_for_decision(session, ask)
    print(f"Audit log: {session.audit.path}")
    return code


def main() -> int:
    documents = sorted({case["change_request"] for case in load_cases("dev")})
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("change_request", choices=documents, help="dev change requests only")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "runs")
    args = parser.parse_args()

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = args.output_dir / f"{args.change_request}_{stamp}"
    run_dir.mkdir(parents=True)
    session = ReviewSession(args.change_request, AuditLog(run_dir / "audit.jsonl"), run_dir)
    try:
        return run_cli(session, OllamaAssessor(model=args.model), EmbeddingRetriever(), input)
    except OllamaUnavailableError as error:
        print(error, file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
