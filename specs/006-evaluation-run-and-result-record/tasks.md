# Tasks: Evaluation Run and Result Record

**Feature**: `006-evaluation-run-and-result-record` | **Inputs**: [spec.md](spec.md), [plan.md](plan.md)

**Depends on**: features 001 to 003 complete. Feature 004 is postponed and feature 005 is not built, so their stages are optional slots that are skipped and named in each record's `stages_skipped`. Wherever a task below mentions check results or span reasons, the test uses a stand-in for that slot, and a second test covers the slot being empty.

Do the tasks in order. After each task, run its test file with `pytest <test file> -q`. A task is done when the tests named under "Done when" pass. All tests here use `FakeDetector` and the stub judge.

## Setup

- [x] **T001** Define the record
  - Files: `evalsvc/records.py`, `tests/unit/test_records.py`
  - Content: `SpanRecord`, `GroundednessRecord`, `EscalationRecord`, `ResultRecord`, `RunSummary`.
  - Done when: tests show a record converts to JSON and back to an equal record, and contains every field named in FR-003 and FR-004 of the spec.

- [x] **T002** Add the config sections
  - Files: `evalsvc/config.py`, `config.example.toml`, `tests/unit/test_config.py`
  - Content: `RunSettings`, `StoreSettings`, `JudgeSettings`.
  - Done when: tests show the defaults in the plan load, and a sample rate outside 0 to 1 is rejected.

- [x] **T003** Define the judge and store protocols
  - Files: `evalsvc/interfaces.py`, `evalsvc/types.py`
  - Content: `LargeJudge`, `ResultStore`, `JudgeRequest`, `JudgeResponse`.
  - Done when: the tests in T004 and T005 assert the implementations satisfy the protocols.

## User Story 1: One record per item

- [x] **T004** Build the store
  - Files: `evalsvc/store/__init__.py`, `evalsvc/store/results.py`, `tests/unit/test_store.py`
  - Content: `JsonlResultStore` with `write`, `get_current`, `iter_current`, and write retries; `build_store`.
  - Done when: tests using a temporary folder show a written record reads back equal; two records for one ID give two lines and the later one as current; `iter_current` yields one record per ID; a write that fails is retried the configured number of times and then raises.

- [x] **T005** Add the judge stand-in
  - Files: `evalsvc/judge.py`, `tests/unit/test_escalation.py`
  - Content: `StubLargeJudge`, which returns a fixed verdict and rationale and records the requests it receives; `build_judge`.
  - Done when: tests show the stub satisfies the protocol and an unknown judge kind in config gives a clear error.

- [x] **T006** Wire the components
  - Files: `evalsvc/pipeline.py`, `tests/unit/test_pipeline.py`
  - Content: `Components` and `build_components`, with a way for tests to pass in a fake detector and a stub judge. Without a detector passed in, it selects the model with `select_model` and applies that model's threshold with `detection_settings_for`.
  - Done when: a test builds components with fakes and a temporary store, without loading a model; a test with model loading patched shows the large model is requested when a GPU is reported and the base model otherwise, and that a model's own threshold reaches the detection settings.

- [x] **T007** Evaluate one item
  - Files: `evalsvc/pipeline.py`, `tests/unit/test_pipeline.py`
  - Content: `evaluate_item` for an evaluable item: chunk, split, detect, check, explain, assemble.
  - Done when: tests show a supported answer gives a `pass` record; an unsupported answer gives a `fail` record whose spans carry `reason_type`, `reason`, and `nearest_chunk_id`; deterministic check results are in the record; `counts`, `threshold`, `evaluated_at`, `model`, and item `metadata` are filled; every span satisfies `answer[start:end] == text`.

- [x] **T008** Evaluate a list
  - Files: `evalsvc/pipeline.py`, `tests/unit/test_pipeline.py`
  - Content: phase 1 of `evaluate_items`, which writes records and builds the `RunSummary`.
  - Done when: tests show three items give three current records keyed by ID; the summary counts match; an empty list writes nothing.

## User Story 4: Keep going when something breaks

- [x] **T009** Record items that cannot be evaluated
  - Files: `evalsvc/pipeline.py`, `tests/unit/test_pipeline.py`
  - Content: not-evaluable items from input; exceptions caught per stage.
  - Done when: tests show an item with an empty answer gets a record with the reason and no verdict; a detector that raises for one item gives that item a not-evaluable record naming the stage, and the other items are evaluated; the summary counts it under `not_evaluable`.

## User Story 2: Escalation

- [x] **T010** Decide which items are sampled
  - Files: `evalsvc/pipeline.py`, `tests/unit/test_escalation.py`
  - Content: `is_sampled`.
  - Done when: tests show the same ID and seed always give the same answer; rate 0 samples nothing and rate 1 samples everything; over 10,000 generated IDs at rate 0.02 the sampled share is between 0.015 and 0.025.

- [x] **T011** Escalate failures and samples
  - Files: `evalsvc/pipeline.py`, `tests/unit/test_escalation.py`
  - Content: phase 2 of `evaluate_items`: build the judge request, call the judge, write a new record version.
  - Done when: tests show a `fail` item is sent to the judge with its flagged claims and full evidence and ends with `escalated=true` and `cause="fail"`; a `pass` item that is not sampled is not sent; a sampled `pass` item is sent with `cause="sample"`; the judge's verdict and rationale are in the record; phase 1 records for all items exist before the first judge call.

- [x] **T012** Survive judge failures
  - Files: `evalsvc/pipeline.py`, `tests/unit/test_escalation.py`
  - Done when: tests show a judge that raises, and a judge that exceeds the time limit, each leave a record with `attempted=true`, `status="failed"`, and an error code; the remaining items are still escalated; the summary counts `escalation_failed`.

## User Story 3: Run in the background

- [x] **T013** Add the command
  - Files: `evalsvc/cli/__init__.py`, `evalsvc/cli/run.py`, `tests/unit/test_cli_run.py`
  - Content: `main`, taking `--config` and `--input`; sets offline mode, loads items, runs, prints the summary.
  - Done when: tests calling `main` with fakes show exit code 0 for a completed run that includes `fail` verdicts; a non-zero exit code when the store cannot be written; input issues from feature 001 counted under `skipped_at_input`; the printed output holds counts and the run ID only.

- [x] **T014** Prove privacy end to end
  - Files: `tests/unit/test_cli_run.py`
  - Done when: a test runs the command on sentinel fixtures, captures standard output and all logs, and asserts the sentinel word appears only in the store file.

## Finish

- [x] **T015** Run the whole suite
  - Files: none
  - Done when: `pytest -q` passes with no failures and no test loads a model.

- [ ] **T016** Try a real run (optional, needs the model)
  - Files: none
  - Done when: `python -m evalsvc.cli.run --config config.toml --input tests/fixtures/items_valid.json` prints a summary and `results.jsonl` appears in the configured store folder.
