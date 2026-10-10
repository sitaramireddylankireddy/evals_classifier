# Feature Specification: Golden-Set Harness

**Feature**: `007-golden-set-harness`
**Created**: 2026-10-10
**Status**: Draft

## Summary

A command that runs the groundedness evaluator over a set of items with known correct labels and reports how well it does. It is how the threshold is chosen, how the base and large models are compared, and how any later change is shown to be an improvement.

A golden-set item is the same as an input item (identifier, question, evidence, answer) with a label added. The first experiment is 200 to 300 labelled items, with the detector used as supplied and no fine-tuning.

## User Scenarios & Testing

### User Story 1 - Measure quality against known labels (Priority: P1)

As a developer, I run one command on the golden set and get recall, precision, and false-alarm rate.

**Why this priority**: without this number there is no basis for trusting the evaluator on live items.

**Acceptance Scenarios**:

1. **Given** a golden set and a model config, **When** the command runs, **Then** it reports recall on known failures, precision, false-alarm rate, and the area under the precision-recall curve.
2. **Given** the report, **Then** recall on known failures is shown first, as the priority measure.
3. **Given** the report, **Then** it states how many items were evaluated, how many were not evaluable, and how many labelled failures the set contains.
4. **Given** the same golden set and config run twice, **Then** the reported numbers are identical.

### User Story 2 - Break results down (Priority: P2)

As a developer, I see where the evaluator is weak.

**Acceptance Scenarios**:

1. **Given** golden-set items that carry a category, **Then** every measure is also shown per category.
2. **Given** a category with too few examples for a meaningful figure, **Then** the report shows the count and marks the figure as unreliable.
3. **Given** items with no category, **Then** only the overall measures are shown.

### User Story 3 - Choose the threshold from data (Priority: P1)

As a developer, I see how the measures change with the threshold, so I can pick one.

**Acceptance Scenarios**:

1. **Given** a threshold sweep is requested, **Then** the report shows recall, precision, and false-alarm rate at each threshold in a configured range.
2. **Given** a recall target, **Then** the report names the highest threshold that meets it and the precision at that threshold.
3. **Given** a sweep, **Then** the detector is run once per item, not once per threshold.

### User Story 4 - Compare two model configs (Priority: P2)

As a developer, I compare the base and the large model side by side on the same data.

**Acceptance Scenarios**:

1. **Given** two model configs, **When** the comparison runs, **Then** the report shows every measure for both, side by side, with the difference.
2. **Given** a comparison, **Then** the report lists the items on which the two configs disagree, by item ID.
3. **Given** a comparison, **Then** each config's processing time per item is reported.

### Edge Cases

- A golden-set item is malformed: it is reported with its position and skipped.
- The golden set has no labelled failures: recall cannot be computed, and the report says so.
- An item is not evaluable: it is counted separately and left out of the measures.
- An item has no label: it is left out and counted.

## Requirements

### Functional Requirements

- **FR-001**: The system MUST provide a command that takes a golden-set file and a model config and produces a report.
- **FR-002**: The golden set MUST use the input format read by feature 001, with a label added to each item and an optional category.
- **FR-003**: The report MUST include recall on known failures, precision, false-alarm rate, and area under the precision-recall curve.
- **FR-004**: The report MUST break every measure down per category where items carry one.
- **FR-005**: The command MUST support a threshold sweep over a configured range, reusing one detector run per item.
- **FR-006**: The command MUST support comparing two model configs on the same golden set. Because one config holds both the large and the base model, it MUST also be able to compare those two directly from a single config.
- **FR-012**: The command MUST allow the model to be forced for a run, so the base model can be measured on a GPU machine and the large model on a CPU machine.
- **FR-013**: The threshold sweep MUST be reported per model, since each model gets its own threshold in config.
- **FR-007**: The report MUST be written both as a readable summary and as a data file, so results can be kept and compared over time.
- **FR-008**: The report MUST record the golden-set file identity, the model name and revision, the threshold, and the date of the run.
- **FR-009**: The report MUST NOT contain raw customer text. Items are referred to by item ID.
- **FR-010**: The command MUST run offline.
- **FR-011**: The measures MUST be testable with a stand-in detector and a small synthetic golden set, with no model present.

### Key Entities

- **Golden-set item**: an input item with a label and an optional category.
- **Label**: whether the item's answer contains unsupported content, and optionally where.
- **Evaluation report**: the measures overall and per category, plus the sweep and the comparison where requested.

## Success Criteria

- **SC-001**: On a synthetic golden set with known outcomes, every reported measure equals the value worked out by hand.
- **SC-002**: A run over 300 items completes on the available hardware in a time that allows several runs per day. The exact limit depends on whether a GPU is available.
- **SC-003**: The first experiment produces a chosen threshold and a base-versus-large recommendation, backed by the report.

## Out of Scope

- Creating the labels. The golden set is supplied.
- Fine-tuning the detector on these labels.
- Measuring the accuracy of explanations (`reason_type`).
- The ablation harness for unnecessary evidence, deferred with that evaluator.

## Open Questions

1. Where do the first golden labels come from: large-judge verdicts, corrections made by human reviewers, or both?
2. At what level are labels given: one pass or fail per item, or the exact unsupported spans? Item-level labels are assumed, with spans optional. Span-level measures need span labels.
3. If labels come from human corrections, how is a correction turned into "this answer had unsupported content"? A correction can be a style change, not a factual fix.
4. What is the label key called and what values does it take? A key `label` with the values `grounded` and `ungrounded` is assumed.
5. Are categories wanted for grouping results, and if so, what are they?
6. What recall target on known failures must be met?
7. How is a false alarm counted: per item or per span? Per item is assumed.
