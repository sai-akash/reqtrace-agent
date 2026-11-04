# Citation output: development results

**These are development results, not a final evaluation.** The fixes were chosen after looking at these 24 cases, so the scores are optimistic. The held-out split wasn't used.

| Setting | Value |
|---|---|
| Labels | `labels-v1`, frozen without an independent human review |
| Model | `qwen2.5:7b` through Ollama, temperature 0, seed 42 |
| Split | `dev`: 24 cases from 3 change requests, which aren't independent |
| Assessor | One call per rule, with no agent or retries |

## What changed

The Ollama output schema is now built for each call. It allows only the supplied section titles, requires at least one citation unless the verdict is `insufficient_evidence`, and allows at most 6 citations. The schema controls the output's shape, so quotes still go through the citation check.

The Claude assessor keeps its earlier, looser schema. It hasn't been run on a real model, and none of these results apply to it.

## Results

| Metric | `oracle` before | `oracle` after | `semantic` before | `semantic` after |
|---|---:|---:|---:|---:|
| Accuracy before check | 0.88 | 0.88 | 0.83 | 0.83 |
| Accuracy after check | 0.54 | 0.88 | 0.29 | 0.79 |
| Macro-F1 after check | 0.53 | 0.88 | 0.27 | 0.79 |
| Abstention precision after check | 0.29 | 0.80 | 0.22 | 0.67 |
| Abstention recall after check | 1.00 | 1.00 | 1.00 | 1.00 |
| Quotes found in the cited section | 0.93 | 1.00 | 0.82 | 0.96 |
| Gold sections cited | 0.47 | 0.83 | 0.30 | 0.67 |
| Gold facts covered | 0.42 | 0.76 | 0.27 | 0.64 |
| Correct after check with all gold facts | 0.38 | 0.67 | 0.08 | 0.46 |
| Cases with no citations | 9 | 1 | 15 | 4 |
| Correct verdicts changed by a downgrade | 8 | 0 | 13 | 1 |
| Failed calls | 0 | 0 | 0 | 0 |

No raw verdict changed. The schema fixed citation output, not reasoning, so accuracy before the check is the same.

"Gold facts covered" is an approximation. It can't recognise a different quote that states the same fact.

## Remaining failures

**Wrong verdicts**

| Case | Gold | Model | Run |
|---|---|---|---|
| `HIT-101-CHG-1` | `supported` | `contradicted` | `semantic` |
| `HIT-101-CHG-3` | `supported` | `contradicted` | `oracle` |
| `HIT-102-CHG-1` | `supported` | `contradicted` | `semantic` |
| `HIT-102-CHG-3` | `not_applicable` | `insufficient_evidence` | `semantic` |
| `HIT-103-CHG-1` | `contradicted` | `not_applicable` | Both |
| `HIT-103-DAT-1` | `not_applicable` | `insufficient_evidence` | `oracle` |

These verdicts all kept verified quotes or abstained, so the citation check can't catch them.

**Citation problems**

- **Incomplete evidence:** verdicts can pass while leaving out required facts. For example, `HIT-101-CHG-2` kept `supported` while citing the rollback time without the Tier 1 classification.
- **Unverified quote:** in `semantic`, `HIT-102-SEC-1` quoted rule text under a change request section. The check rejected it and downgraded a correct verdict.
- **Abstaining without citations:** this is still allowed, and it's the only way to return no citations. Requiring citations could push a model towards abstaining. That didn't happen here, because no raw verdict changed, but check for it with other models.

## Prompt change tried and rejected

One general prompt change asked for text only from the change request and a separate citation for each condition. On `oracle`, accuracy after the check fell from 0.88 to 0.83, gold facts covered fell from 0.76 to 0.73, and a quote failed verification. It fixed `HIT-103-CHG-1` but broke `HIT-102-CHG-3`, so it was removed. `semantic` wasn't run for this change.

No further prompt tuning was attempted, to avoid fitting the prompt to 24 cases.

## Limitations

- **Easy retrieval:** the embedding retriever had every gold section in its top 3 in the baseline run. Documents are short and have only 9 sections.
- **Small sample:** one case moves accuracy by about 0.04, and cases from the same change request are related.
- **Labels:** the labels have had no independent human review.
- **Synthetic data:** the documents are fictional and cleaner than real change requests.

## Reports

Reports are in `eval/results/`: `baseline/` (commit `7bb513e`), `schema/` (commit `55161a0`, clean tree), and the rejected `prompt/` attempt (uncommitted code, so not reproducible from its recorded commit). The `schema/` runs were repeated on this computer and gave identical case details for all 24 cases. To compare two:

```bash
python eval/compare_reports.py eval/results/baseline/oracle_dev.json eval/results/schema/oracle_dev.json
```
