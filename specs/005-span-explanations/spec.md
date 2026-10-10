# Feature Specification: Span Explanations

**Feature**: `005-span-explanations`
**Created**: 2026-10-10
**Status**: Draft

## Summary

Give every flagged span a short reason a reviewer can act on: what kind of problem it is, and the closest piece of evidence. Reasons are produced by fixed rules and templates, with no language model. A replaceable reason generator is left in place so a model-written reason can be added later for flagged cases.

## User Scenarios & Testing

### User Story 1 - See the closest evidence for a flagged span (Priority: P1)

As a reviewer, I see the evidence sentence most related to a flagged span and which chunk it came from, so I can judge the flag quickly.

**Why this priority**: a flag with no pointer into 32,000 tokens of evidence cannot be reviewed in reasonable time.

**Acceptance Scenarios**:

1. **Given** a flagged span and evidence containing a sentence that shares most of its words, **When** it is explained, **Then** that sentence is returned as the closest evidence, with its `chunk_id`.
2. **Given** a flagged span that shares no meaningful words with any evidence sentence, **Then** no closest evidence is returned and the reason type is `no_related_evidence`.

### User Story 2 - See what kind of problem it is (Priority: P1)

As a reviewer, I see a problem type for each flagged span.

**Acceptance Scenarios**:

1. **Given** a span stating "£150" whose closest evidence states "£75", **Then** the reason type is `number_mismatch`.
2. **Given** a span stating "3 March 2025" whose closest evidence states "13 March 2025", **Then** the reason type is `date_mismatch`.
3. **Given** a span naming a product or organisation that appears nowhere in the evidence, **Then** the reason type is `entity_not_in_evidence`.
4. **Given** a span to which more than one type applies, **Then** one type is chosen by a fixed order of precedence, and the result is the same on every run.

### User Story 3 - Read a plain reason (Priority: P2)

As a reviewer, I read a one-line reason built from a template.

**Acceptance Scenarios**:

1. **Given** a `number_mismatch`, **Then** the reason reads in the form: `Amount "£150" not supported. Closest evidence: "... up to £75 ..." (c12).`
2. **Given** any reason, **Then** the quoted evidence is shortened to a configured length.
3. **Given** the same span and evidence twice, **Then** the reason text is identical.

### User Story 4 - Replace the reason writer later (Priority: P3)

As a developer, I can swap in a different reason generator without changing the rest of the service.

**Acceptance Scenarios**:

1. **Given** a different reason generator configured, **Then** its reasons appear in the result and nothing else changes.

### Edge Cases

- Several evidence sentences are equally close: the first in evidence order is chosen.
- A span covers more than one sentence of the answer.
- A span contains both a number and a date that differ from the evidence.
- The closest evidence is related, but no number, date, or entity difference is found.

## Requirements

### Functional Requirements

- **FR-001**: For every flagged span, the system MUST find the closest evidence sentence by word overlap and return its text and `chunk_id` as `nearest_chunk_id`.
- **FR-002**: Every flagged span MUST be given exactly one `reason_type` from: `number_mismatch`, `date_mismatch`, `entity_not_in_evidence`, `no_related_evidence`.
- **FR-003**: When no evidence sentence reaches a configured minimum overlap, the type MUST be `no_related_evidence`.
- **FR-004**: When more than one type applies, the order of precedence MUST be: `number_mismatch`, then `date_mismatch`, then `entity_not_in_evidence`.
- **FR-005**: Every flagged span MUST be given a `reason` built from a template for its type.
- **FR-006**: Explanations MUST use no language model and MUST be the same for the same input on every run.
- **FR-007**: Reason generation MUST be reached through a replaceable contract (`ReasonGenerator`).
- **FR-008**: Reasons contain quoted customer and policy text. They MUST be written only to the service's own store and MUST NOT appear in application logs.
- **FR-009**: The minimum overlap and the maximum quoted length MUST come from config.

### Key Entities

- **Span explanation**: `reason_type`, `reason`, `nearest_chunk_id`, and the closest evidence sentence.

## Success Criteria

- **SC-001**: 100% of flagged spans carry a `reason_type` and a `reason`.
- **SC-002**: On a labelled set of flagged spans, the assigned `reason_type` matches a human label in a share of cases to be agreed. This target is an open question.
- **SC-003**: The feature is tested with no model present.

## Out of Scope

- Reasons written by a language model.
- Typed hallucination labels learned by the detector (contradiction, unsupported, number, date, entity).
- Explanations for deterministic check failures. Those already name the check and the value.

## Open Questions

1. What type is given when related evidence exists but no number, date, or entity difference is found? The four listed types do not cover this. Options: add a fifth type such as `unsupported_claim`, or fall back to `no_related_evidence`. A fifth type is recommended.
2. How are entities recognised without adding a new model? Assumed: the names and capitalised terms the sentence splitter already identifies.
3. Should the reason wording be general, such as "Amount", or name the kind of claim, such as "Refund amount"? General wording is assumed, since the service is generic and knowing the claim kind needs rules for each use case.
4. What accuracy is expected of `reason_type`?
