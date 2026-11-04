# reqtrace-agent

An agent that checks engineering evidence against requirements, cites its sources, flags gaps, drafts follow-up questions and tests, and waits for human approval.

**Status: evaluation data, retrieval, an evaluation runner, single-call LLM assessors, citation checks, and a controlled agent workflow with human approval and an audit log are in place. There are no published results, and hidden instructions in a document can still change verdicts. The labels are frozen as `labels-v1`, without an independent human review.**

| Assessor | Status |
|---|---|
| Ollama (local, free) | Run on the dev split with `qwen2.5:7b`; development runs only, so no published scores |
| Claude API | Tested against a fake API only, because it hasn't been run with a real key |

## First demo: IT change request review

The agent reads a fictional IT change request, compares it with a fictional IT policy, and gives each policy rule one of four verdicts:

| Verdict | Meaning |
|---|---|
| `supported` | The change request shows that the rule is met |
| `contradicted` | The change request shows that the rule is not met |
| `insufficient_evidence` | The rule applies, but the change request doesn't show whether it is met |
| `not_applicable` | The rule doesn't apply to this change |

A person reviews the findings and approves any export. The output is a preliminary review, not a compliance decision.

See the [scenario spec](docs/scenario_healthcare_it.md) for inputs, outputs, metrics, and build order.

## Repository layout

```text
docs/                        Scenario spec and annotation guidelines
domains/healthcare_it/       Fictional policy and change requests
eval/datasets/healthcare_it/ Labelled cases (dev and held-out)
eval/validate_cases.py       Checks the cases against the documents
eval/review_labels.py        Blind label review and agreement check
eval/run_eval.py             Retrieval and assessment experiments
eval/compare_reports.py      Compares two evaluation reports
eval/run_agent_eval.py       Runs the agent workflow on dev change requests
eval/results/                Development reports
src/reqtrace/                Document loading, retrieval, and scoring
tests/                       Tests for the validator and dataset
```

## Check the evaluation data

```bash
python -m pip install -e ".[dev]"
```

```bash
python eval/validate_cases.py
```

```bash
python -m pytest
```

## Data notice

All organisations, systems, people, policies, and change requests here are invented. The repo contains no patient data and no data from any real company. The labels are one author's judgment and haven't had an independent human review. Any published results must say so. With only 5 source documents, results can't support broad claims about generalisation. See the [limitations](docs/scenario_healthcare_it.md#limitations-to-state-in-every-evaluation-report).
