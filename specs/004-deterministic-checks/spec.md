# Feature Specification: Deterministic Checks

**Feature**: `004-deterministic-checks`
**Created**: 2026-10-10
**Status**: Draft

## Summary

Check the facts that a detection model is weakest at, using fixed rules and no model. Every amount, date, and percentage in an answer must appear in the evidence. Every policy or section reference the answer cites must exist in the evidence. Where a list of required fields is configured, the answer must contain them.

Each failure is reported with its position in the answer so it can be shown next to the detector's spans.

## User Scenarios & Testing

### User Story 1 - Amounts, dates, and percentages must come from the evidence (Priority: P1)

As a reviewer, I am told when an answer states a figure that appears nowhere in the evidence it was given.

**Why this priority**: in banking, a wrong amount or date is the most damaging error, and the detector is known to be weak on numbers.

**Acceptance Scenarios**:

1. **Given** an answer stating "£150" and evidence containing "£150.00", **When** it is checked, **Then** the amount check passes.
2. **Given** an answer stating "£150" and evidence containing only "£75", **When** it is checked, **Then** the amount check fails and reports the start and end of "£150" in the answer.
3. **Given** an answer stating "3 March 2025" and evidence containing "03/03/2025", **Then** the date check passes.
4. **Given** an answer stating "5%" and evidence containing "5 per cent", **Then** the percentage check passes.
5. **Given** an answer with three amounts of which one is missing from the evidence, **Then** exactly one failure is reported, for that amount.

### User Story 2 - Cited references must exist (Priority: P1)

As a reviewer, I am told when an answer cites a policy or section that was not in the evidence.

**Acceptance Scenarios**:

1. **Given** an answer citing "section 4.2" and evidence that contains section 4.2, **Then** the reference check passes.
2. **Given** an answer citing "section 9.1" and evidence with no such section, **Then** the reference check fails with the position of the citation.

### User Story 3 - Required fields are present (Priority: P2)

As an operator, I am told when an answer is missing a field that answers are required to contain.

**Acceptance Scenarios**:

1. **Given** a configured list of required fields, **When** one field is absent from the answer, **Then** one failure is reported naming that field.
2. **Given** no configured list, **Then** the required-field check is not run.
3. **Given** a change to a required-field list in config, **Then** the check changes with no code change.

### Edge Cases

- An amount in the answer is correctly derived from the evidence, such as the sum of two amounts: this check fails it, because the figure itself is not in the evidence. This is a known limitation and is reported as such.
- The same value appears twice in the answer: each occurrence is checked and reported separately.
- A date written with numbers only, such as 03/04/2025: read day first.
- A date without a year, such as "3 March".
- Durations and relative dates, such as "within 8 weeks" or "last Tuesday".
- Plain numbers that are not amounts, dates, or percentages, such as account numbers or counts.

## Requirements

### Functional Requirements

- **FR-001**: The system MUST find every amount, date, and percentage in the answer and check that the same value appears in the evidence after normalisation.
- **FR-002**: Amount normalisation MUST treat different writings of the same value as equal: currency symbol or code, thousands separators, and trailing zero pence.
- **FR-003**: Date normalisation MUST treat different writings of the same date as equal: day-month-year in numbers, month names in full or short, and year-month-day.
- **FR-004**: Percentage normalisation MUST treat "%", "per cent", and "percent" as equal.
- **FR-005**: The system MUST find every policy or section reference cited in the answer and check that it exists in the evidence.
- **FR-006**: When a required-field list is set in config, the system MUST check that every field in the list is present in the answer. With no list, the check is not run.
- **FR-007**: Every result MUST name the check, say whether it passed, and for a failure give the start and end offsets in the original answer. A missing required field has no offsets and names the field.
- **FR-008**: Checks MUST use no model and MUST give the same result for the same input every time.
- **FR-009**: The required-field lists, the reference patterns, the accepted currencies, and the date order MUST come from config.
- **FR-010**: Check names MUST be stable: `amount_in_evidence`, `date_in_evidence`, `percentage_in_evidence`, `reference_in_evidence`, `required_field_present`.
- **FR-011**: Each check MUST be switchable on or off in config, so an application uses only the checks that apply to it.

### Key Entities

- **Check result**: check name, passed or failed, start and end offsets, the value found, and the field name for required-field checks.

## Success Criteria

- **SC-001**: Every currency and date variant in the test set is matched correctly to its equal form.
- **SC-002**: For 100% of failures with offsets, the offsets reproduce the reported value from the original answer.
- **SC-003**: The checks run with no model present.

## Out of Scope

- Checking that a calculation is correct, such as a sum or an interest figure.
- Checking that a value is attached to the right thing, such as the right amount paired with the right date. Only presence in the evidence is checked.
- Names of people, products, and organisations. The detector and feature 005 handle those.

## Open Questions

1. Are required fields needed at all for the first application, and if so, what are they? The check is off by default.
2. How are policy and section references written? Examples are needed to define the default patterns.
3. Which currencies occur? Pounds sterling only is assumed as the default.
4. Are numeric dates always day first? Assumed yes as the default.
5. Should durations and relative dates be checked? Assumed no for version 1.
6. Does a failed deterministic check change the groundedness verdict or cause escalation? Assumed no: it is reported beside the verdict and does not change it.
7. How is a required field recognised in an answer: as a named field in structured output, or by a label in prose?
