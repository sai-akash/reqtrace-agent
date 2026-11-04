# reqtrace-agent

An agent that checks engineering evidence against requirements, cites its sources, flags gaps, drafts follow-up questions and tests, and waits for human approval.

**Status: scenario and evaluation data only. The agent is not built yet, so there are no results to report.**

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
src/reqtrace/                Agent code (to be added)
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

All organisations, systems, people, policies, and change requests here are invented. The repo contains no patient data and no data from any real company. The labels are one author's judgment and need an independent review before results are published. With only 5 source documents, results can't support broad claims about generalisation. See the [limitations](docs/scenario_healthcare_it.md#limitations-to-state-in-every-evaluation-report).
