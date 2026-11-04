"""Assess one policy rule using a local model served by Ollama."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from collections.abc import Sequence

from pydantic import ValidationError

from reqtrace.assessment import Citation, Finding
from reqtrace.documents import Rule, Section
from reqtrace.prompting import SYSTEM_PROMPT, AssessmentError, FindingOutput, build_user_message

DEFAULT_MODEL = "qwen2.5:7b"
DEFAULT_HOST = "http://localhost:11434"


class OllamaUnavailableError(Exception):
    """Ollama can't serve the request. This stops the run, because it isn't a model answer."""


class OllamaAssessor:
    """A single-call assessor: no tools, retries on bad citations, or agent loop."""

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        host: str | None = None,
        timeout: float = 600.0,
        seed: int = 42,
    ) -> None:
        self.model = model
        self.host = (host or os.environ.get("OLLAMA_HOST") or DEFAULT_HOST).rstrip("/")
        if "://" not in self.host:
            self.host = f"http://{self.host}"
        self.timeout = timeout
        self.seed = seed

    def _request(self, path: str, payload: dict | None = None) -> dict:
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = urllib.request.Request(
            f"{self.host}{path}", data=data, headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            hint = f" Try: ollama pull {self.model}" if error.code == 404 else ""
            raise OllamaUnavailableError(f"Ollama returned {error.code}: {detail}.{hint}") from error
        except (urllib.error.URLError, TimeoutError) as error:
            raise OllamaUnavailableError(
                f"Can't reach Ollama at {self.host}: {error}. Check that it's running."
            ) from error

    def model_digest(self) -> str | None:
        """Return the installed model's digest, which identifies the exact weights used."""
        models = self._request("/api/tags").get("models", [])
        return next((m.get("digest") for m in models if m.get("name") == self.model), None)

    def assess(self, rule: Rule, sections: Sequence[Section]) -> Finding:
        response = self._request(
            "/api/chat",
            {
                "model": self.model,
                "stream": False,
                "format": FindingOutput.model_json_schema(),
                "options": {"temperature": 0, "seed": self.seed, "num_ctx": 8192},
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": build_user_message(rule, sections)},
                ],
            },
        )
        done_reason = response.get("done_reason")
        if done_reason != "stop":
            raise AssessmentError(f"No usable finding for {rule.rule_id}: done_reason={done_reason}")
        try:
            output = FindingOutput.model_validate_json(response["message"]["content"])
        except (KeyError, TypeError, ValidationError) as error:
            raise AssessmentError(f"Invalid output for {rule.rule_id}: {error}") from error
        return Finding(
            verdict=output.verdict,
            citations=tuple(Citation(c.section, c.quote) for c in output.citations),
            served_by=response.get("model", self.model),
            input_tokens=response.get("prompt_eval_count", 0),
            output_tokens=response.get("eval_count", 0),
        )
