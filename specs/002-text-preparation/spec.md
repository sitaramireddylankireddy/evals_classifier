# Feature Specification: Text Preparation

**Feature**: `002-text-preparation`
**Created**: 2026-10-10
**Status**: Draft

## Summary

Prepare the text of an item for checking. Evidence is cut into chunks with stable IDs. The answer is split into sentences that keep their position in the original answer. Sentences that state no facts (apologies, empathy, next steps) are marked so they are left out of scoring.

## User Scenarios & Testing

### User Story 1 - Chunk evidence with stable IDs (Priority: P1)

As the evaluator, I get the evidence as chunks of a bounded size, each with an ID that stays the same on every run, so results can point at a specific chunk.

**Why this priority**: evidence of up to about 32,000 tokens cannot be checked in one pass, and explanations must cite a chunk.

**Acceptance Scenarios**:

1. **Given** an evidence item longer than the maximum chunk size, **When** it is chunked, **Then** every chunk is within the configured size range (default 300 to 500 tokens), except a final remainder that may be shorter.
2. **Given** evidence with section headings, **When** it is chunked, **Then** each chunk carries the heading of the section it came from.
3. **Given** the same evidence chunked twice, **Then** the chunk IDs and chunk texts are identical both times.
4. **Given** any chunk, **Then** it records which evidence item it came from and its character range in that item, and that range reproduces the chunk's body text exactly.
5. **Given** an evidence item shorter than the minimum chunk size, **When** it is chunked, **Then** it becomes a single chunk.

### User Story 2 - Split the answer into sentences with offsets (Priority: P1)

As the evaluator, I get the answer as sentences, each with its start and end position in the original answer, so every finding can be shown on the exact original text.

**Acceptance Scenarios**:

1. **Given** an answer, **When** it is split, **Then** for every sentence, the original answer cut at the sentence's start and end equals the sentence text.
2. **Given** an answer, **When** it is split, **Then** sentences do not overlap and appear in order.
3. **Given** an answer containing amounts and abbreviations such as "£1,250.00" or "e.g.", **When** it is split, **Then** the sentence is not broken inside them.
4. **Given** an answer written as a list, **When** it is split, **Then** each list item is its own unit.

### User Story 3 - Mark non-factual sentences (Priority: P2)

As a reviewer, I do not want apologies or courtesy text counted as unsupported claims.

**Acceptance Scenarios**:

1. **Given** a sentence that matches a configured non-factual rule, **When** sentences are classified, **Then** it is marked non-factual.
2. **Given** a non-factual sentence, **Then** it is still present in the output with its offsets; it is excluded from scoring, not deleted.
3. **Given** a sentence that matches a non-factual rule but also contains an amount, a date, a percentage, or a policy reference, **Then** it is treated as factual.
4. **Given** a change to the rule list in config, **Then** the classification changes with no code change.

### Edge Cases

- A single sentence in evidence is longer than the maximum chunk size: it is split at the size limit, never dropped.
- Evidence with no headings: chunks have no heading.
- An empty or whitespace-only answer yields no sentences.
- The answer contains line breaks, tabs, or repeated spaces: offsets still refer to the untouched original.

## Requirements

### Functional Requirements

- **FR-001**: The system MUST split each evidence item into chunks within a configurable token range, default 300 to 500.
- **FR-002**: Token counts MUST be measured the same way the detector counts tokens, so window sizes computed later are accurate.
- **FR-003**: Chunks MUST break at sentence or paragraph boundaries where possible.
- **FR-004**: Every chunk MUST have a `chunk_id` that is the same for the same input on every run, and unique within an item.
- **FR-005**: Every chunk MUST carry its section heading where one exists, its source evidence item, its character range in that item, and its token count.
- **FR-006**: The system MUST split the answer into sentences with start and end character offsets into the original, unmodified answer.
- **FR-007**: The system MUST mark each sentence as factual or non-factual using a rule list from config.
- **FR-008**: Non-factual sentences MUST be kept in the output and flagged, never removed.
- **FR-009**: A sentence containing an amount, date, percentage, or policy reference MUST be treated as factual regardless of the rule list.
- **FR-010**: Chunk size range and the non-factual rule list MUST come from config.

### Key Entities

- **Evidence chunk**: `chunk_id`, text, heading, source evidence item, character range, token count.
- **Answer sentence**: text, start offset, end offset, factual or non-factual, and the rule that matched if non-factual.

## Success Criteria

- **SC-001**: For 100% of sentences in the test set, the offsets reproduce the sentence text exactly.
- **SC-002**: Chunking the same evidence 10 times gives identical IDs and texts every time.
- **SC-003**: No evidence text is lost: joining the chunk bodies of an evidence item in order reproduces the item's content.
- **SC-004**: All of this is tested without the detector model.

## Out of Scope

- Near-duplicate chunk detection (part of the deferred unnecessary-evidence evaluator).
- Selecting or ranking chunks by relevance.

## Open Questions

1. What are the non-factual sentence patterns for the first application? A starter list of apology, empathy, and next-step phrases is assumed until the real list is supplied.
2. Can an answer be structured, such as a bullet list or named fields, as well as prose? This decides how it is split into units.
3. Do evidence passages arrive with headings as separate fields, or must headings be recognised inside the text?
4. Should chunks overlap each other? Assumed no, since sliding windows already overlap.
