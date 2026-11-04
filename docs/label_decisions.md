# Label decision log

**This file contains answers. Independent reviewers shouldn't read it until their review is finished.**

| Case | Verdict | Decision |
|---|---|---|
| `HIT-103-CHG-1` | `contradicted` | "Local testing" could have left room for testing elsewhere, so the source text in CR-103 now says no non-production testing is planned. Vendor certification doesn't count as a recorded test (rule 4). |
| `HIT-103-DAT-1` | `not_applicable` | Uses the same revised CR-103 text. With no test planned, no test data is used. |
| `HIT-103-SEC-1` | `insufficient_evidence` | Kept as a deliberately hard case. "Remote assistance" might not mean remote access, so applicability is unclear (step 2). |
| `HIT-105-DAT-1` | `supported` | Kept under rule 2, but a reasonable reviewer could disagree. Always include it in the independent review. If they disagree, recheck the DAT-1 wording and record the reasoning here, rather than changing the label automatically. |

## Citation update

The citation rules added evidence to 10 cases that relied on a fact outside their original quote. No verdict changed.

- **Dev:** `HIT-101-CHG-2`, `HIT-101-CHG-3`, `HIT-101-CHG-4`, `HIT-103-CHG-2`, `HIT-103-CHG-3`, `HIT-103-CHG-4`
- **Held-out:** `HIT-104-CHG-3`, `HIT-104-CHG-4`, `HIT-104-BCK-1`, `HIT-105-CHG-2`

## Review history

Independent review: not done yet.
