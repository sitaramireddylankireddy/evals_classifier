# Expected results for golden_synthetic.jsonl

Worked by hand for the fake detector used in the tests, at threshold 0.5. The tests in `tests/unit/test_cli_run_eval.py` compare the harness output with these values.

## How the fake detector scores

It marks an answer word as unsupported when the same word is not in the evidence. An item's score is 0.95 if any word is unsupported and 0.05 otherwise. So an item is predicted as a failure when it has at least one word that is not in the evidence.

## Item by item

| ID | Category | Label | Word not in the evidence | Score | Predicted | Outcome |
|---|---|---|---|---|---|---|
| g-01 | cards | grounded | none | 0.05 | pass | passed correctly |
| g-02 | cards | grounded | none | 0.05 | pass | passed correctly |
| g-03 | loans | grounded | none | 0.05 | pass | passed correctly |
| g-04 | loans | grounded | none | 0.05 | pass | passed correctly |
| g-05 | cards | grounded | "usually" | 0.95 | fail | false alarm |
| g-06 | cards | ungrounded | "£9" | 0.95 | fail | flagged correctly |
| g-07 | cards | ungrounded | "2" | 0.95 | fail | flagged correctly |
| g-08 | loans | ungrounded | "£900" | 0.95 | fail | flagged correctly |
| g-09 | loans | ungrounded | none: every word is in the evidence | 0.05 | pass | missed failure |
| g-10 | loans | ungrounded | "yearly" | 0.95 | fail | flagged correctly |

## Overall

- Flagged correctly (TP) = 4, false alarms (FP) = 1, passed correctly (TN) = 4, missed failures (FN) = 1.
- Recall = TP / (TP + FN) = 4 / 5 = 0.8.
- Precision = TP / (TP + FP) = 4 / 5 = 0.8.
- False-alarm rate = FP / (FP + TN) = 1 / 5 = 0.2.
- Area under the precision-recall curve = 0.74. There are two distinct scores:
  - at 0.95, five items are predicted and four are failures: recall 0.8, precision 0.8, which adds 0.8 × 0.8 = 0.64;
  - at 0.05, all ten are predicted and five are failures: recall 1.0, precision 0.5, which adds (1.0 − 0.8) × 0.5 = 0.10.

## By category

| Category | TP | FP | TN | FN | Recall | Precision | False-alarm rate |
|---|---|---|---|---|---|---|---|
| cards | 2 | 1 | 2 | 0 | 2 / 2 = 1.0 | 2 / 3 = 0.667 | 1 / 3 = 0.333 |
| loans | 2 | 0 | 2 | 1 | 2 / 3 = 0.667 | 2 / 2 = 1.0 | 0 / 2 = 0.0 |

## Threshold sweep

Scores are only 0.05 or 0.95, so the predictions are the same at every threshold from 0.05 to 0.90: recall 0.8. At 0.95 nothing is predicted, because 0.95 is not above 0.95: recall 0.

With a recall target of 0.8, the highest threshold that meets it is 0.90. With a target of 0.9, no threshold meets it.
