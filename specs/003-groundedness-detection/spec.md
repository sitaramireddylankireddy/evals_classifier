# Feature Specification: Groundedness Detection

**Feature**: `003-groundedness-detection`
**Created**: 2026-10-10
**Status**: Draft

## Summary

For one item, find the parts of the answer that the evidence does not support. The result is a list of unsupported spans, a groundedness score, and a pass or fail verdict.

The detector accepts a limited amount of text (8,192 tokens for evidence, question, and answer together). When the evidence is larger, it is checked in overlapping windows and the results are combined so that a claim counts as supported if any window supports it.

## User Scenarios & Testing

### User Story 1 - Flag unsupported text when everything fits (Priority: P1)

As a reviewer, I see which parts of an answer are not backed by the evidence it was given.

**Why this priority**: this is the core purpose of the service.

**Acceptance Scenarios**:

1. **Given** an answer in which every claim is supported by the evidence, **When** it is checked, **Then** there are no unsupported spans and the verdict is `pass`.
2. **Given** an answer with one claim the evidence does not support, **When** it is checked, **Then** a span covering that claim is returned with a confidence value, and the verdict is `fail`.
3. **Given** any returned span, **Then** the original answer cut at the span's start and end equals the span's text.
4. **Given** evidence, question, and answer that fit within the limit, **Then** exactly one detector pass is made.

### User Story 2 - Check evidence larger than the limit (Priority: P1)

As the evaluator, I can check an answer against evidence of about 32,000 tokens.

**Acceptance Scenarios**:

1. **Given** evidence larger than the limit, **When** it is checked, **Then** it is processed in windows of a configured size (default about 6,000 evidence tokens) with a configured overlap (default about 500), each window together with the full question and the full answer.
2. **Given** a claim supported only by evidence in the third window, **When** results are combined, **Then** the claim is not flagged.
3. **Given** a claim supported by no window, **When** results are combined, **Then** the claim is flagged.
4. **Given** the combined result, **Then** every part of the evidence was included in at least one window.
5. **Given** an item, **Then** the number of windows run is reported.

### User Story 3 - Score and verdict (Priority: P1)

As an operator, I get one score and one verdict per item to track and route on.

**Acceptance Scenarios**:

1. **Given** an answer with 7 factual sentences of which 1 contains a flagged span, **Then** the groundedness score is 6/7.
2. **Given** at least one span whose confidence is above the configured threshold, **Then** the verdict is `fail`; otherwise it is `pass`.
3. **Given** an item, **Then** the highest span confidence is reported as `max_span_confidence`, and it is 0 when there are no spans.
4. **Given** a span that lies wholly inside a non-factual sentence, **Then** it does not lower the score.

### User Story 4 - Run on GPU or CPU with the right model (Priority: P1)

As an operator, I can run the service on a machine with or without a GPU. It uses the large model on a GPU and the base model on CPU, and I can see which one produced a result.

**Acceptance Scenarios**:

1. **Given** a machine with a GPU, **When** the service starts with default settings, **Then** the large model is loaded on the GPU.
2. **Given** a machine with no GPU, **When** the service starts with default settings, **Then** the base model is loaded on CPU.
3. **Given** a config that forces one model or one device, **When** the service starts, **Then** that choice is used with no code change.
4. **Given** the selected model has no local path configured, **When** the service starts, **Then** it stops with a clear error and does not switch to the other model.
5. **Given** a config that forces the GPU on a machine without one, **When** the service starts, **Then** it stops with a clear error.
6. **Given** any result, **Then** it records the model name, revision, and device that produced it.
7. **Given** a threshold set for one model, **Then** that threshold is used when that model runs, and the general threshold is used otherwise.
8. **Given** the service at run time, **Then** it makes no outbound network call and loads weights only from the configured local path.

### Edge Cases

- The question and answer alone leave no room for evidence within the limit: the item is marked not evaluable with a reason code.
- The answer has no factual sentences: there is nothing to score.
- The item has no evidence.
- A claim needs two passages that are far apart and never share a window: it may be flagged. This is a known weak spot; such cases go to escalation and are not fixed here.
- Numbers, dates, and amounts: the detector is not relied on for these. Feature 004 covers them.

## Requirements

### Functional Requirements

- **FR-001**: The system MUST produce, for each item: `unsupported_spans` (each with `start`, `end`, `text`, `confidence`), `groundedness_score`, `verdict`, `max_span_confidence`, and `windows_run`.
- **FR-002**: When evidence, question, and answer fit within the token limit, the system MUST use a single pass with all evidence.
- **FR-003**: Otherwise the system MUST use overlapping windows of evidence, each run with the full question and full answer. Window size and overlap MUST come from config.
- **FR-004**: The system MUST combine windows by taking, for each position in the answer, the lowest hallucination probability across all windows.
- **FR-005**: Consecutive answer positions whose combined probability is above the threshold MUST be merged into one span.
- **FR-006**: Span offsets MUST refer to the original, unmodified answer.
- **FR-007**: `groundedness_score` MUST be the share of factual sentences that contain no flagged span.
- **FR-008**: `verdict` MUST be `fail` if any span is above the configured threshold, otherwise `pass`.
- **FR-009**: Model path, model revision, threshold, window size, and overlap MUST come from config. The model revision MUST be pinned.
- **FR-013**: The system MUST run on both GPU and CPU. Config holds two models, large and base, each with its own path and revision.
- **FR-014**: At start-up the system MUST select the large model when a GPU is available and the base model otherwise. Config MUST be able to force either model and either device.
- **FR-015**: If the selected model is not configured, or a forced GPU is not available, the system MUST stop with a clear error. It MUST NOT fall back to the other model.
- **FR-016**: Each model MAY have its own threshold in config. When it has one, that threshold applies whenever that model runs.
- **FR-017**: Every result MUST record the device as well as the model name and revision.
- **FR-010**: The model MUST load from a local path, offline, without executing code shipped with the model.
- **FR-011**: The window-combining and span-merging behaviour MUST be testable with a stand-in detector, with no model weights present.
- **FR-012**: An item that cannot be checked MUST be returned as not evaluable with a reason code, and MUST NOT stop other items.

### Key Entities

- **Unsupported span**: start, end, text, confidence.
- **Window**: a run of consecutive evidence chunks that fits the limit together with the question and answer.
- **Groundedness result**: spans, score, verdict, maximum span confidence, windows run, model name and revision.

## Success Criteria

- **SC-001**: For 100% of returned spans, the offsets reproduce the span text exactly.
- **SC-002**: With a stand-in detector, a claim supported in any one window is never flagged, and a claim supported in none is always flagged.
- **SC-003**: Evidence of 32,000 tokens is checked without exceeding the 8,192-token limit in any pass.
- **SC-004**: Recall on known failures in the golden set is measured by feature 007. The target value is an open question.

## Out of Scope

- Escalation to the large judge (feature 006).
- Explanations for spans (feature 005).
- Fine-tuning the detector and typed hallucination labels.
- Choosing which chunks to check by relevance.

## Open Questions

1. Resolved: the service supports both. It uses the large model on a GPU and the base model on CPU (User Story 4).
2. What is the starting threshold before the golden-set sweep chooses one? 0.5 is assumed.
3. How is a span's confidence defined when it covers several positions: the highest value in the span, or the average? The highest is assumed.
4. When an answer has no factual sentences, what are the score and verdict? Assumed: score is empty and verdict is `pass`.
5. When an item has no evidence, is it `fail` or not evaluable? Not evaluable is assumed.
6. Do spans inside non-factual sentences affect the verdict? Assumed: they are recorded and marked as excluded, and they do not cause `fail`.
7. What recall target on known failures must be met before this is trusted on live items?
