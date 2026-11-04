"""Tests run real HTTP against a fake local server, so they don't need Ollama."""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from reqtrace.documents import Rule, Section
from reqtrace.evaluation import evaluate_assessor, load_cases
from reqtrace.ollama_assessor import OllamaAssessor, OllamaUnavailableError
from reqtrace.prompting import SYSTEM_PROMPT, AssessmentError, build_output_schema

RULE = Rule("CHG-1", "Test evidence", "A test must be recorded.")
SECTIONS = [Section("CR-1", "4. Testing", "Tested on 1 May. Outcome: passed.")]
ANSWER = json.dumps(
    {"verdict": "supported", "citations": [{"section": "4. Testing", "quote": "Tested on 1 May."}]}
)


def chat_reply(content=ANSWER, done_reason="stop"):
    return {
        "model": "test-model:1b",
        "message": {"role": "assistant", "content": content},
        "done_reason": done_reason,
        "prompt_eval_count": 100,
        "eval_count": 20,
    }


@pytest.fixture
def server():
    state = {"status": 200, "reply": chat_reply(), "requests": []}

    class Handler(BaseHTTPRequestHandler):
        def _send(self, status, body):
            data = json.dumps(body).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            state["requests"].append(body)
            self._send(state["status"], state["reply"])

        def do_GET(self):
            self._send(200, {"models": [{"name": "test-model:1b", "digest": "abc123"}]})

        def log_message(self, *args):
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    state["host"] = f"http://127.0.0.1:{httpd.server_address[1]}"
    yield state
    httpd.shutdown()
    httpd.server_close()


def assessor(server):
    return OllamaAssessor(model="test-model:1b", host=server["host"])


def test_request_uses_schema_system_prompt_and_fixed_seed(server):
    assessor(server).assess(RULE, SECTIONS)
    body = server["requests"][0]
    assert body["stream"] is False
    assert body["format"] == build_output_schema(SECTIONS)
    assert body["options"]["temperature"] == 0
    assert body["options"]["seed"] == 42
    assert body["messages"][0] == {"role": "system", "content": SYSTEM_PROMPT}


def test_parses_finding_and_records_usage(server):
    finding = assessor(server).assess(RULE, SECTIONS)
    assert finding.verdict == "supported"
    assert finding.citations[0].quote == "Tested on 1 May."
    assert finding.served_by == "test-model:1b"
    assert (finding.input_tokens, finding.output_tokens) == (100, 20)


@pytest.mark.parametrize(
    "reply",
    [
        chat_reply(content="not json"),
        chat_reply(content='{"verdict": "compliant", "citations": []}'),
        chat_reply(done_reason="length"),
    ],
)
def test_unusable_output_raises_assessment_error(server, reply):
    server["reply"] = reply
    with pytest.raises(AssessmentError):
        assessor(server).assess(RULE, SECTIONS)


def test_unusable_output_counts_against_the_score(server):
    server["reply"] = chat_reply(content="not json")
    report = evaluate_assessor(load_cases("dev")[:2], assessor(server), "oracle")
    assert report["failed_calls"] == 2
    assert report["checked"]["verdict_accuracy"] == 0


def test_missing_model_stops_with_a_pull_hint(server):
    server["status"] = 404
    server["reply"] = {"error": "model not found"}
    with pytest.raises(OllamaUnavailableError, match="ollama pull test-model:1b"):
        assessor(server).assess(RULE, SECTIONS)


def test_server_down_stops_the_run_instead_of_scoring_wrong_answers():
    down = OllamaAssessor(model="test-model:1b", host="http://127.0.0.1:9", timeout=2)
    with pytest.raises(OllamaUnavailableError, match="Can't reach Ollama"):
        evaluate_assessor(load_cases("dev")[:1], down, "oracle")


def test_digest_lookup(server):
    assert assessor(server).model_digest() == "abc123"
    assert OllamaAssessor(model="other:1b", host=server["host"]).model_digest() is None


def test_host_without_scheme_is_accepted():
    assert OllamaAssessor(host="localhost:11434").host == "http://localhost:11434"
