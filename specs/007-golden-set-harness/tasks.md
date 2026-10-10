# Tasks: Golden-Set Harness

**Feature**: `007-golden-set-harness` | **Inputs**: [spec.md](spec.md), [plan.md](plan.md)

**Depends on**: features 001, 002, and 003 complete, plus `Components` from feature 006 (task T006 there).

Do the tasks in order. After each task, run its test file with `pytest <test file> -q`. A task is done when the tests named under "Done when" pass. All tests here use `FakeDetector`.

## Setup

- [ ] **T001** Add the config sections
  - Files: `evalsvc/config.py`, `config.example.toml`, `tests/unit/test_config.py`
  - Content: `GoldenSettings`, `SweepSettings`.
  - Done when: tests show the defaults in the plan load; a sweep with `start` above `stop` is rejected; a recall target outside 0 to 1 is rejected.

- [ ] **T002** Build the synthetic golden set
  - Files: `tests/fixtures/golden_synthetic.jsonl`, `tests/fixtures/golden_expected.md`
  - Content: ten invented items with labels and two categories, written so `FakeDetector` gives known scores. The second file records the hand-worked TP, FP, TN, FN, recall, precision, false-alarm rate, and average precision at threshold 0.5.
  - Done when: both files exist and the hand-worked values are shown with their working.

- [ ] **T003** Load the golden set
  - Files: `evalsvc/harness/__init__.py`, `evalsvc/harness/golden.py`, `tests/unit/test_golden.py`
  - Content: `GoldenItem`, `load_golden`, reading label and category from item metadata by the configured keys.
  - Done when: tests show labels map to `is_failure`; a missing label and an unknown label value are each left out and counted; a malformed line is reported with its position; items with no category load with `category=None`; changing the key names in config is honoured.

## User Story 1: Measures

- [ ] **T004** Compute the confusion counts and rates
  - Files: `evalsvc/harness/metrics.py`, `tests/unit/test_metrics.py`
  - Content: `Measures`, `compute_measures`.
  - Done when: tests with hand-written inputs show correct TP, FP, TN, FN, recall, precision, and false-alarm rate; no labelled failures gives empty recall; no predicted failures gives empty precision; no labelled passes gives an empty false-alarm rate; a group below `min_group_size` has `reliable=False`.

- [ ] **T005** Compute the area under the precision-recall curve
  - Files: `evalsvc/harness/metrics.py`, `tests/unit/test_metrics.py`
  - Content: `average_precision`.
  - Done when: tests show a perfect ranking gives 1.0; a hand-worked five-item case gives the expected value; tied scores are handled the same way on every run; no failures gives an empty result.

- [ ] **T006** Score items once
  - Files: `evalsvc/harness/scoring.py`, `tests/unit/test_scoring.py`
  - Content: `ScoredItem`, `score_items`, running preparation and detection once per item and timing it.
  - Done when: tests show one `ScoredItem` per golden item; the fake detector's call count equals the number of evaluable items; not-evaluable items are marked and carry no score; `seconds` is filled.

## User Story 3: Threshold sweep

- [ ] **T007** Sweep thresholds and pick one
  - Files: `evalsvc/harness/metrics.py`, `tests/unit/test_metrics.py`
  - Content: `sweep`, `pick_threshold`, both using `verdict_from_tokens` from feature 003.
  - Done when: tests show one point per threshold in the configured range; recall never rises as the threshold rises; `pick_threshold` returns the highest threshold meeting the target and nothing when no threshold meets it; the sweep makes no detector calls.

## User Story 2: Breakdown

- [ ] **T008** Break results down by category
  - Files: `evalsvc/harness/metrics.py`, `tests/unit/test_metrics.py`
  - Content: `by_category`.
  - Done when: tests show measures per category on the synthetic set; a small category is marked unreliable; items with no category produce the overall measures only.

## User Story 4: Comparison

- [ ] **T009** Compare two configs
  - Files: `evalsvc/harness/metrics.py`, `tests/unit/test_metrics.py`
  - Content: `Comparison`, `compare`, giving differences per measure, the IDs where verdicts differ, and mean and 95th-percentile seconds per item.
  - Done when: tests with two fake detectors built to disagree on known items show the expected ID list, the expected differences, and timing figures for both.

## Report and command

- [ ] **T010** Build and write the report
  - Files: `evalsvc/harness/report.py`, `tests/unit/test_report.py`
  - Content: `Report`, `build_report`, `write_report`, producing `report.md` and `report.json`.
  - Done when: tests show recall on known failures is the first measure in `report.md`; counts of evaluated, not evaluable, unlabelled, and labelled failures are present; the golden file's SHA-256, model name and revision, threshold, and date are recorded; empty measures show their reason; `report.json` loads back with the same numbers; neither file contains the sentinel word.

- [ ] **T011** Add the command
  - Files: `evalsvc/cli/run_eval.py`, `tests/unit/test_cli_run_eval.py`
  - Content: `main`, taking `--config`, `--golden`, `--out`, `--sweep`, and `--compare`; sets offline mode; writes nothing to the result store and calls no judge.
  - Done when: tests calling `main` with fakes show both report files are written; `--sweep` adds the sweep section; `--compare` adds the comparison section; the store folder stays empty.

- [ ] **T012** Check against the hand-worked values
  - Files: `tests/unit/test_cli_run_eval.py`
  - Done when: a test runs the command on `golden_synthetic.jsonl` and every measure equals the value in `golden_expected.md`; a second run gives an identical `report.json` apart from the run ID and date.

## Finish

- [ ] **T013** Run the whole suite
  - Files: none
  - Done when: `pytest -q` passes with no failures and no test loads a model.

- [ ] **T014** Run the first experiment (needs the model and real labelled data)
  - Files: none
  - Done when: `python -m evalsvc.cli.run_eval --config config.toml --golden <golden file> --out reports/ --sweep --compare <base model config>` produces a report, and a threshold and a base-or-large choice are recorded from it.
