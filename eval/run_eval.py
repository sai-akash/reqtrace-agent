"""Run a retrieval or assessment experiment and print a JSON report."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from reqtrace.assessment import AbstainAssessor
from reqtrace.documents import ROOT
from reqtrace.evaluation import evaluate_assessor, evaluate_retrieval, load_cases
from reqtrace.ollama_assessor import DEFAULT_MODEL as OLLAMA_MODEL
from reqtrace.ollama_assessor import OllamaAssessor, OllamaUnavailableError
from reqtrace.retrieval import Bm25Retriever, EmbeddingRetriever



def build_assessor(name: str, model: str | None, effort: str | None):
    if name == "abstain":
        return AbstainAssessor()
    if name == "ollama":
        return OllamaAssessor(model=model or OLLAMA_MODEL)
    from reqtrace.claude_assessor import DEFAULT_EFFORT, DEFAULT_MODEL, ClaudeAssessor

    return ClaudeAssessor(model=model or DEFAULT_MODEL, effort=effort or DEFAULT_EFFORT)


def current_commit() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=False
    )
    return result.stdout.strip() or "unknown"


def build_retriever(name: str):
    return EmbeddingRetriever() if name == "embedding" else Bm25Retriever()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment", choices=["retrieval", "oracle", "semantic"], required=True)
    parser.add_argument("--retriever", choices=["bm25", "embedding"], default="bm25")
    parser.add_argument("--assessor", choices=["abstain", "ollama", "claude"], default="abstain")
    parser.add_argument("--model", help="model name for the chosen assessor")
    parser.add_argument(
        "--effort", choices=["low", "medium", "high", "xhigh", "max"], help="Claude only"
    )
    parser.add_argument("--split", choices=["dev", "held_out"], default="dev")
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--limit", type=int, help="run only the first N cases, for a cheap trial")
    parser.add_argument(
        "--final-held-out-run",
        action="store_true",
        help="confirm that this is the single final run on the held-out split",
    )
    parser.add_argument("--output", type=Path, help="also write the report to this file")
    args = parser.parse_args()

    try:
        cases = load_cases(args.split, confirm_held_out=args.final_held_out_run)
    except PermissionError as error:
        print(f"{error} Pass --final-held-out-run only for that run.", file=sys.stderr)
        return 2

    if args.limit is not None:
        if args.split == "held_out":
            print("--limit can't be used on the held-out split.", file=sys.stderr)
            return 2
        cases = cases[: args.limit]

    report = {"commit": current_commit(), "split": args.split, "partial_run": args.limit is not None}
    if args.experiment == "retrieval":
        report |= {"retriever": args.retriever}
        report |= evaluate_retrieval(cases, build_retriever(args.retriever))
    else:
        retriever = build_retriever(args.retriever) if args.experiment == "semantic" else None
        assessor = build_assessor(args.assessor, args.model, args.effort)
        report |= {"assessor": args.assessor, "top_k": args.top_k}
        if args.assessor == "claude":
            report |= {"model": assessor.model, "effort": assessor.effort}
        if retriever:
            report["retriever"] = args.retriever
        try:
            if args.assessor == "ollama":
                report |= {"model": assessor.model, "model_digest": assessor.model_digest()}
            report |= evaluate_assessor(cases, assessor, args.experiment, retriever, args.top_k)
        except OllamaUnavailableError as error:
            print(error, file=sys.stderr)
            return 3

    text = json.dumps(report, indent=2)
    print(text)
    if args.output:
        args.output.write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
