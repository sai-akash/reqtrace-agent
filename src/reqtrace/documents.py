"""Load policy rules and change requests from Markdown."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOMAIN = ROOT / "domains" / "healthcare_it"
POLICY_PATH = DOMAIN / "policy" / "FCN-IT-POL-07.md"
CHANGE_REQUESTS_DIR = DOMAIN / "change_requests"


@dataclass(frozen=True)
class Section:
    doc_id: str
    title: str
    text: str


@dataclass(frozen=True)
class Rule:
    rule_id: str
    title: str
    text: str


def parse_sections(text: str) -> dict[str, str]:
    """Return a mapping of each level-2 heading to its body text."""
    parts = re.split(r"^## (.+)$", text, flags=re.MULTILINE)
    return {parts[i].strip(): parts[i + 1].strip() for i in range(1, len(parts) - 1, 2)}


def load_rules(path: Path = POLICY_PATH) -> dict[str, Rule]:
    rules = {}
    for heading, body in parse_sections(path.read_text(encoding="utf-8")).items():
        rule_id, title = heading.split(maxsplit=1)
        rules[rule_id] = Rule(rule_id, title, body)
    return rules


def load_change_request(doc_id: str, directory: Path = CHANGE_REQUESTS_DIR) -> list[Section]:
    text = (directory / f"{doc_id}.md").read_text(encoding="utf-8")
    return [Section(doc_id, title, body) for title, body in parse_sections(text).items()]
