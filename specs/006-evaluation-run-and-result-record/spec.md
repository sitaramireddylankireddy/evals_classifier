# Feature Specification: Evaluation Run and Result Record

**Feature**: `006-evaluation-run-and-result-record`
**Created**: 2026-10-10
**Status**: Draft

## Summary

Run the whole check for a list of items and keep the outcome. For every item, the service prepares the text, detects unsupported spans, runs the deterministic checks, explains the spans, and writes one result record keyed by the item ID.

Failed items, plus a small random sample of all items, are sent to the existing large judge. Evaluation covers 100% of items and runs in the background, away from the evaluated application's request path.

## User Scenarios & Testing

### User Story 1 - One record per item (Priority: P1)

As an operator, I can look up an item by its ID and see one complete result for it.

**Why this priority**: this is the service's output. Everything else is a part of it.

**Acceptance Scenarios**:

1. **Given** a list of three items, **When** it is evaluated, **Then** three result records are written, each keyed by its item ID.
2. **Given** a result record, **Then** it contains: item ID, model name and revision, the groundedness verdict, score, maximum span confidence, the unsupported spans with their reasons, the deterministic check results, whether it was escalated, and the number of windows run.
3. **Given** a signal that no feature uses yet, **Then** it is still in the record.
4. **Given** a stored record, **When** it is read back, **Then** it equals what was written.

### User Story 2 - Escalate failures and a sample to the large judge (Priority: P1)

As a quality owner, I want every failed item looked at by the large judge, and a random sample of all items, so the detector's own accuracy can be tracked.

**Acceptance Scenarios**:

1. **Given** an item whose verdict is `fail`, **When** it is evaluated, **Then** the large judge is called with the flagged claims and the full evidence, and the record shows `escalated: true`.
2. **Given** an item whose verdict is `pass` and that is not sampled, **Then** the judge is not called and the record shows `escalated: false`.
3. **Given** a configured sample rate, **When** many items are evaluated, **Then** about that share of items are sent to the judge regardless of verdict, and the record says the item was sampled.
4. **Given** the judge returns a result, **Then** it is stored in the record.
5. **Given** the judge fails or is unavailable, **Then** the record is still written, and it shows that escalation was attempted and failed.

### User Story 3 - Run in the background on every item (Priority: P1)

As the owner of an evaluated application, I need evaluation never to slow down or change a customer response.

**Acceptance Scenarios**:

1. **Given** a list being evaluated, **Then** the evaluated application does not wait for the result.
2. **Given** an evaluation that fails, **Then** the application's output is unaffected.
3. **Given** a `fail` verdict, **Then** the response is not blocked, changed, or withheld by this service.
4. **Given** a list of items, **Then** every item is either evaluated or reported as not evaluable. None is silently skipped.

### User Story 4 - Keep going when something breaks (Priority: P2)

As an operator, one bad item does not cost me the results of the others.

**Acceptance Scenarios**:

1. **Given** a list in which one item cannot be evaluated, **Then** the other items are evaluated and written, and the failing item gets a record marked not evaluable with a reason code.
2. **Given** an item evaluated twice, **Then** the store does not end up with two conflicting current results for the same item ID.

### Edge Cases

- The store is unavailable when a record is written.
- An item with an ID that was evaluated before arrives again.
- An item is not evaluable: it has a record, but no verdict.
- The judge is slow: this must not hold up the evaluation of other items.
- The list is empty: nothing is written, and this is not an error.

## Requirements

### Functional Requirements

- **FR-001**: For each item, the system MUST run text preparation, groundedness detection, deterministic checks, and span explanations, in that order.
- **FR-002**: The system MUST write exactly one result record per item, keyed by item ID.
- **FR-003**: The record MUST contain: `id`, `model` (name, revision, and device), `groundedness` (`verdict`, `score`, `max_span_confidence`, `unsupported_spans` each with `start`, `end`, `text`, `confidence`, `reason_type`, `reason`, `nearest_chunk_id`), `deterministic_checks`, `escalated`, and `windows_run`.
- **FR-004**: The record MUST include every computed signal, including the threshold in force, the time of evaluation, and any metadata that came with the item.
- **FR-005**: When the verdict is `fail`, the system MUST call the large judge with the flagged claims and the full evidence.
- **FR-006**: The system MUST also send a random sample of items to the judge at a rate set in config, and record that the item was sampled.
- **FR-007**: The judge MUST be reached through a replaceable contract (`LargeJudge`). This feature provides a stand-in; the real judge exists elsewhere.
- **FR-008**: The judge's response, or the fact that the call failed, MUST be stored in the record.
- **FR-009**: Evaluation MUST run in the background, off the request path, and MUST cover 100% of items received.
- **FR-010**: The system MUST NOT alter, block, or prune anything in the evaluated application.
- **FR-011**: A failure in one item MUST NOT stop the evaluation of others.
- **FR-012**: Records contain customer text in spans and reasons. They MUST be written only to the service's own store. Application logs MUST carry only identifiers, counts, scores, and reason codes.
- **FR-013**: The sample rate MUST come from config.
- **FR-014**: After a list is processed, the system MUST report how many items were evaluated, how many passed, how many failed, and how many were not evaluable.
- **FR-017**: Deterministic checks (feature 004, postponed) and span explanations (feature 005, not yet built) are optional stages. When a stage is not available, the run MUST skip it, leave its part of the record empty, and name it in the record's `stages_skipped` list, so "not run" is never mistaken for "nothing found".
- **FR-018**: Adding a skipped stage later MUST NOT require any change to the rest of the run.
- **FR-015**: At the start of a run the system MUST select the model from the hardware, as defined in feature 003: the large model on a GPU and the base model on CPU. One model is used for the whole run, and the run report names the model and device.
- **FR-016**: The threshold in force for a run MUST be the selected model's own threshold when it has one.

### Key Entities

- **Result record**: the stored outcome for one item, as listed in FR-003 and FR-004.
- **Escalation**: a call to the large judge, with its cause (`fail` verdict or random sample) and its outcome.

## Success Criteria

- **SC-001**: For a list of items, the number of records written equals the number of items with a valid ID, counting not-evaluable items.
- **SC-002**: 100% of `fail` items show an escalation attempt.
- **SC-003**: Over a large list, the share of sampled items is close to the configured rate.
- **SC-004**: No raw customer text appears in application logs during a test run.
- **SC-005**: The run is tested end to end with a stand-in detector and a stand-in judge, with no model present.

## Out of Scope

- The real large judge.
- Routing decisions based on confidence, and any learned routing policy.
- Dashboards and alerting.
- The unnecessary-evidence section of the record (`evidence_use`), deferred with that evaluator.

## Open Questions

1. How does the list reach the service: a file, a queue, a scheduled batch, or a request to an endpoint?
2. What is the service's own store: a database, files, or an existing platform store?
3. What random sample rate goes to the judge? 2% is assumed.
4. When an item ID is evaluated again, is the old record replaced or kept as history? Assumed: kept, with the newest marked current.
5. What does the existing judge accept and return? The stand-in assumes a verdict and a free-text rationale.
6. Is there a limit on how long after a list arrives its evaluation must finish?
7. Should a failed deterministic check also trigger escalation? Assumed no.
8. Does the caller need the results returned to it, or only written to the store?
