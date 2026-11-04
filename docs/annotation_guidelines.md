# Annotation guidelines

Use these rules to label a change request against one policy rule. Judge only what the change request and policy say, and don't assume anything from general IT knowledge.

## Verdicts

Apply these in order and stop at the first match.

| Step | Question | Verdict |
|---|---|---|
| 1 | Does the text show the rule doesn't apply? | `not_applicable` |
| 2 | Is it unclear whether the rule applies? | `insufficient_evidence` |
| 3 | Does the text show a condition isn't or won't be met? | `contradicted` |
| 4 | Is any required information missing or vague? | `insufficient_evidence` |
| 5 | Are all conditions shown to be met? | `supported` |

## Decision rules

1. **Read each rule literally.** "Completed" needs a finished test (CHG-1), while "completed or scheduled" also accepts a future backup (BCK-1).
2. **Treat a rule on data content as met by declared data.** DAT-1 restricts which data is used, so a stated test data source is enough, even if the test hasn't run. The reviewer should confirm this if the data changes.
3. **Separate missing from impossible.** Use `insufficient_evidence` if the information could still be added before deployment. Use `contradicted` if the text says the requirement won't be met, including when a required item will only exist after deployment.
4. **Don't treat a substitute as equivalent.** Something similar to what a rule requires doesn't count, unless the rule says it does.
5. **Treat named test environments as non-production in this dataset.** Names containing `TEST` or `STAGING` count. This is an assumption of the fictional scenario, not a general IT rule, because a name alone doesn't prove what an environment is.
6. **Use the system tier from section 2.** Tier-specific rules are `not_applicable` to other tiers.
7. **Treat only the stated emergency status as valid.** Don't infer that a change is an emergency.

## Citations

Cite verbatim from the section containing each fact the verdict relies on, including:

- The system tier, when the verdict depends on it
- Emergency status, for CHG-3
- The deployment time, when a backup's timing must be calculated

For `insufficient_evidence`, cite any partial evidence. An empty citation list is allowed if the text says nothing relevant.

## Independent review

Generate a blind sheet, which leaves out the existing verdicts:

```bash
python eval/review_labels.py sheet --output review_sheet.csv
```

A second person fills in the `verdict` column using only this guideline, the policy, and the change requests. They shouldn't see `eval/datasets/` or [`label_decisions.md`](label_decisions.md), which contain the answers. Then compare the results:

```bash
python eval/review_labels.py agreement review_sheet.csv
```

Report the number of cases reviewed, raw agreement, and Cohen's kappa. Discuss any disagreements and record changes in the decision log. Don't quietly change a label to raise the agreement score.

The labels are frozen once this review is complete. Tag that commit and report the tag with the results. Any later label change needs a new tag and a note explaining it.
