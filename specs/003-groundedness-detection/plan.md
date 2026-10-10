# Implementation Plan: Groundedness Detection

**Feature**: `003-groundedness-detection` | **Date**: 2026-10-10 | **Spec**: [spec.md](spec.md)

## Summary

A thin wrapper around the detector that returns a hallucination probability for each answer token with its character range. On top of it: window planning, minimum-aggregation across windows, merging tokens into spans, and the score and verdict. Everything above the wrapper is tested with a fake detector.

## Technical Context

Shared stack: see [001 plan](../001-input-ingestion/plan.md), Technical Context.

- **New dependencies**: `torch`, `transformers` (a version that supports ModernBERT). `lettucedetect` is a test-only dependency used for one parity check.
- **Loading approach**: load directly with `AutoTokenizer` and `AutoModelForTokenClassification`, which the constitution allows. The reason is offsets: the tokenizer returns the character range of every token, which the spec requires and which the packaged token output is not known to provide.
- **Device and model**: the service runs on GPU or CPU. Config holds both models. At start-up `select_model` picks the large model on a GPU and the base model on CPU, unless config forces a model or a device.
- **GPU build of torch**: on Windows, `pip install torch` installs a CPU-only build. A GPU machine needs the CUDA build from the PyTorch package index or the internal mirror. With a CPU-only build, `torch.cuda.is_available()` is false and the base model is selected.

## Constitution Check

| Principle | How this plan meets it |
|---|---|
| I. Offline, safe model loading | `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1` are set before any model import. Loading uses `local_files_only=True`, `use_safetensors=True`, and never passes `trust_remote_code`. Start-up fails if the path has no safetensors weights. Path and revision come from config. No embedding or other model is added. |
| II. Customer data stays in the store | Only item IDs, counts, window numbers, and scores are logged. |
| III. Observes only | Returns a result. No side effects. |
| IV. Interfaces | The rest of the service sees only the `Detector` protocol. The prompt format and label index are verified against the installed package before coding (see Risks). |
| V. Configuration over constants | Model path, revision, device, batch size, token limit, threshold, window size, and overlap are all config. Swapping models is a config change. |
| VI. Tested without the model, exact offsets | Window planning, aggregation, span merging, and scoring are tested with `FakeDetector`. Span offsets are asserted against the original answer. Real-model tests are marked `slow`. |
| VII. Log every signal | The result keeps the aggregated token scores and a threshold-independent maximum probability, so later features can re-threshold without rerunning the model. |

## Project Structure

```
evalsvc/
  types.py                 # add TokenScore, Span, GroundednessResult, ModelInfo
  config.py                # add ModelSettings, DetectionSettings
  interfaces.py            # add Detector protocol
  runtime.py               # set_offline_env
  detector/
    __init__.py
    prompt.py              # format_context
    select.py              # SelectedModel, gpu_available, select_model, detection_settings_for
    model.py               # TransformerDetector, HFTokenCounter
    windows.py             # plan_windows, aggregate_min, merge_spans
  evaluators/
    __init__.py
    groundedness.py        # evaluate_groundedness
tests/
  fakes.py                 # FakeDetector
  unit/test_windows.py
  unit/test_groundedness.py
  slow/test_model_integration.py
```

## Design

### Data structures

```python
class TokenScore:
    start: int            # character range in the answer
    end: int
    prob: float           # probability that the token is unsupported

class Span:
    start: int
    end: int
    text: str             # answer[start:end]
    confidence: float     # highest token probability in the span
    excluded: bool        # lies wholly inside non-factual sentences

class ModelInfo:
    name: str
    revision: str

class GroundednessResult:
    evaluable: bool
    not_evaluable_reason: str | None      # "no_room_for_evidence", "empty_evidence", ...
    verdict: Literal["pass", "fail"] | None
    score: float | None                   # None when there are no factual sentences
    max_span_confidence: float
    max_token_probability: float          # over factual sentences, independent of threshold
    unsupported_spans: list[Span]
    token_scores: list[TokenScore]        # after aggregation
    windows_run: int
    threshold: float
    model: ModelInfo
```

### Functions

```python
# evalsvc/interfaces.py
class Detector(Protocol):
    info: ModelInfo
    max_tokens: int
    def count_tokens(self, text: str) -> int: ...
    def fixed_cost(self, question: str, answer: str, n_passages: int) -> int: ...
    def score_batch(self, contexts: list[list[str]], question: str, answer: str) -> list[list[TokenScore]]: ...

# evalsvc/detector/windows.py
def plan_windows(chunks: list[Chunk], budget: int, window_tokens: int, overlap_tokens: int) -> list[list[Chunk]]: ...
def aggregate_min(per_window: list[list[TokenScore]]) -> list[TokenScore]: ...
def merge_spans(tokens: list[TokenScore], answer: str, threshold: float, sentences: list[Sentence]) -> list[Span]: ...

# evalsvc/evaluators/groundedness.py
def evaluate_groundedness(question: str, chunks: list[Chunk], answer: str, sentences: list[Sentence],
                          detector: Detector, settings: DetectionSettings) -> GroundednessResult: ...
def verdict_from_tokens(tokens: list[TokenScore], answer: str, sentences: list[Sentence],
                        threshold: float) -> tuple[str, float | None, list[Span]]: ...

# evalsvc/detector/model.py
class TransformerDetector:               # implements Detector
    def __init__(self, settings: ModelSettings) -> None: ...
class HFTokenCounter:                    # implements TokenCounter from feature 002
    def __init__(self, detector: TransformerDetector) -> None: ...
```

### Algorithm

1. **Budget**: `budget = detector.max_tokens - detector.fixed_cost(question, answer) - safety_margin`. The fixed cost covers the question, the answer, the prompt wording, and special tokens. Each chunk's cost comes from `detector.passage_cost`, which includes the wrapper around a passage. If the budget is smaller than one chunk, return not evaluable with `no_room_for_evidence`.
2. **Single pass or windows**: if all chunks fit in the budget, use one window with all chunks. Otherwise use `min(window_tokens, budget)` per window.
3. **Window planning**: a window is a run of consecutive whole chunks. The next window starts by stepping back from the end of the previous one until at least `overlap_tokens` are repeated. Every chunk is in at least one window.
4. **Detection**: run windows through `score_batch` in batches of `batch_size`. Each window uses `chunk.context_text` for its passages, with the full question and full answer.
5. **Aggregation**: the answer is tokenized the same way in every window, so tokens line up by character range. For each token take the lowest probability across windows.
6. **Spans**: merge consecutive tokens whose probability is above the threshold. Start is the first token's start, end is the last token's end, confidence is the highest probability. Mark `excluded` when the span lies wholly inside non-factual sentences.
7. **Score**: share of factual sentences that overlap no non-excluded span. `None` if there are no factual sentences.
8. **Verdict**: `fail` if there is at least one non-excluded span, otherwise `pass`.

`verdict_from_tokens` holds steps 6 to 8 so the golden-set harness can apply many thresholds to one detector run.

### Model selection

```python
# evalsvc/detector/select.py
class SelectedModel:
    variant: Literal["large", "base"]
    name: str
    path: str
    revision: str
    device: Literal["cpu", "cuda"]
    threshold: float

def gpu_available() -> bool: ...
def select_model(settings: Settings, has_gpu: bool) -> SelectedModel: ...
def detection_settings_for(settings: Settings, selected: SelectedModel) -> DetectionSettings: ...
```

- **Device**: `cuda` when `model.device` is `cuda`, or is `auto` and a GPU is available. Otherwise `cpu`. A forced `cuda` with no GPU is a config error.
- **Model**: with `model.select = "auto"`, large on `cuda` and base on `cpu`. `"large"` or `"base"` forces one, on whichever device was chosen.
- **No fallback**: if the selected model has no `path`, start-up fails with an error naming the missing key. The other model is never used in its place, because that would change results without anyone knowing.
- **Threshold**: the selected model's own `threshold` when it has one, otherwise `[detection].threshold`. `detection_settings_for` returns the detection settings with that threshold in force.
- **Recording**: `ModelInfo` gains a `device` field, so every result shows the model name, revision, and device.
- `select_model` takes `has_gpu` as an argument, so it is tested without torch or a GPU.

### Model wrapper

- Takes a `SelectedModel`, loads from its `path`, and moves the model and every input batch to its `device`.
- Builds the model input as a pair: the formatted context and question as the first part, the answer as the second, with truncation off. The caller guarantees the fit.
- Reads token character ranges from the tokenizer's offset mapping, keeps only answer tokens, and drops special tokens.
- Applies softmax to the logits and takes the probability of the "unsupported" label.
- Merges sub-word tokens of one word by taking the highest probability, so spans never start or end inside a word.

## Config Keys

```toml
[model]
select = "auto"          # auto (large on GPU, base on CPU), large, base
device = "auto"          # auto, cpu, cuda
batch_size = 4
max_tokens = 8192

[model.large]
name = "lettucedect-large-modernbert-en-v1"
path = "C:/models/lettucedect-large-modernbert-en-v1"
revision = "<pinned commit hash>"
# threshold = 0.6      # optional, chosen from the golden set

[model.base]
name = "lettucedect-base-modernbert-en-v1"
path = "C:/models/lettucedect-base-modernbert-en-v1"
revision = "<pinned commit hash>"

[detection]
threshold = 0.5
window_evidence_tokens = 6000
window_overlap_tokens = 500
safety_margin_tokens = 32
```

## Test Approach

**Unit, with `FakeDetector`** (it marks a token unsupported unless its word appears in the window's context):

- Everything fits: exactly one call, `windows_run == 1`.
- Large evidence: no window exceeds the budget, every chunk is covered, overlap is at least the configured size.
- A claim supported only in the third window is not flagged. A claim supported nowhere is flagged.
- `aggregate_min` on hand-written inputs.
- `merge_spans`: neighbouring tokens merge, a gap splits, offsets reproduce the text, confidence is the maximum.
- Score 6/7 for one flagged sentence in seven. Excluded spans do not lower the score or cause `fail`.
- No factual sentences gives `score=None` and `pass`. No room for evidence gives not evaluable.

**Slow, with the real model on a tiny synthetic fixture**:

- A supported answer passes and an obviously unsupported one fails.
- Parity: spans from `TransformerDetector` match the spans from the `lettucedetect` package's `transformer` method on the same input.
- A patched socket confirms no network call is made.

## Risks and Items to Verify

### Findings (task T012, verified on 2026-10-10)

Checked against `lettucedetect` 0.2.3, `transformers` 5.19.0, `torch` 2.14.1, and the base model at commit `bbd77832f52f9bd87546a3924c032467921f5c34`.

1. **Prompt format.** The wording is in the package's `prompts/qa_prompt_en.txt`, filled by `PromptUtils.format_context` in `detectors/prompt_utils.py`. Each passage becomes a line `passage N: text`. With no question, `prompts/summary_prompt_en.txt` is used. `evalsvc/detector/prompt.py` holds a copy, and a slow test compares it with the installed files.
2. **Input length.** The model and tokenizer accept 8,192 tokens, but the package trains and runs at `max_length = 4096`. The default `model.max_tokens` is therefore 4,096. With this limit, 32,000 tokens of evidence needs about ten windows, not six. Raising it to 8,192 is a config change and should be justified with the golden set.
3. **Label index.** The package reads probability index 1 as "hallucinated". The model's own config names no labels.
4. **Input layout.** The tokenizer is given the pair (prompt, answer), which gives `[CLS] prompt [SEP] answer [SEP]`. The package truncates the prompt when the input is too long. The wrapper never truncates: it raises `DetectorInputError`.
5. **Aggregation differs on purpose.** When the package splits evidence itself, it keeps the highest probability per token across parts. This service keeps the lowest, as the brief requires: a token is supported if any window supports it.
6. **Package dependencies.** The package was installed with `--no-deps`, so the token parity test is skipped when the package cannot be imported. The prompt wording test only reads the package's files.

### Original list

These were the items to check before coding the wrapper.

1. **Prompt format.** The detector was trained on a specific wording that wraps the passages and the question. The wrapper must reproduce it exactly, either by calling the package's own formatting helper or by copying it into `prompt.py` with the package version noted. The parity test guards this.
2. **Trained input length.** The model accepts 8,192 tokens, but the package may truncate at a lower default (possibly 4,096). If so, set `max_tokens` to that value; window planning adapts on its own.
3. **Label index.** Which output label means "unsupported". Believed to be label 1.
4. **Token output fields.** The brief asks to verify the field names of the package's token-level output. This plan does not depend on them, since it reads offsets from the tokenizer, but the parity test uses the span output.
5. **Two models, two score scales.** The large and base models give different probabilities for the same text, so one threshold does not suit both. Each model gets its own threshold from the golden-set sweep (feature 007). Until then both use `[detection].threshold`.
6. **Results from mixed hardware.** A store filled by GPU and CPU machines holds results from two models. Every record carries the model name and device so they can be told apart.
7. **GPU memory.** The large model with 8,192-token inputs may need a smaller `batch_size` on a small GPU. It is a config value.
8. **Revision pinning with a local path.** A local folder has no revision of its own. The plan records the configured revision in every result, and when the path is a hub cache snapshot folder, checks that the folder name equals the configured hash.

## Assumptions Carried From the Spec

Starting threshold 0.5. Span confidence is the highest token probability. No factual sentences gives an empty score and `pass`. No evidence gives not evaluable. Excluded spans are recorded and do not cause `fail`. The service supports GPU and CPU, with the model chosen at start-up.
