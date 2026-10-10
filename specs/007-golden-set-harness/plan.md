# Implementation Plan: Golden-Set Harness

**Feature**: `007-golden-set-harness` | **Date**: 2026-10-10 | **Spec**: [spec.md](spec.md)

## Summary

A command that loads labelled items, runs detection once per item for each model config, computes the measures at any threshold from the stored token scores, and writes a report as Markdown and JSON.

## Technical Context

Shared stack: see [001 plan](../001-input-ingestion/plan.md), Technical Context.

- **No new dependencies.** Recall, precision, false-alarm rate, and area under the precision-recall curve are short formulas and are written in-house, tested against hand-worked values.
- Reuses the parser from feature 001, the pipeline pieces from 002 and 003, and `verdict_from_tokens` from 003 for the sweep.

## Constitution Check

| Principle | How this plan meets it |
|---|---|
| I. Offline, safe model loading | The command calls `set_offline_env` and loads models only from the configured local paths. |
| II. Customer data stays in the store | The report refers to items by ID only. It holds measures, counts, IDs, and timings. A test asserts no item text appears in either report file. |
| III. Observes only | Reads a golden-set file and writes a report. It does not write to the result store or call the judge. |
| IV. Interfaces | Uses the `InputParser` and `Detector` protocols. |
| V. Configuration over constants | Label key and values, category key, sweep range, recall target, and minimum group size come from config. The two model configs are two config files. |
| VI. Tested without the model, exact offsets | All measures are tested with `FakeDetector` and a synthetic golden set. |
| VII. Log every signal | The JSON report keeps per-item scores, verdicts at the chosen threshold, and timings, so runs can be compared over time. Decisions on threshold and model come from this report. |

## Project Structure

```
evalsvc/
  config.py             # add GoldenSettings, SweepSettings
  harness/
    __init__.py
    golden.py           # GoldenItem, load_golden
    scoring.py          # ScoredItem, score_items
    metrics.py          # Measures, compute_measures, average_precision, sweep, pick_threshold
    report.py           # build_report, write_report
  cli/
    run_eval.py         # main
tests/
  fixtures/golden_synthetic.jsonl
  unit/test_metrics.py
  unit/test_golden.py
  unit/test_report.py
  unit/test_cli_run_eval.py
```

## Design

### Data structures

```python
class GoldenItem:
    item: Item
    is_failure: bool          # True when the label says the answer has unsupported content
    category: str | None

class ScoredItem:
    item_id: str
    is_failure: bool
    category: str | None
    evaluable: bool
    score: float              # max_token_probability from feature 003
    token_scores: list[TokenScore]
    sentences: list[Sentence]
    answer_length: int
    seconds: float            # detection time for this item

class Measures:
    n: int
    failures: int
    tp, fp, tn, fn: int
    recall: float | None      # None when there are no labelled failures
    precision: float | None
    false_alarm_rate: float | None
    pr_auc: float | None
    reliable: bool            # False when n is below the minimum group size

class Report:
    run_id, date, golden_file, golden_sha256
    configs: list[ConfigReport]         # one or two
    comparison: Comparison | None
```

### Functions

```python
# evalsvc/harness/golden.py
def load_golden(path: Path, parser: InputParser, settings: GoldenSettings) -> tuple[list[GoldenItem], list[IngestIssue]]: ...

# evalsvc/harness/scoring.py
def score_items(golden: list[GoldenItem], c: Components) -> list[ScoredItem]: ...

# evalsvc/harness/metrics.py
def compute_measures(scored: list[ScoredItem], threshold: float, min_group: int) -> Measures: ...
def average_precision(labels: list[bool], scores: list[float]) -> float | None: ...
def sweep(scored: list[ScoredItem], settings: SweepSettings) -> list[tuple[float, Measures]]: ...
def pick_threshold(points: list[tuple[float, Measures]], recall_target: float) -> float | None: ...
def by_category(scored: list[ScoredItem]) -> dict[str, list[ScoredItem]]: ...

# evalsvc/harness/report.py
def build_report(...) -> Report: ...
def write_report(report: Report, out_dir: Path) -> None: ...     # report.md and report.json

# evalsvc/cli/run_eval.py
def main(argv: list[str] | None = None) -> int: ...
```

### Rules

- **Golden file**: the feature 001 format. The label and category are read from each item's metadata using the configured key names. An item with no label, or an unknown label value, is left out and counted.
- **One detector run per item**: `score_items` runs preparation and detection once and keeps the token scores. The verdict at any threshold is computed with `verdict_from_tokens`, so the sweep costs no extra model time.
- **Definitions**, with "failure" as the positive class:
  - A prediction is positive when the verdict at the threshold is `fail`.
  - Recall = TP / (TP + FN). Precision = TP / (TP + FP). False-alarm rate = FP / (FP + TN).
  - Area under the precision-recall curve is average precision over items ranked by `score`.
  - A measure with a zero denominator is reported as empty with a stated reason, never as zero.
- **Not evaluable items** are counted separately and excluded from all measures.
- **Breakdown**: overall, then per category when items carry one. A group smaller than `min_group_size` is shown with its count and marked unreliable.
- **Sweep**: thresholds from `start` to `stop` in steps of `step`. With a recall target, `pick_threshold` returns the highest threshold whose recall meets it.
- **Comparison**: with a second config, both run on the same items. The report shows each measure side by side with the difference, the IDs where the verdicts differ, and mean and 95th-percentile seconds per item for each.
- **Report order**: recall on known failures first, then precision, false-alarm rate, and area under the curve; then counts; then the breakdown, sweep, and comparison.
- **Repeatability**: the model runs in evaluation mode with no randomness, items are processed in file order, and the run records the golden file's SHA-256, model name and revision, threshold, and date.
- **Command**:
  - `python -m evalsvc.cli.run_eval --config config.toml --golden golden.jsonl --out reports/`
  - add `--sweep` for the threshold sweep
  - add `--compare other_config.toml` for the side-by-side comparison

## Config Keys

```toml
[golden]
label_key = "label"
failure_value = "ungrounded"
pass_value = "grounded"
category_key = "category"
min_group_size = 20

[sweep]
start = 0.05
stop = 0.95
step = 0.05
recall_target = 0.90
```

## Test Approach

All with `FakeDetector` and a synthetic golden set built so the answers are known.

- A ten-item set with hand-worked TP, FP, TN, FN, recall, precision, false-alarm rate, and average precision. The command's numbers must equal them.
- No labelled failures gives empty recall with a reason. No predicted positives gives empty precision.
- A malformed line, a missing label, and a not-evaluable item are each counted and excluded.
- Categories: measures per category; a small category is marked unreliable; no categories gives overall only.
- Sweep: recall never rises as the threshold rises; `pick_threshold` returns the expected value; the detector call count equals the item count, not items times thresholds.
- Comparison: two fake detectors with known disagreements give the expected ID list and differences.
- Two runs on the same input give identical `report.json` apart from the run ID and date.
- Privacy: neither report file contains the fixture sentinel word.

## Risks and Items to Verify

- **Label quality** decides how much the numbers mean. Labels taken from the large judge measure agreement with the judge, not correctness.
- **Small sets**: with 200 to 300 items and few failures, recall has a wide margin of error. The report shows the failure count beside recall so this is visible.
- **Run time on CPU** with the large model and 32,000-token evidence could be long. The comparison's timing output will show whether the base model is needed.
- The recall target of 0.90 is a placeholder until one is agreed.

## Assumptions Carried From the Spec

Item-level labels with the key `label` and values `grounded` and `ungrounded`. False alarms are counted per item. Span-level measures are left out until span labels exist.
