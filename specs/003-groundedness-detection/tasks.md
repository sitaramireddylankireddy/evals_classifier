# Tasks: Groundedness Detection

**Feature**: `003-groundedness-detection` | **Inputs**: [spec.md](spec.md), [plan.md](plan.md)

**Depends on**: features 001 and 002 complete.

Do the tasks in order. After each task, run its test file with `pytest <test file> -q`. A task is done when the tests named under "Done when" pass.

Tasks T001 to T011 need no model. Tasks T012 to T016 need the model weights on local disk.

## Setup

- [x] **T001** Add the types
  - Files: `evalsvc/types.py`, `tests/unit/test_types.py`
  - Content: `TokenScore`, `Span`, `ModelInfo`, `GroundednessResult`.
  - Done when: tests show each model can be built and is frozen.

- [x] **T002** Add the config sections
  - Files: `evalsvc/config.py`, `config.example.toml`, `tests/unit/test_config.py`
  - Content: `ModelSettings`, `DetectionSettings`.
  - Done when: tests show the defaults in the plan load; a threshold outside 0 to 1 is rejected; an overlap larger than the window is rejected.

- [x] **T003** Define the detector protocol and the fake
  - Files: `evalsvc/interfaces.py`, `tests/fakes.py`, `tests/unit/test_fakes.py`
  - Content: `Detector` protocol; `FakeDetector`, which scores an answer word as unsupported unless the word appears in the window's context, and records every call it receives.
  - Done when: tests show the fake satisfies the protocol, gives a low probability to a word present in the context and a high one to a word that is absent, and returns character ranges that reproduce each word.

## User Story 2: Windows and aggregation

- [x] **T004** Plan windows
  - Files: `evalsvc/detector/__init__.py`, `evalsvc/detector/windows.py`, `tests/unit/test_windows.py`
  - Content: `plan_windows`.
  - Done when: tests show chunks that fit give one window; no window exceeds the budget; every chunk is in at least one window; consecutive windows repeat at least `overlap_tokens`; windows hold whole chunks in order.

- [x] **T005** Aggregate across windows
  - Files: `evalsvc/detector/windows.py`, `tests/unit/test_windows.py`
  - Content: `aggregate_min`.
  - Done when: tests with hand-written inputs show each token takes its lowest probability; one window passes through unchanged; mismatched token ranges between windows raise an error.

## User Stories 1 and 3: Spans, score, and verdict

- [x] **T006** Merge tokens into spans
  - Files: `evalsvc/detector/windows.py`, `tests/unit/test_windows.py`
  - Content: `merge_spans`.
  - Done when: tests show neighbouring tokens above the threshold form one span; a token at or below the threshold splits spans; `answer[start:end] == text` for every span; confidence is the highest token probability; a span wholly inside non-factual sentences has `excluded=True`.

- [x] **T007** Compute score and verdict
  - Files: `evalsvc/evaluators/__init__.py`, `evalsvc/evaluators/groundedness.py`, `tests/unit/test_groundedness.py`
  - Content: `verdict_from_tokens`.
  - Done when: tests show one flagged sentence out of seven gives 6/7; any non-excluded span gives `fail`; no spans gives `pass`; excluded spans neither lower the score nor cause `fail`; no factual sentences gives `score=None` and `pass`.

- [x] **T008** Assemble the evaluator
  - Files: `evalsvc/evaluators/groundedness.py`, `tests/unit/test_groundedness.py`
  - Content: `evaluate_groundedness`, covering the budget, single pass or windows, batching, aggregation, and the result.
  - Done when: tests with `FakeDetector` show input that fits makes exactly one call and `windows_run == 1`; a claim supported only in the third window is not flagged; a claim supported in no window is flagged; `max_span_confidence` is 0 with no spans; `max_token_probability` is filled; the result carries the model name and revision and the threshold.

- [x] **T009** Handle items that cannot be checked
  - Files: `evalsvc/evaluators/groundedness.py`, `tests/unit/test_groundedness.py`
  - Done when: tests show that when question and answer leave no room for one chunk, the result is not evaluable with `no_room_for_evidence`; no chunks gives `empty_evidence`; neither case raises.

## User Story 4: Automatic model selection

These two tasks were added after T001 to T017 were numbered. They need no model and come before the model wrapper.

- [x] **T018** Hold both models in config
  - Files: `evalsvc/config.py`, `evalsvc/types.py`, `config.example.toml`, `tests/unit/test_config.py`
  - Content: `[model]` with `select` and `device`; `[model.large]` and `[model.base]`, each with `name`, `path`, `revision`, and an optional `threshold`; `ModelInfo` gains `device`.
  - Done when: tests show both models have default names and empty paths; a file can set each model's path, revision, and threshold; an unknown `select` value and a model threshold outside 0 to 1 are rejected.

- [x] **T019** Select the model from the hardware
  - Files: `evalsvc/detector/select.py`, `tests/unit/test_select.py`
  - Content: `SelectedModel`, `gpu_available`, `select_model`, `detection_settings_for`.
  - Done when: tests show a GPU selects the large model on `cuda`; no GPU selects the base model on `cpu`; `select` forces a model on either device; `device = "cpu"` selects base even with a GPU; `device = "cuda"` with no GPU is an error; a missing path for the selected model is an error and not a fallback; a model's own threshold is used when set.

- [x] **T020** Prove selection and the large model with real weights
  - Files: `tests/slow/test_model_selection.py`
  - Content: slow tests that go through `select_model` and `TransformerDetector` with real model folders, named by `EVALSVC_TEST_MODEL_PATH` (base) and `EVALSVC_TEST_LARGE_MODEL_PATH` (large).
  - Done when: `pytest -m slow tests/slow/test_model_selection.py -q` shows the large model loads and flags the wrong number, and automatic selection loads the large model on a GPU machine and the base model on a CPU machine.

## Model wrapper

- [x] **T010** Force offline mode
  - Files: `evalsvc/runtime.py`, `tests/unit/test_runtime.py`
  - Content: `set_offline_env`.
  - Done when: a test shows `HF_HUB_OFFLINE` and `TRANSFORMERS_OFFLINE` are both `1` after the call.

- [x] **T011** Add the model dependencies
  - Files: `pyproject.toml`
  - Content: `torch` and `transformers` as dependencies; `lettucedetect` in a `slow` extra.
  - Done when: `pip install -e ".[dev,slow]"` succeeds and `python -c "import torch, transformers, lettucedetect"` prints nothing.

- [x] **T012** Verify the three unknowns in the plan
  - Files: `specs/003-groundedness-detection/plan.md`
  - Content: with the package installed and the model on disk, confirm (1) the exact prompt wording the package builds around the passages and the question, and where that helper lives; (2) the maximum input length the package uses; (3) which label index means "unsupported". Ask the assistant for an inspection script to run.
  - Done when: the three answers are written into the "Risks and Items to Verify" section of the plan, and `max_tokens` in `config.example.toml` matches finding (2).

- [x] **T013** Reproduce the prompt format
  - Files: `evalsvc/detector/prompt.py`, `tests/unit/test_prompt.py`
  - Content: `format_context`, either calling the package's helper or copying its wording with the package version noted in a comment.
  - Done when: a test compares the output for a two-passage example with the exact expected text recorded in T012.

- [x] **T014** Load the model safely
  - Files: `evalsvc/detector/model.py`, `tests/unit/test_model_loading.py`
  - Content: `TransformerDetector.__init__`, taking a `SelectedModel`, with start-up checks.
  - Done when: tests with the loader patched show it is called with `local_files_only=True` and `use_safetensors=True` and without `trust_remote_code`; a folder with no safetensors weights is rejected; the model is moved to the selected device; `info` carries the selected name, revision, and device.

- [x] **T015** Score answers with the model
  - Files: `evalsvc/detector/model.py`, `tests/slow/test_model_integration.py`
  - Content: `score_batch`, `count_tokens`, `fixed_cost`, `HFTokenCounter`; sub-word tokens merged to whole words.
  - Done when: `pytest -m slow tests/slow/test_model_integration.py -q` shows token ranges reproduce the answer's words; `fixed_cost` plus the context token count equals the real input length; an answer supported by the evidence passes; an obviously unsupported answer fails.

- [x] **T016** Prove parity and no network use
  - Files: `tests/slow/test_model_integration.py`
  - Done when: slow tests show the spans from `TransformerDetector` match the spans from the `lettucedetect` package's `transformer` method on the same synthetic input, and a run with network sockets blocked completes.

## Finish

- [x] **T017** Run both suites
  - Files: none
  - Done when: `pytest -q` passes without loading a model, and `pytest -m slow -q` passes with the model on disk.
