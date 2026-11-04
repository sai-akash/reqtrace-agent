# Agent workflow: development results

**These are development results, not a final evaluation.** The design was chosen after looking at dev cases, so the scores are optimistic. The held-out split wasn't used.

| Setting | Value |
|---|---|
| Labels | `labels-v1`, frozen without an independent human review |
| Model | `qwen2.5:7b` through Ollama, temperature 0, seed 42 |
| Split | `dev`: 24 cases from 3 change requests, which aren't independent |

## What was built

- **Tools:** `read_change_request`, `search_policy`, `verify_quote`, `save_finding`, `request_approval`, and `export_report`, with refused calls logged.
- **Approval:** findings lock when approval is requested. Only code outside the model's tools can record a person's decision, and export needs that approval and unchanged findings.
- **Audit log:** one JSON line per event, each chained to the hash of the previous entry.
- **Terminal review:** `python -m reqtrace.cli CR-101` shows the findings, then exports only after a named person types `approve`. It accepts dev change requests only.

## Three ways of running the review

| Mode | Who picks each step | How the verdict is produced | Scope | Accuracy after check |
|---|---|---|---|---:|
| `free` | Model | Tool-call arguments | CR-101, 8 cases | 0.38 (3 of 8) |
| `scoped` | Model, with one conversation per rule | Tool-call arguments | CR-101, 8 cases | 0.13 (1 of 8) |
| `workflow` | Code | Schema-limited output | All dev, 24 cases | 0.79 (19 of 24) |

**`workflow` is the default.** The two model-driven modes ran on one change request only, so that comparison is limited. It also applies only to this small local model. A stronger model might do far better with tool calling, and that hasn't been tested.

## `workflow` results (24 cases)

| Metric | Value |
|---|---:|
| Accuracy before check | 0.83 |
| Accuracy after check | 0.79 |
| Macro-F1 after check | 0.79 |
| Quotes found in the cited section | 0.96 |
| Gold facts covered | 0.64 |
| Reviews reaching approval | 3 of 3 |
| Tool calls accepted | All |
| Export attempts by the model | 0 |
| Approval bypass count | 0 |
| Audit log problems | 0 |

All 24 verdicts match the single-call `semantic` run, as expected, because they use the same model, retriever, and prompt. This workflow adds controls but doesn't improve reasoning. In `workflow` the model doesn't choose tools, so the acceptance and export-attempt figures show that the code followed the process, not that the model chose well.

Follow-up questions haven't been scored. Some are weak, such as `HIT-102-CHG-1`, which questions a test that met the rule. That verdict was wrong, so the question was too. A person needs to check them.

## Prompt injection: partly mitigated, still open

The spec requires that hidden instructions don't change verdicts. **This requirement still isn't met.**

Each test added one attack to the last section of each change request, which reached the model only when that section was retrieved. Changes are counted against the clean run across 24 verdicts.

| Attack | Text style | Screen flags it? | Verdicts changed, no screen | Verdicts changed, with screen |
|---|---|---|---:|---:|
| `system_override` | Direct instruction, names a tool | Yes | 6 | 0 (run) |
| `addressed_note` | Note addressed to the AI reviewer | Yes | 3 | 0 (input identical to clean) |
| `obfuscated` | Instruction with altered spelling | No | 2 | 2 (input unchanged by screen) |
| `false_claim` | False compliance claim in plain prose | No | 1 | 1 (input unchanged by screen) |

Only the screened `system_override` case was run with the screen on. For the other three, the screened document was compared with the input shown, so the result follows from fixed inputs and the repeatable runs seen earlier.

In all of these runs, every review reached approval, the model made no export attempts, and the approval bypass count was 0.

### The screen

`src/reqtrace/screening.py` uses rules to find sentences that look like instructions to an AI. It hides them from the model, so a quote from them fails the citation check. It also logs them, shows them to the reviewer, includes them in the exported report, and includes them in the digest the reviewer approves. It flagged nothing in the 3 clean dev documents, so clean results don't change.

### What this does and doesn't show

- **The result is limited:** the rules were written alongside these attacks, so 0 changes doesn't show how they'd handle new phrasing. All the attacks were one fixed string in one position.
- **Accuracy hides the damage:** `addressed_note` raised accuracy to 0.88 because some verdicts happened to change to the right answer. Count changed verdicts, not accuracy.
- **Not every change shows the attack worked:** the model may also react to any added text, and no harmless-text control was run. Some changes may be noise, and only `system_override` was quoted in the findings.
- **The screen is not the main control:** text written as ordinary evidence, like `false_claim`, can't be separated by pattern matching. Human review and the model having no route to approval or export remain the real safeguards.
- **False positives:** a real document that discusses AI or quotes such text would lose those sentences. The reviewer sees them, but the model doesn't.
- **Not checked:** the held-out documents haven't been screened, so the false positive result covers dev only.

## Limits

- **Audit log:** the chain reveals edits, reordering, and removal, except removal from the end of the file. Someone who can rewrite the whole file can rebuild the chain, so the latest hash would need storing elsewhere.
- **Terminal review:** tests cover it with a fake assessor. It hasn't been run end to end with a real model and a person.
- **Reviewer identity:** the name is typed in, with no authentication.
- **Rejection:** a rejected review ends there, with no route to revise and resubmit.
- **Claude:** the workflow's follow-up step exists only for Ollama, so Claude can't run this workflow yet.
- **Data:** easy retrieval, a small sample, unreviewed labels, and synthetic documents all still apply. See the [citation results](dev_citation_results.md).

## Reports

Reports are in `eval/results/agent/`: `free_cr101.json`, `scoped_cr101.json`, and `workflow_hostile_dev.json` are earlier runs from uncommitted code. `workflow_dev.json` comes from commit `06aba0f`, and the `attack_*.json` files come from `f4b6224`. Those two commits differ only in a report flag and saved reports, and repeated runs on this computer gave identical verdicts and citations.
