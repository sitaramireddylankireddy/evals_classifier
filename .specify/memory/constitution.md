# Evalsvc Constitution

Evalsvc is a generic groundedness (hallucination) detection service for banking applications that use language models. For each item it receives (a question, the evidence, and an answer), it flags text in the answer that the evidence does not support.

## Core Principles

### I. Offline, Pinned, Safe Model Loading (NON-NEGOTIABLE)

- Model weights MUST load from a local path or the internal registry. `HF_HUB_OFFLINE=1` MUST be set, and the service MUST make no outbound network calls at run time.
- `trust_remote_code=True` MUST never be used. Only safetensors weights are allowed.
- The model path and revision hash MUST come from config and MUST be pinned.
- Only the `transformer` method of `lettucedetect`, or direct loading with `AutoModelForTokenClassification`, may be used. Any feature that calls an external LLM service is forbidden.
- Models from BAAI (BGE) and Alibaba (GTE, Qwen) MUST NOT be added. If embeddings are needed later, use `ibm-granite/granite-embedding-english-r2`.

Rationale: the service runs in a bank environment, and these are compliance requirements.

### II. Customer Data Stays in the Service Store (NON-NEGOTIABLE)

- Raw customer text MUST NOT be written anywhere outside the service's own store. This includes application logs, error messages, metrics, and test fixtures.
- Logs may carry item IDs, chunk IDs, offsets, scores, and counts.
- Test fixtures MUST use synthetic text.

Rationale: customer text is personal data.

### III. The Evaluator Observes, It Never Changes the Evaluated Application

- Evaluation MUST run asynchronously and off the request path.
- The evaluator MUST NOT alter, block, or prune what the evaluated application receives or produces at run time.
- A `fail` verdict is a signal for escalation and review. It does not stop or rewrite a response.

Rationale: a wrong evaluator must not be able to harm a customer outcome.

### IV. Unknown and External Systems Sit Behind Interfaces

- Anything outside this service, or not yet confirmed, MUST be reached through a protocol with a stub: `InputParser`, `LargeJudge`, `ReasonGenerator`.
- A format or external behaviour MUST NOT be hard-coded until it is confirmed against the real system.
- Assumptions about third-party packages MUST be verified against the installed version before code relies on them.

Rationale: the input format and the judge are owned elsewhere and can change.

### V. Configuration Over Constants

- Model path and revision, thresholds, window size and overlap, chunk sizes, sample rates, the non-factual sentence rules, and the required-field list MUST come from config.
- Two model configs MUST be swappable and comparable without code changes.
- The service is generic. Code MUST NOT contain the names, fields, or rules of a specific application or workflow. Anything specific to a use case comes from config.

Rationale: thresholds are chosen from data, base and large models must be compared side by side, and the same service must serve more than one banking use case.

### VI. Tested Without the Model, Exact on Offsets

- Core logic (window aggregation, sentence splitting, chunking, deterministic checks, explanations) MUST have unit tests that run with a fake detector and no model weights.
- Every span and check failure MUST map back to the exact characters of the original answer. Offset correctness MUST be tested.
- Tests that need the real model MUST be marked slow and kept to a tiny fixture.

Rationale: the test suite must run anywhere, and a span that points at the wrong text is useless to a reviewer.

### VII. Log Every Signal, Decide From Data

- Every result record MUST include all computed signals, even those no feature uses yet.
- Thresholds and model choice MUST be justified by the golden-set harness: recall on known failures first, then precision and false-alarm rate.
- Amounts, dates, percentages, and policy references are checked by deterministic code. The detector is not relied on for them.

Rationale: routing and retraining in later phases depend on this history, and a missed failure costs more than a false alarm.

## Technology and Scope Constraints

- Language: Python 3.14.
- Detector: `KRLabsOrg/lettucedect-large-modernbert-en-v1` on a GPU and `KRLabsOrg/lettucedect-base-modernbert-en-v1` on CPU. The service MUST run on either. At start-up it selects the large model when a GPU is available and the base model otherwise; config can force either model or either device.
- Both models MUST be configured with their own local path and pinned revision. If the selected model is not configured, the service MUST stop with a clear error. It MUST NOT fall back to the other model without the operator knowing.
- Every result MUST record the model name, revision, and device that produced it. A threshold is chosen per model from the golden set, since the two models score differently.
- Context, question, and answer together MUST fit in 8,192 tokens; larger evidence uses sliding windows.
- Sentence splitting: spaCy.
- Current scope is groundedness detection only: the detector, sliding windows, deterministic checks, rule-based explanations, result records, and the golden-set harness.
- Version 1 has no embedding model, no reranker, and no LLM-written explanations.
- Out of scope for now, but the code MUST stay open to them: the unnecessary-evidence evaluator and its ablation harness, fine-tuning on internal labels, typed hallucination labels, completeness checks, confidence-based routing, embedding-based chunk selection.
- A new dependency or model MUST be checked against Principles I and II before it is added.

## Development Workflow and Quality Gates

- Work follows spec-driven development: specification, then plan, then tasks, then implementation. Code is not written for a feature that has no specification.
- Each plan MUST include a constitution check listing how it meets Principles I to VII.
- A change is complete only when its unit tests pass without the model and its offsets are tested.
- Open questions MUST be recorded in the specification and resolved, or placed behind an interface, before implementation.
- The AI assistant does not execute commands in this repository. It provides code and the steps to run it; the developer runs them.

## Governance

- This constitution takes precedence over other project guidance. Where a specification, plan, or task conflicts with it, the constitution wins or is amended first.
- Amendments are made by editing this file with a stated reason, and the version is updated in the same change.
- Versioning: MAJOR for removing or redefining a principle, MINOR for adding a principle or section, PATCH for clarifications.
- Principles I and II may be changed only with approval from the bank's security and compliance owners.
- Every review checks the change against the principles. A deviation MUST be justified in writing in the plan.

**Version**: 1.2.0 | **Ratified**: 2026-10-10 | **Last Amended**: 2026-10-10
