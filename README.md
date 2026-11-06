# reqtrace-agent

[![Tests](https://github.com/sai-akash/reqtrace-agent/actions/workflows/tests.yml/badge.svg?branch=main)](https://github.com/sai-akash/reqtrace-agent/actions/workflows/tests.yml)

**An agentic AI prototype that reviews healthcare IT change requests against policy rules, cites its evidence, and stops for human approval.**

Before an IT system changes, someone has to check that the request meets policy: was it tested, can it be rolled back, was it approved? An LLM can help with that review, but a confident answer with no evidence is a risk in a healthcare setting.

This prototype explores how to make that kind of agent testable and governable. Every verdict must cite the source text, every step is logged, and a named person decides whether anything leaves the system. The evaluation records what works and what still fails.

> **This is a proof of concept using invented data.** It produces a preliminary review, not a compliance decision. All organisations, systems, policies, and change requests are fictional, and the repo contains no patient or company data.

## What it does

The input is a change request and an IT policy with 8 rules. For each rule, the prototype returns a verdict, verbatim citations, and a follow-up question if the rule isn't shown to be met.

| Verdict | Meaning |
|---|---|
| `supported` | The change request shows that the rule is met |
| `contradicted` | The change request shows that the rule isn't met |
| `insufficient_evidence` | The rule applies, or might, but the text doesn't settle it |
| `not_applicable` | The rule doesn't apply to this change |

### Example output

This is a real result from the local model, reviewing rule CHG-2 for fictional change request CR-103. The rule limits rollback on Tier 1 systems to 60 minutes.

```text
CHG-2: contradicted
  [verified] 5. Rollback: Estimated rollback time: 90 minutes.
  Follow-up: Can the estimated rollback time be reduced to meet the 60-minute
  requirement for Tier 1 systems, or is there a reason it cannot?
```

The verdict is correct, but the citation is incomplete because it leaves out the Tier 1 classification. The evaluation measures gaps like this.

### A full review

<img src="docs/images/terminal_review.png" alt="Terminal output of a full CR-103 review: findings for all 8 rules, then a prompt where a named person approves the export." width="760">

*Text from a real run on CR-103, drawn as an image, with scripted answers and a placeholder name. The model isn't always right: its CHG-1 verdict here should be `contradicted`, and the citation check can't catch that because the quote is real.*

## How it works

```mermaid
flowchart TD
    A[Change request] --> B[Screen for text addressed to an AI]
    B --> C[Retrieve the top 3 sections for each rule]
    C --> D[LLM returns a verdict and citations in a fixed schema]
    D --> E[Code checks each quote against its source section]
    E -->|Quote or citation missing| F[Downgrade to insufficient_evidence]
    E -->|Verified| G[Draft finding]
    F --> G
    G --> H[Draft follow-up question if needed]
    H --> I{Named person approves?}
    I -->|Yes| J[Export report]
    I -->|No| K[Nothing exported]
```

All of these steps run through audited tools, so refused actions are logged too. The model has no tool for recording a decision, and export needs both approval and unchanged findings.

## What the project covers

| Area | What's here |
|---|---|
| **Agent design** | Six audited tools (`read_change_request`, `search_policy`, `verify_quote`, `save_finding`, `request_approval`, `export_report`), plus a comparison of model-driven and code-controlled workflows |
| **Generative AI and RAG** | A local LLM through Ollama, embedding retrieval with a BM25 comparison, and structured output with JSON Schema |
| **Testing and evaluation** | 40 labelled cases split by document, a frozen label set, 162 automated tests, and a prompt injection test suite |
| **Governance and controls** | Human approval, a hash-chained audit log, citation checks, document screening, and a record of known limits |
| **Documentation** | [Scenario spec](docs/scenario_healthcare_it.md), [annotation guidelines](docs/annotation_guidelines.md), [label decisions](docs/label_decisions.md), and written results |

## Results so far

These are **development results** from 24 synthetic cases, using `qwen2.5:7b`. I chose the fixes after seeing these same cases, so the scores are optimistic. The 16 held-out cases haven't been run.

### Citation checks

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/citation_results_dark.png">
  <img src="docs/images/citation_results_light.png" alt="Bar chart: accuracy after citation checks rose from 0.29 to 0.79, quotes found in the cited section from 0.82 to 0.96, and expected facts covered from 0.27 to 0.64." width="760">
</picture>

| Metric | Before schema constraints | After |
|---|---:|---:|
| Accuracy after citation checks | 0.29 | **0.79** |
| Quotes found in the cited section | 0.82 | 0.96 |
| Expected facts covered by citations | 0.27 | 0.64 |

The model's verdicts didn't change. It had often left out its evidence, so the checks were downgrading correct answers.

### Who should control the workflow?

| Mode | Who picks each step | Cases | Correct after check |
|---|---|---:|---:|
| `free` | Model | 8 | 3 |
| `scoped` (one conversation per rule) | Model | 8 | 1 |
| `workflow` | Code | 24 | **19** |

For this small local model, a code-controlled workflow was far more reliable. The model-driven modes ran on one change request only, and a stronger model might do much better.

### Prompt injection

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/injection_results_dark.png">
  <img src="docs/images/injection_results_light.png" alt="Bar chart of verdicts changed out of 24: direct instruction 6 without the screen and 0 with it; addressed note 3 and 0; altered spelling 2 and 2; false claim 1 and 1." width="760">
</picture>

| Attack added to the document | Verdicts changed without the screen (of 24) | With the screen |
|---|---:|---:|
| Direct instruction naming a tool | 6 | 0 |
| Note addressed to the AI reviewer | 3 | 0 |
| Instruction with altered spelling | 2 | 2 |
| False compliance claim in plain prose | 1 | 1 |

In every run, the model made no export attempts and nothing bypassed approval. **Hidden text can still change verdicts, so this remains an open risk.** Read the [agent results](docs/dev_agent_results.md) and [citation results](docs/dev_citation_results.md) for how each figure was measured.

## Known limitations

- **Labels:** they're one author's judgment and have had no independent human review. An AI second opinion agreed, but it had already seen some labels, so it doesn't count as validation.
- **Data:** the 5 change requests are short, synthetic, and from one author, so results can't support claims about real documents.
- **Retrieval:** it's an easy test here, with only 9 short sections per document.
- **Evidence:** the citation check shows that quotes exist, not that they prove the verdict.
- **Follow-up questions:** these aren't scored, and some are weak.
- **Access control:** the reviewer's name is typed in, with no authentication.
- **Claude adapter:** it has only run against a fake API, and it can't run the full workflow yet.

## Try it

You need Python 3.11 or later. To run the tests and check the data, you don't need a model:

```bash
python -m pip install -e ".[dev,embeddings]"
```

```bash
python eval/validate_cases.py
```

```bash
python -m pytest
```

To run a review, install [Ollama](https://ollama.com) and download the model (about 4.7 GB):

```bash
ollama pull qwen2.5:7b
```

This shows the findings, then exports a report only if you type `approve` and your name:

```bash
python -m reqtrace.cli CR-103
```

Reviews take a few minutes on a laptop CPU. Each run saves its audit log and any report in `runs/`.

## Repository layout

```text
src/reqtrace/            Tools, approval state, audit log, screening, retrieval, and agent workflows
domains/healthcare_it/   Fictional policy and change requests
eval/datasets/           Labelled cases (dev and held-out)
eval/results/            Saved development reports
eval/                    Evaluation, comparison, label review, and figure scripts
tests/                   Automated tests, including approval and tampering behaviour
docs/                    Scenario spec, guidelines, label decisions, results, and images
```

## Next steps

- Address the open injection risk, and test with new attack wording and a harmless-text control
- Add a route to revise and resubmit rejected reviews
- Compare plain tool calling with LangGraph
- Add a FastAPI service and Docker packaging
- Write the governance pack: agent card, permission matrix, and risk register
- Get an independent label review, then run the held-out cases once

## Licence

[MIT](LICENSE)
