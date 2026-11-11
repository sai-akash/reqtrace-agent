"""An append-only audit log, with each entry chained to the hash of the one before."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

GENESIS_HASH = "0" * 64


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _entry_hash(entry: dict) -> str:
    content = {key: value for key, value in entry.items() if key != "hash"}
    encoded = json.dumps(content, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class AuditLog:
    """Write one JSON line per event.

    The chain reveals edited, reordered, or removed entries, except removal from the
    end of the file. Someone who can rewrite the whole file can also rebuild the
    chain, so a real deployment would need to store the latest hash elsewhere.
    """

    def __init__(self, path: Path, clock: Callable[[], str] = _utc_now) -> None:
        if path.exists():
            raise FileExistsError(f"Audit log already exists: {path}")
        self.path = path
        self.clock = clock
        self.sequence = 0
        self.last_hash = GENESIS_HASH

    @classmethod
    def resume(cls, path: Path, clock: Callable[[], str] = _utc_now) -> "AuditLog":
        """Continue an existing log, but only if its chain is intact."""
        problems = verify_audit_log(path)
        if problems:
            raise ValueError(f"Audit log is damaged, so it can't be continued: {problems[0]}")
        entries = read_audit_log(path)
        log = cls.__new__(cls)
        log.path = path
        log.clock = clock
        log.sequence = len(entries)
        log.last_hash = entries[-1]["hash"] if entries else GENESIS_HASH
        return log

    def record(self, actor: str, action: str, details: dict, outcome: str) -> dict:
        self.sequence += 1
        entry = {
            "sequence": self.sequence,
            "time": self.clock(),
            "actor": actor,
            "action": action,
            "details": details,
            "outcome": outcome,
            "previous_hash": self.last_hash,
        }
        entry["hash"] = _entry_hash(entry)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, sort_keys=True, ensure_ascii=False) + "\n")
        self.last_hash = entry["hash"]
        return entry


def read_audit_log(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def verify_audit_log(path: Path) -> list[str]:
    """Return every problem found in the chain. An empty list means it's intact."""
    problems = []
    previous = GENESIS_HASH
    for position, entry in enumerate(read_audit_log(path), start=1):
        if entry.get("sequence") != position:
            problems.append(f"Entry {position}: unexpected sequence {entry.get('sequence')}")
        if entry.get("previous_hash") != previous:
            problems.append(f"Entry {position}: doesn't follow the previous entry")
        if entry.get("hash") != _entry_hash(entry):
            problems.append(f"Entry {position}: content doesn't match its hash")
        previous = entry.get("hash")
    return problems
