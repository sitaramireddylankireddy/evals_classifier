# Implementation Plan: Evaluation Run and Result Record

**Feature**: `006-evaluation-run-and-result-record` | **Date**: 2026-10-10 | **Spec**: [spec.md](spec.md)

## Summary

A pipeline function that takes one item through preparation, detection, checks, and explanations and returns a result record. A run function applies it to a list, writes records to the store, escalates failures and a sample to the judge, and returns a summary. A command-line entry point runs it on a file.

## Technical Context

Shared stack: see [001 plan](../001-input-ingestion/plan.md), Technical Context.

- **No new dependencies.** The store is append-only JSON Lines files written with the standard library. The command uses `argparse`.
- **Delivery**: how the list reaches the service is an open question. Version 1 is a batch command run separately from the evaluated application, which keeps it off the request path. The core `evaluate_items` function takes items in memory, so a queue consumer or an endpoint can wrap it later without changes.

## Constitution Check

| Principle | How this plan meets it |
|---|---|
| I. Offline, safe model loading | The command calls `set_offline_env` before loading the detector. The judge stand-in makes no network call. |
| II. Customer data stays in the store | Records are written only to the configured store directory. The command prints and logs only counts, IDs, and reason codes. A test asserts this. |
| III. Observes only | The command reads an input file and writes to its own store. It never calls back into the evaluated application, and a `fail` verdict triggers nothing but an escalation. |
| IV. Interfaces | `LargeJudge` and `ResultStore` are protocols, each with a stand-in or simple implementation chosen by config. |
| V. Configuration over constants | Sample rate and seed, store location, judge choice, and retry counts come from config. |
| VI. Tested without the model, exact offsets | End-to-end tests use `FakeDetector` and the stub judge. A test asserts that every span in a written record matches the original answer. |
| VII. Log every signal | The record holds every signal from every feature, plus the threshold, the time, item metadata, a schema version, and the judge outcome. |

## Project Structure

```
evalsvc/
  records.py            # ResultRecord and its parts, RunSummary
  config.py             # add RunSettings, StoreSettings, JudgeSettings
  interfaces.py         # add LargeJudge, ResultStore protocols
  judge.py              # StubLargeJudge, build_judge
  pipeline.py           # Components, build_components, evaluate_item, evaluate_items
  store/
    __init__.py
    results.py          # JsonlResultStore, build_store
  cli/
    __init__.py
    run.py              # main
tests/
  unit/test_pipeline.py
  unit/test_store.py
  unit/test_escalation.py
  unit/test_cli_run.py
```

## Design

### Data structures

```python
class SpanRecord:                 # a Span joined with its explanation
    start, end, text, confidence, excluded
    reason_type, reason, nearest_chunk_id

class GroundednessRecord:
    verdict: str | None
    score: float | None
    max_span_confidence: float
    max_token_probability: float
    threshold: float
    unsupported_spans: list[SpanRecord]

class EscalationRecord:
    attempted: bool
    cause: Literal["fail", "sample", "fail_and_sample"] | None
    status: Literal["ok", "failed"] | None
    error_code: str | None
    judge_verdict: str | None
    judge_rationale: str | None

class ResultRecord:
    schema_version: int
    id: str
    evaluated_at: str             # UTC, ISO 8601
    run_id: str
    model: ModelInfo
    evaluable: bool
    not_evaluable_reason: str | None
    groundedness: GroundednessRecord | None
    deterministic_checks: list[CheckResult]
    escalated: bool               # same as escalation.attempted
    sampled: bool
    escalation: EscalationRecord
    windows_run: int
    counts: dict[str, int]        # sentences, factual sentences, chunks, evidence tokens
    metadata: dict[str, Any]      # extra keys that came with the item

class RunSummary:
    run_id: str
    received, evaluated, passed, failed, not_evaluable, skipped_at_input: int
    escalated, escalation_failed: int
```

### Functions

```python
# evalsvc/interfaces.py
class LargeJudge(Protocol):
    def judge(self, request: JudgeRequest) -> JudgeResponse: ...
class ResultStore(Protocol):
    def write(self, record: ResultRecord) -> None: ...
    def get_current(self, item_id: str) -> ResultRecord | None: ...
    def iter_current(self) -> Iterator[ResultRecord]: ...

# evalsvc/pipeline.py
class Components: ...             # settings, nlp, detector, token counter, reason generator, judge, store
def build_components(settings: Settings) -> Components: ...
def evaluate_item(item: Item, c: Components, run_id: str) -> ResultRecord: ...
def evaluate_items(items: list[Item], c: Components) -> RunSummary: ...
def is_sampled(item_id: str, rate: float, seed: str) -> bool: ...

# evalsvc/cli/run.py
def main(argv: list[str] | None = None) -> int: ...
```

### Flow

`evaluate_item`, for one item:

1. If the item is not evaluable, return a record with the reason and no verdict.
2. Chunk the evidence and split the answer (feature 002).
3. Run groundedness detection (feature 003).
4. Run deterministic checks (feature 004).
5. Explain each span (feature 005).
6. Assemble the record.

Any exception in steps 2 to 5 is caught. The item gets a not-evaluable record with a reason code naming the stage, and the run continues.

`evaluate_items`, for a list, in two phases so a slow judge never delays detection:

1. **Phase 1**: evaluate every item and write its record.
2. **Phase 2**: for each record whose verdict is `fail` or that is sampled, call the judge with a time limit. Write a new version of the record with the escalation outcome. A judge error or timeout is recorded as `status="failed"` with an error code.

### Rules

- **Model**: `build_components` calls `gpu_available` and `select_model` from feature 003 once, builds the detector for the selected model, and uses `detection_settings_for` so the selected model's threshold is in force. One model serves the whole run. `RunSummary` gains `model` and `device`, and the command prints them. A store filled from GPU and CPU machines holds results from two models; each record's `model` field tells them apart.
- **Sampling**: `is_sampled` hashes the seed and the item ID to a number between 0 and 1 and compares it with the rate. The result is repeatable, which makes it testable, and over many items the share matches the rate.
- **Judge request**: item ID, question, the text of each non-excluded span with its surrounding sentence, and the full evidence.
- **Store**: one file `results.jsonl` in the store directory, one record per line, never rewritten. The current record for an ID is the latest by `evaluated_at`. This gives history for free and settles re-evaluation of the same ID.
- **Store failure**: a write is retried a configured number of times. If it still fails, the run stops with a non-zero exit code and the summary shows how far it got.
- **Command**: `python -m evalsvc.cli.run --config config.toml --input items.json`. It prints the run summary as counts. Exit code 0 when the run completed, even if some items failed their verdict; non-zero only when the run itself broke.

## Config Keys

```toml
[run]
sample_rate = 0.02
sample_seed = "evalsvc"

[store]
kind = "jsonl"
path = "D:/evalsvc/store"
write_retries = 3

[judge]
kind = "stub"
timeout_seconds = 60
```

## Test Approach

All with `FakeDetector` and the stub judge.

- Three items give three records, each readable back from the store and equal to what was written.
- A record contains every field in FR-003 and FR-004.
- A `fail` item is escalated; a `pass` item that is not sampled is not.
- Sampling: over 10,000 generated IDs, the sampled share is within a small tolerance of the rate; the same ID and seed always give the same answer.
- A judge that raises, and a judge that times out, each leave a record with `status="failed"`.
- An item that makes one stage raise gets a not-evaluable record and the other items are unaffected.
- The same ID evaluated twice gives two lines in the file and one current record.
- An empty list writes nothing and exits 0.
- Privacy: captured standard output and logs from a full run contain no fixture sentinel word.
- Spans in written records satisfy `answer[start:end] == text`.

## Risks and Items to Verify

- A JSON Lines store is simple but slow to look up by ID once it grows large. If lookups matter, a SQLite store can be added behind the same protocol.
- The real judge's request and response shape is unknown. The protocol may need adjusting when it is connected.
- Records contain customer text, so the store directory needs the same access controls as the source data.

## Assumptions Carried From the Spec

Sample rate 2%. Old records are kept and the newest is current. The judge returns a verdict and a rationale. A failed deterministic check does not trigger escalation. Results are written to the store and not returned to the caller.
