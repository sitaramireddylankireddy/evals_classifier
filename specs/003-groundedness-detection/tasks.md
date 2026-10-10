# Tasks: Groundedness Detection

**Feature**: `003-groundedness-detection` | **Inputs**: [spec.md](spec.md), [plan.md](plan.md)

**Depends on**: features 001 and 002 complete.

Do the tasks in order. After each task, run its test file with `pytest <test file> -q`. A task is done when the tests named under "Done when" pass.

Tasks T001 to T011 need no model. Tasks T012 to T016 need the model weights on local disk.

## Setup

- [ ] **T001** Add the types
  - Files: `evalsvc/types.py`, `tests/unit/test_types.py`
  - Content: `TokenScore`, `Span`, `ModelInfo`, `GroundednessResult`.
  - Done when: tests show each model can be built and is frozen.

- [ ] **T002** Add the config sections
  - Files: `evalsvc/config.py`, `config.example.toml`, `tests/unit/test_config.py`
  - Content: `ModelSettings`, `DetectionSettings`.
  - Done when: tests show the defaults in the plan load; a threshold outside 0 to 1 is rejected; an overlap larger than the window is rejected.

- [ ] **T003** Define the detector protocol and the fake
  - Files: `evalsvc/interfaces.py`, `tests/fakes.py`, `tests/unit/test_fakes.py`
  - Content: `Detector` protocol; `FakeDetector`, which scores an answer word as unsupported unless the word appears in the window's context, and records every call it receives.
  - Done when: tests show the fake satisfies the protocol, gives a low probability to a word present in the context and a high one to a word that is absent, and returns character ranges that reproduce each word.

## User Story 2: Windows and aggregation

- [ ] **T004** Plan windows
  - Files: `evalsvc/detector/__init__.py`, `evalsvc/detector/windows.py`, `tests/unit/test_windows.py`
  - Content: `plan_windows`.
  - Done when: tests show chunks that fit give one window; no window exceeds the budget; every chunk is in at least one window; consecutive windows repeat at least `overlap_tokens`; windows hold whole chunks in order.

- [ ] **T005** Aggregate across windows
  - Files: `evalsvc/detector/windows.py`, `tests/unit/test_windows.py`
  - Content: `aggregate_min`.
  - Done when: tests with hand-written inputs show each token takes its lowest probability; one window passes through unchanged; mismatched token ranges between windows raise an error.

## User Stories 1 and 3: Spans, score, and verdict

- [ ] **T006** Merge tokens into spans
  - Files: `evalsvc/detector/windows.py`, `tests/unit/test_windows.py`
  - Content: `merge_spans`.
  - Done when: tests show neighbouring tokens above the threshold form one span; a token at or below the threshold splits spans; `answer[start:end] == text` for every span; confidence is the highest token probability; a span wholly inside non-factual sentences has `excluded=True`.

- [ ] **T007** Compute score and verdict
  - Files: `evalsvc/evaluators/__init__.py`, `evalsvc/evaluators/groundedness.py`, `tests/unit/test_groundedness.py`
  - Content: `verdict_from_tokens`.
  - Done when: tests show one flagged sentence out of seven gives 6/7; any non-excluded span gives `fail`; no spans gives `pass`; excluded spans neither lower the score nor cause `fail`; no factual sentences gives `score=None` and `pass`.

- [ ] **T008** Assemble the evaluator
  - Files: `evalsvc/evaluators/groundedness.py`, `tests/unit/test_groundedness.py`
  - Content: `evaluate_groundedness`, covering the budget, single pass or windows, batching, aggregation, and the result.
  - Done when: tests with `FakeDetector` show input that fits makes exactly one call and `windows_run == 1`; a claim supported only in the third window is not flagged; a claim supported in no window is flagged; `max_span_confidence` is 0 with no spans; `max_token_probability` is filled; the result carries the model name and revision and the threshold.

- [ ] **T009** Handle items that cannot be checked
  - Files: `evalsvc/evaluators/groundedness.py`, `tests/unit/test_groundedness.py`
  - Done when: tests show that when question and answer leave no room for one chunk, the result is not evaluable with `no_room_for_evidence`; no chunks gives `empty_evidence`; neither case raises.

## Model wrapper

- [ ] **T010** Force offline mode
  - Files: `evalsvc/runtime.py`, `tests/unit/test_runtime.py`
  - Content: `set_offline_env`.
  - Done when: a test shows `HF_HUB_OFFLINE` and `TRANSFORMERS_OFFLINE` are both `1` after the call.

- [ ] **T011** Add the model dependencies
  - Files: `pyproject.toml`
  - Content: `torch` and `transformers` as dependencies; `lettucedetect` in a `slow` extra.
  - Done when: `pip install -e ".[dev,slow]"` succeeds and `python -c "import torch, transformers, lettucedetect"` prints nothing.

- [ ] **T012** Verify the three unknowns in the plan
  - Files: `specs/003-groundedness-detection/plan.md`
  - Content: with the package installed and the model on disk, confirm (1) the exact prompt wording the package builds around the passages and the question, and where that helper lives; (2) the maximum input length the package uses; (3) which label index means "unsupported". Ask the assistant for an inspection script to run.
  - Done when: the three answers are written into the "Risks and Items to Verify" section of the plan, and `max_tokens` in `config.example.toml` matches finding (2).

- [ ] **T013** Reproduce the prompt format
  - Files: `evalsvc/detector/prompt.py`, `tests/unit/test_prompt.py`
  - Content: `format_context`, either calling the package's helper or copying its wording with the package version noted in a comment.
  - Done when: a test compares the output for a two-passage example with the exact expected text recorded in T012.

- [ ] **T014** Load the model safely
  - Files: `evalsvc/detector/model.py`, `tests/unit/test_model_loading.py`
  - Content: `TransformerDetector.__init__`, with start-up checks.
  - Done when: tests with the loader patched show it is called with `local_files_only=True` and `use_safetensors=True` and without `trust_remote_code`; a folder with no safetensors weights is rejected; a snapshot folder whose name differs from the configured revision is rejected; `device="auto"` picks CPU when no GPU is present.

- [ ] **T015** Score answers with the model
  - Files: `evalsvc/detector/model.py`, `tests/slow/test_model_integration.py`
  - Content: `score_batch`, `count_tokens`, `fixed_cost`, `HFTokenCounter`; sub-word tokens merged to whole words.
  - Done when: `pytest -m slow tests/slow/test_model_integration.py -q` shows token ranges reproduce the answer's words; `fixed_cost` plus the context token count equals the real input length; an answer supported by the evidence passes; an obviously unsupported answer fails.

- [ ] **T016** Prove parity and no network use
  - Files: `tests/slow/test_model_integration.py`
  - Done when: slow tests show the spans from `TransformerDetector` match the spans from the `lettucedetect` package's `transformer` method on the same synthetic input, and a run with network sockets blocked completes.

## Finish

- [ ] **T017** Run both suites
  - Files: none
  - Done when: `pytest -q` passes without loading a model, and `pytest -m slow -q` passes with the model on disk.
