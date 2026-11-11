"""Run reviews through folders that OneDrive syncs with SharePoint.

A change request uploaded to `Requests` is reviewed on this computer, and a draft is
written to `Drafts`. A Power Automate flow collects a person's approval and writes a
decision file to `Decisions`. The report is exported to `Approved` only if that
decision names the exact findings that were reviewed.

Anyone who can write to `Decisions` could create a decision file. The digest check
and the logged approver make forgery harder and visible, but this isn't
authentication, so access to that folder must be limited.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from collections.abc import Callable
from pathlib import Path

from reqtrace.agent import run_workflow_review
from reqtrace.audit import AuditLog
from reqtrace.documents import ROOT, Rule, Section, parse_sections
from reqtrace.review import ReviewSession

FOLDERS = ("Requests", "Drafts", "Decisions", "Approved", "Problems")
REQUEST_NAME = re.compile(r"^CR-[A-Za-z0-9-]{1,40}$")
MAX_REQUEST_BYTES = 200_000
STABLE_SECONDS = 10
OUTCOMES = {"approve": "approved", "approved": "approved", "reject": "rejected", "rejected": "rejected"}


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_atomically(path: Path, text: str) -> None:
    """Write a file in one step, so a sync or a flow never sees half of it."""
    temporary = path.with_name(f".{path.name}.partial")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


class FolderBridge:
    def __init__(
        self,
        shared_dir: Path,
        state_dir: Path,
        assessor,
        retriever,
        rules: dict[str, Rule] | None = None,
        clock: Callable[[], float] = time.time,
        stable_seconds: float = STABLE_SECONDS,
    ) -> None:
        self.shared = {name: shared_dir / name for name in FOLDERS}
        for folder in self.shared.values():
            folder.mkdir(parents=True, exist_ok=True)
        self.state_dir = state_dir
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.assessor = assessor
        self.retriever = retriever
        self.rules = rules
        self.clock = clock
        self.stable_seconds = stable_seconds
        self.state_path = state_dir / "bridge_state.json"
        self.state = (
            json.loads(self.state_path.read_text(encoding="utf-8"))
            if self.state_path.exists()
            else {"seen_files": {}, "reviews": {}}
        )
        log_path = state_dir / "bridge_audit.jsonl"
        self.log = AuditLog.resume(log_path) if log_path.exists() else AuditLog(log_path)

    def _save_state(self) -> None:
        _write_atomically(self.state_path, json.dumps(self.state, indent=2, sort_keys=True))

    def _process(self, folder: str, suffixes: tuple[str, ...], handler) -> None:
        """Handle new files that have stopped changing, so partly synced files are skipped.

        A file is marked as handled only after its handler returns, so a run that stops
        partway, such as when Ollama is down, tries the file again next time.
        """
        for path in sorted(self.shared[folder].iterdir()):
            if not path.is_file() or path.name.startswith((".", "~$")):
                continue
            if self.clock() - path.stat().st_mtime < self.stable_seconds:
                continue
            data = path.read_bytes()
            key = f"{folder}/{path.name}"
            if self.state["seen_files"].get(key) == _sha(data):
                continue
            if path.suffix.lower() in suffixes:
                handler(path, data)
            else:
                self._problem(path.name, f"Unsupported file type. Expected {', '.join(suffixes)}.")
            self.state["seen_files"][key] = _sha(data)
            self._save_state()

    def _problem(self, name: str, message: str) -> None:
        self.log.record("bridge", "problem", {"file": name, "message": message}, "refused")
        _write_atomically(self.shared["Problems"] / f"{name}.txt", message + "\n")

    def _audit(self, review_id: str) -> AuditLog:
        return AuditLog.resume(self.state_dir / review_id / "audit.jsonl")

    def run_once(self) -> None:
        self._process("Requests", (".md",), self._handle_request)
        self._process("Decisions", (".json",), self._handle_decision)

    def _handle_request(self, path: Path, data: bytes) -> None:
        change_request_id = path.stem
        if not REQUEST_NAME.match(change_request_id):
            return self._problem(path.name, "Name the file like CR-123.md, using letters, numbers, and hyphens.")
        if len(data) > MAX_REQUEST_BYTES:
            return self._problem(path.name, f"The file is larger than {MAX_REQUEST_BYTES} bytes.")
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            return self._problem(path.name, "The file isn't UTF-8 text.")
        sections = [Section(change_request_id, title, body) for title, body in parse_sections(text).items()]
        if not sections:
            return self._problem(path.name, "No sections found. Use '## ' headings for each section.")

        review_id = f"{change_request_id}_{_sha(data)[:8]}"
        for other_id, review in self.state["reviews"].items():
            if review["change_request_id"] == change_request_id and review["status"] == "pending_approval":
                review["status"] = "superseded"
                self._audit(other_id).record("bridge", "supersede", {"by": review_id}, "ok")

        review_dir = self.state_dir / review_id
        review_dir.mkdir(exist_ok=True)
        leftover = review_dir / "audit.jsonl"
        if leftover.exists():
            leftover.rename(review_dir / f"audit_interrupted_{len(list(review_dir.glob('audit_*')))}.jsonl")
        session = ReviewSession(
            change_request_id,
            AuditLog(review_dir / "audit.jsonl"),
            self.shared["Approved"],
            rules=self.rules,
            sections=sections,
        )
        run = run_workflow_review(session, self.assessor, self.retriever)
        record = {"change_request_id": change_request_id, "status": run.status}
        self.state["reviews"][review_id] = record
        self.log.record("bridge", "review", {"review_id": review_id, "status": run.status}, "ok")
        if run.status != "pending_approval":
            return self._problem(path.name, f"The review couldn't finish ({run.status}). See {review_id}.")

        saved = session.to_state(sections)
        _write_atomically(review_dir / "session.json", json.dumps(saved, indent=2))
        record["findings_digest"] = saved["findings_digest"]
        summary = _render_summary(session, review_id)
        _write_atomically(self.shared["Drafts"] / f"{review_id}.md", summary)
        draft = {
            "review_id": review_id,
            "change_request_id": change_request_id,
            "findings_digest": saved["findings_digest"],
            "summary": summary,
        }
        _write_atomically(self.shared["Drafts"] / f"{review_id}.json", json.dumps(draft, indent=2))

    def _handle_decision(self, path: Path, data: bytes) -> None:
        try:
            decision = json.loads(data.decode("utf-8-sig"))
            review_id = str(decision["review_id"])
            digest = str(decision["findings_digest"])
            outcome = OUTCOMES.get(str(decision["outcome"]).strip().lower())
            approver = str(decision["approver_email"]).strip()
        except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as error:
            return self._problem(path.name, f"Unreadable decision file: {error}")
        if outcome is None or not approver:
            return self._problem(path.name, "The decision needs an outcome of Approve or Reject and an approver email.")
        review = self.state["reviews"].get(review_id)
        if review is None:
            return self._problem(path.name, f"No review called {review_id} exists.")
        audit = self._audit(review_id)
        details = {"file": path.name, "approver": approver, "outcome": outcome}
        if review["status"] != "pending_approval":
            audit.record("bridge", "decision_refused", details | {"reason": review["status"]}, "refused")
            return self._problem(path.name, f"Review {review_id} isn't waiting for a decision ({review['status']}).")
        if digest != review["findings_digest"]:
            audit.record("bridge", "decision_refused", details | {"reason": "digest_mismatch"}, "refused")
            return self._problem(path.name, "The decision doesn't match the findings that were sent for approval.")

        saved = json.loads((self.state_dir / review_id / "session.json").read_text(encoding="utf-8"))
        try:
            session = ReviewSession.restore(saved, audit, self.shared["Approved"], rules=self.rules)
        except ValueError as error:
            audit.record("bridge", "decision_refused", details | {"reason": str(error)}, "refused")
            return self._problem(path.name, f"The saved review can't be trusted: {error}")
        note = json.dumps(
            {key: decision.get(key) for key in ("approver_name", "comments", "flow_run_id", "responded_at")}
        )
        session.record_decision(outcome, approver, note)
        review["status"] = outcome
        if outcome == "approved":
            result = session.call_tool("export_report", {})
            if result["ok"]:
                review["status"] = "exported"
            else:
                self._problem(path.name, f"Export refused: {result['error']}")
        self.log.record("bridge", "decision", {"review_id": review_id, "status": review["status"]}, "ok")


def _render_summary(session: ReviewSession, review_id: str) -> str:
    lines = [
        f"# Preliminary review: {session.change_request_id}",
        "",
        "This is a preliminary review for a person to check, not a compliance decision.",
        "",
        f"- Review ID: `{review_id}`",
        f"- Findings digest: `{session.findings_digest()}`",
        "",
    ]
    if session.quarantined:
        lines += ["**Warning: text that looked like instructions to an AI was hidden from the model:**", ""]
        lines += [f"- {item.section}: \"{item.text}\"" for item in session.quarantined]
        lines.append("")
    for rule_id in session.rules:
        finding = session.findings[rule_id]
        lines.append(f"**{rule_id}: {finding.verdict}**")
        if finding.downgrade_reason:
            lines.append(f"- Downgraded from {finding.raw_verdict}: {finding.downgrade_reason}")
        for citation in finding.citations:
            status = "verified" if citation["verbatim"] else "NOT verified"
            lines.append(f"- {citation['section']} ({status}): \"{citation['quote']}\"")
        if finding.follow_up_question:
            lines.append(f"- Follow-up: {finding.follow_up_question}")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    from reqtrace.ollama_assessor import DEFAULT_MODEL, OllamaAssessor, OllamaUnavailableError
    from reqtrace.retrieval import EmbeddingRetriever

    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--shared-dir", type=Path, required=True, help="the OneDrive-synced SharePoint folder")
    parser.add_argument("--state-dir", type=Path, default=ROOT / "runs" / "bridge")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--interval", type=float, default=15)
    parser.add_argument("--once", action="store_true", help="check the folders once, then stop")
    args = parser.parse_args()

    bridge = FolderBridge(args.shared_dir, args.state_dir, OllamaAssessor(model=args.model), EmbeddingRetriever())
    print(f"Watching {args.shared_dir}. Press Ctrl+C to stop.")
    while True:
        try:
            bridge.run_once()
        except OllamaUnavailableError as error:
            print(error, file=sys.stderr)
            return 3
        if args.once:
            return 0
        try:
            time.sleep(args.interval)
        except KeyboardInterrupt:
            return 0


if __name__ == "__main__":
    sys.exit(main())
