# Feature Specification: Input Ingestion

**Feature**: `001-input-ingestion`
**Created**: 2026-10-10
**Status**: Draft

## Summary

Read the service's input and turn it into items the evaluator can check. For now the input is assumed to be a list of JSON objects. Each object has a unique identifier, a question, the evidence, and an answer.

Reading the input is done through a replaceable parser, so another input format can be added later without changing the rest of the service.

## Assumed Input

```json
[
  {
    "id": "a1b2c3",
    "question": "What is the daily cash withdrawal limit?",
    "evidence": ["Passage one ...", "Passage two ..."],
    "answer": "The daily limit is £500."
  }
]
```

The key names `id`, `question`, `evidence`, and `answer` are assumed. See the open questions.

## User Scenarios & Testing

### User Story 1 - Read a list of items (Priority: P1)

As the evaluation service, I receive a list of JSON objects and get back one item per object, so each answer can be checked against its own evidence.

**Why this priority**: nothing else can run without items.

**Acceptance Scenarios**:

1. **Given** a list with one valid object, **When** it is read, **Then** one item is returned with its ID, question, evidence, and answer.
2. **Given** a list with many valid objects, **When** it is read, **Then** one item is returned per object, in the same order.
3. **Given** an object whose evidence is a list of passages, **Then** each passage is a separate evidence item, in the same order.
4. **Given** an object whose evidence is a single piece of text, **Then** it becomes one evidence item.
5. **Given** any item, **Then** its answer and evidence text are character-for-character equal to the input.

### User Story 2 - Survive bad input (Priority: P2)

As an operator, I want a bad object to be reported and skipped, not to stop the run.

**Acceptance Scenarios**:

1. **Given** an object with an empty answer or empty evidence, **When** it is read, **Then** the item is returned marked as not evaluable, with a reason code.
2. **Given** an object with a missing or empty ID, **When** it is read, **Then** it is reported by its position in the list and is not evaluated.
3. **Given** two objects with the same ID, **When** the list is read, **Then** the duplicate is reported and only the first is evaluated.
4. **Given** a list in which one object is malformed, **Then** the other objects are still returned.
5. **Given** input that is not a list of objects, **Then** a failure is reported with a reason code.
6. **Given** any reported problem, **Then** the message contains IDs, positions, and reason codes only, and no raw customer text.

### User Story 3 - Plug in another input format (Priority: P3)

As a developer, I can add a parser for another input format without changing any code that consumes items.

**Acceptance Scenarios**:

1. **Given** two parsers for two formats that describe the same items, **When** each reads its input, **Then** both return equal items.
2. **Given** the service configuration, **When** the parser is changed in config, **Then** the rest of the pipeline works unchanged.

### Edge Cases

- The list is empty: no items are returned, and this is not an error.
- An object has extra keys beyond the four: they are kept with the item as metadata and do not cause a failure.
- The question is empty: the item is still evaluated, with an empty question.
- A field has the wrong type, such as a number for the answer.
- The same passage appears twice in an object's evidence: both are kept.

## Requirements

### Functional Requirements

- **FR-001**: The system MUST accept a list of JSON objects, each with a unique identifier, a question, evidence, and an answer.
- **FR-002**: The system MUST return one item per valid object, with: item ID, question, evidence items, and answer.
- **FR-003**: Evidence MUST be accepted either as a single piece of text or as a list of passages.
- **FR-004**: Evidence and answer text MUST be kept exactly as received, with no trimming or reformatting, so character offsets computed later remain valid.
- **FR-005**: The item ID MUST be unique within a list. Duplicates MUST be reported.
- **FR-006**: Missing fields, wrong types, empty answers, empty evidence, and duplicate IDs MUST be reported with a reason code and MUST NOT stop the reading of other objects.
- **FR-007**: Extra keys on an object MUST be kept as metadata and MUST NOT cause a failure.
- **FR-008**: Input reading MUST be done through a parser contract (`InputParser`) so formats can be added without changing consumers.
- **FR-009**: Error and log messages MUST NOT contain raw customer text.

### Key Entities

- **Item**: one thing to evaluate: item ID, question, evidence items, answer, metadata, and whether it is evaluable.
- **Evidence item**: one passage of evidence, with its position in the object's evidence.

## Success Criteria

- **SC-001**: Every object in the fixture set is read into the expected item.
- **SC-002**: The answer and evidence text in each item are character-for-character equal to the input.
- **SC-003**: A list that includes bad objects is read to the end, and every bad object is reported.

## Out of Scope

- Splitting evidence into chunks and splitting the answer into sentences (feature 002).
- How the list reaches the service, such as a file, a queue, or a request (feature 006).
- Parsers for other input formats.

## Open Questions

1. What are the exact key names? `id`, `question`, `evidence`, and `answer` are assumed.
2. Is evidence a single piece of text, a list of passages, or a list of objects with their own fields such as a source or a heading? Text or a list of text passages is assumed.
3. Can a question be empty? Assumed yes.
4. Is the ID unique only within one list, or across all lists the service ever receives? Within one list is assumed.
5. Will objects carry anything else useful, such as a category or the name of the application that produced them? Extra keys are kept as metadata until this is known.
