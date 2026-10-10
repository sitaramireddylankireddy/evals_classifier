# Tasks: Span Explanations

**Feature**: `005-span-explanations` | **Inputs**: [spec.md](spec.md), [plan.md](plan.md)

**Depends on**: features 001, 002, and 004 complete, plus the `Span` type from feature 003 (task T001 there).

Do the tasks in order. After each task, run its test file with `pytest <test file> -q`. A task is done when the tests named under "Done when" pass.

## Decision

- [ ] **T001** Decide on the fifth reason type
  - Files: `specs/005-span-explanations/spec.md`
  - Content: the plan adds `unsupported_claim` for a span that has related evidence but no number, date, or entity difference. Accept it or keep four types.
  - Done when: if accepted, FR-002 in the spec lists five types and open question 1 is removed. If not, `fallback_type` is set to `no_related_evidence` in `config.example.toml` during T002.

## Setup

- [ ] **T002** Add the types, config, and protocol
  - Files: `evalsvc/types.py`, `evalsvc/config.py`, `evalsvc/interfaces.py`, `config.example.toml`, `tests/unit/test_config.py`
  - Content: `ReasonType`, `SpanExplanation`, `ExplainSettings`, `ReasonGenerator` protocol.
  - Done when: tests show the defaults in the plan load, and an unknown `fallback_type` is rejected.

## User Story 1: Closest evidence

- [ ] **T003** Tokenize for ranking
  - Files: `evalsvc/explain/__init__.py`, `evalsvc/explain/nearest.py`, `tests/unit/test_nearest.py`
  - Content: `tokenize`, giving lower-case words with punctuation and stop words removed, and amounts kept whole.
  - Done when: tests show "The limit is £500." gives `["limit", "£500"]`, and empty text gives an empty list.

- [ ] **T004** Rank evidence sentences
  - Files: `evalsvc/explain/nearest.py`, `tests/unit/test_nearest.py`
  - Content: `EvidenceIndex` with BM25 ranking, the overlap ratio, and the `chunk_id` of each sentence.
  - Done when: tests show the sentence sharing most words is returned with its `chunk_id`; equal scores resolve to the earliest sentence; a query sharing no words returns nothing; `overlap` is the expected ratio for a hand-worked case; an index over no chunks returns nothing.

## User Story 2: Problem type

- [ ] **T005** Detect number mismatches
  - Files: `evalsvc/explain/reasons.py`, `tests/unit/test_reasons.py`
  - Content: the `number_mismatch` rule.
  - Done when: tests show a span with "£150" against a nearest sentence with "£75" is `number_mismatch`; a span with "£150" against a sentence with "£150.00" is not; a span with an amount against a sentence with no amounts is not.

- [ ] **T006** Detect date mismatches and apply precedence
  - Files: `evalsvc/explain/reasons.py`, `tests/unit/test_reasons.py`
  - Content: the `date_mismatch` rule and the order of precedence.
  - Done when: tests show "3 March 2025" against "13 March 2025" is `date_mismatch`, and a span differing in both a number and a date is `number_mismatch`.

- [ ] **T007** Detect names missing from the evidence
  - Files: `evalsvc/explain/reasons.py`, `tests/unit/test_reasons.py`
  - Content: name detection by capitalisation, or by the pipeline's entities when it has them; the `entity_not_in_evidence` rule.
  - Done when: tests show a product name absent from all evidence is `entity_not_in_evidence`; a name present in different case is not; a capitalised word at the start of a sentence is not treated as a name.

- [ ] **T008** Handle unrelated evidence and the fallback
  - Files: `evalsvc/explain/reasons.py`, `tests/unit/test_reasons.py`
  - Content: `no_related_evidence` below `min_overlap`; the configured fallback type otherwise.
  - Done when: tests show an overlap below the minimum gives `no_related_evidence` with no nearest sentence; related evidence with no difference gives the configured fallback; changing `fallback_type` in config changes the result.

## User Story 3: Reason text

- [ ] **T009** Fill the templates
  - Files: `evalsvc/explain/reasons.py`, `tests/unit/test_reasons.py`
  - Content: one template per type; quote shortening centred on the differing value.
  - Done when: tests compare the exact reason text for each type; a long evidence sentence is cut to `max_quote_chars` with "..." where text was removed, and the differing value is still inside the quote.

## User Story 4: Replaceable generator

- [ ] **T010** Assemble the generator
  - Files: `evalsvc/explain/reasons.py`, `tests/unit/test_reasons.py`
  - Content: `RuleBasedReasonGenerator.explain`, using the answer sentence around the span as the query; `build_reason_generator`.
  - Done when: tests show every span gets exactly one `reason_type` and a `reason`; a span covering two answer sentences is handled; the same input gives the same explanation on repeated runs; a stub generator selected in config is used in place of the rule-based one.

- [ ] **T011** Prove no customer text is logged
  - Files: `tests/unit/test_reasons.py`
  - Done when: a test explains spans built from sentinel fixtures while capturing all log output and asserts the sentinel word never appears.

## Finish

- [ ] **T012** Run the whole suite
  - Files: none
  - Done when: `pytest -q` passes with no failures and no test loads a model.
