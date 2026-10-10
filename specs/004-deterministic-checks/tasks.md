# Tasks: Deterministic Checks

**Feature**: `004-deterministic-checks` | **Inputs**: [spec.md](spec.md), [plan.md](plan.md)

**Depends on**: features 001 and 002 complete. Independent of feature 003.

Do the tasks in order. After each task, run its test file with `pytest <test file> -q`. A task is done when the tests named under "Done when" pass.

## Setup

- [ ] **T001** Add the type and the config
  - Files: `evalsvc/types.py`, `evalsvc/config.py`, `config.example.toml`, `tests/unit/test_config.py`
  - Content: `CheckResult`; the remaining `ChecksSettings` keys: the four on/off switches, `day_first`, `required_fields`.
  - Done when: tests show the defaults in the plan load, with all four value checks on and `required_fields` empty.

## Normalisation

- [ ] **T002** Normalise amounts
  - Files: `evalsvc/text/patterns.py`, `evalsvc/checks/__init__.py`, `evalsvc/checks/normalise.py`, `tests/unit/test_normalise.py`
  - Content: extend `find_amounts` for symbols, codes, thousands separators, pence, and the words "pounds" and "pence"; `normalise_amount`.
  - Done when: tests show "£150", "£150.00", "GBP 150", and "150 pounds" normalise to the same value; "£1,250" equals "£1250.00"; "50p" equals "£0.50"; "£150" differs from "£75".

- [ ] **T003** Normalise dates
  - Files: `evalsvc/text/patterns.py`, `evalsvc/checks/normalise.py`, `tests/unit/test_normalise.py`
  - Content: extend `find_dates` for numeric, year-first, and month-name forms; `normalise_date`.
  - Done when: tests show "3 March 2025", "3rd Mar 2025", "03/03/2025", and "2025-03-03" are equal; "03/04/2025" is 3 April with `day_first=true` and 4 March with `false`; "3 March" is recognised as a date without a year; an impossible date such as "31/02/2025" is not treated as a date.

- [ ] **T004** Normalise percentages and references
  - Files: `evalsvc/checks/normalise.py`, `tests/unit/test_normalise.py`
  - Content: `normalise_percentage`, `normalise_reference`.
  - Done when: tests show "5%", "5 per cent", and "5.0 percent" are equal; "Section 4.2" and "section  4.2" are equal; "section 4.2" differs from "section 4.20".

## User Story 1: Amounts, dates, and percentages

- [ ] **T005** Check amounts
  - Files: `evalsvc/checks/deterministic.py`, `tests/unit/test_deterministic_checks.py`
  - Content: `check_amounts`.
  - Done when: tests show "£150" passes against "£150.00"; "£150" fails against "£75" with offsets covering "£150"; three amounts with one missing give exactly one failure; the same amount twice gives two results with different offsets.

- [ ] **T006** Check dates
  - Files: `evalsvc/checks/deterministic.py`, `tests/unit/test_deterministic_checks.py`
  - Content: `check_dates`.
  - Done when: tests show a date passes against the same date written differently; a different date fails with offsets; a date without a year passes on day and month and carries the note `date_without_year`.

- [ ] **T007** Check percentages
  - Files: `evalsvc/checks/deterministic.py`, `tests/unit/test_deterministic_checks.py`
  - Content: `check_percentages`.
  - Done when: tests show "5%" passes against "5 per cent" and fails against "7%".

## User Story 2: Cited references

- [ ] **T008** Check references
  - Files: `evalsvc/checks/deterministic.py`, `tests/unit/test_deterministic_checks.py`
  - Content: `check_references`, using the configured patterns.
  - Done when: tests show a cited section present in the evidence passes; an absent one fails with the citation's offsets; a pattern added in config is picked up.

## User Story 3: Required fields

- [ ] **T009** Check required fields
  - Files: `evalsvc/checks/deterministic.py`, `tests/unit/test_deterministic_checks.py`
  - Content: `check_required_fields` for JSON-object answers and labelled-line answers.
  - Done when: tests show a missing field gives one failure naming the field with no offsets; a present but empty field fails; an empty list runs nothing.

## Assemble

- [ ] **T010** Run all checks together
  - Files: `evalsvc/checks/deterministic.py`, `tests/unit/test_deterministic_checks.py`
  - Content: `run_checks`, honouring the switches and running against the full evidence text.
  - Done when: tests show turning a check off removes its results; a value that sits across two evidence passages' boundary area is still found within its own passage; check names are exactly the five in the spec; repeated runs give identical results.

- [ ] **T011** Prove offsets and negative cases
  - Files: `tests/unit/test_deterministic_checks.py`
  - Done when: a test asserts `answer[start:end] == value` for every result with offsets across all fixtures; account numbers, sort codes, durations such as "8 weeks", and plain counts produce no results.

## Finish

- [ ] **T012** Run the whole suite
  - Files: none
  - Done when: `pytest -q` passes with no failures and no test loads a model.
