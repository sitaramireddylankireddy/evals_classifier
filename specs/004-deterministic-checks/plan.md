# Implementation Plan: Deterministic Checks

**Feature**: `004-deterministic-checks` | **Date**: 2026-10-10 | **Spec**: [spec.md](spec.md)

## Summary

Find amounts, dates, percentages, and references in the answer, normalise them, and test each one for presence in the evidence. Optionally check that required fields are present. Pure standard-library code with no model.

## Technical Context

Shared stack: see [001 plan](../001-input-ingestion/plan.md), Technical Context.

- **No new dependencies.** Values are found with regular expressions and normalised with `decimal` and `datetime` from the standard library. No date-parsing library is used, so results are the same on every machine.
- Builds on the pattern finders created in feature 002 (`evalsvc/text/patterns.py`).

## Constitution Check

| Principle | How this plan meets it |
|---|---|
| I. Offline, safe model loading | No model and no network use. |
| II. Customer data stays in the store | Check results hold the matched value, which is customer text, so they go only into the result record. Logs carry the check name, pass or fail, and the item ID. |
| III. Observes only | Pure functions. |
| IV. Interfaces | Nothing external is used. |
| V. Configuration over constants | Each check has an on/off switch. Currencies, date order, reference patterns, and required fields come from config. No application-specific field names in code. |
| VI. Tested without the model, exact offsets | All tests are unit tests. Offsets of every failure are asserted against the original answer. |
| VII. Log every signal | One result per value found, passing or failing, with the raw and normalised value. |

## Project Structure

```
evalsvc/
  types.py              # add CheckResult
  config.py             # add ChecksSettings
  text/patterns.py      # extend finders where needed
  checks/
    __init__.py
    normalise.py        # normalise_amount, normalise_date, normalise_percentage, normalise_reference
    deterministic.py    # run_checks and one function per check
tests/unit/
  test_normalise.py
  test_deterministic_checks.py
```

## Design

### Data structures

```python
class CheckResult:
    check: str               # one of the five stable names
    passed: bool
    start: int | None        # character range in the answer; None for a missing required field
    end: int | None
    value: str | None        # answer[start:end]
    normalised: str | None   # e.g. "GBP 150.00", "2025-03-03", "5", "section 4.2"
    field: str | None        # for required_field_present
    note: str | None         # e.g. "value_not_in_evidence", "date_without_year"
```

### Functions

```python
# evalsvc/checks/normalise.py
def normalise_amount(match: Match, default_currency: str) -> tuple[str, Decimal] | None: ...
def normalise_date(match: Match, day_first: bool) -> NormalisedDate | None: ...
def normalise_percentage(match: Match) -> Decimal | None: ...
def normalise_reference(match: Match) -> str: ...

# evalsvc/checks/deterministic.py
def run_checks(answer: str, evidence: list[EvidenceItem], settings: ChecksSettings) -> list[CheckResult]: ...
def check_amounts(answer, evidence_text, settings) -> list[CheckResult]: ...
def check_dates(answer, evidence_text, settings) -> list[CheckResult]: ...
def check_percentages(answer, evidence_text, settings) -> list[CheckResult]: ...
def check_references(answer, evidence_text, settings) -> list[CheckResult]: ...
def check_required_fields(answer, settings) -> list[CheckResult]: ...
```

### Rules

- **Evidence side**: the checks run against the full evidence text, not chunks, so a value split across a chunk boundary is still found. Evidence values are extracted and normalised once into sets.
- **Amounts**: recognise a currency symbol or code before or after the number, thousands separators, optional pence, and the words "pounds" and "pence" or "p". Normalise to a currency code and a decimal value with two places. "£150", "£150.00", "GBP 150", and "150 pounds" are equal.
- **Dates**: recognise numeric day-month-year with `/`, `-`, or `.`; year-month-day; and day with a month name in full or short, with optional ordinal suffix and optional year. Numeric dates are read day first unless config says otherwise. A date without a year matches any evidence date with the same day and month, and the result carries the note `date_without_year`.
- **Percentages**: "%", "per cent", and "percent" after a number. Normalise to a decimal, so "5%" equals "5.0 per cent".
- **References**: found with the configured patterns. Normalise to lower case with single spaces. A reference passes when the same normalised reference is found in the evidence.
- **Required fields**: if the answer parses as a JSON object, a field is present when the key exists with a non-empty value. Otherwise a field is present when a line starts with the field name followed by a colon. With an empty list, the check does not run.
- **Not checked**: durations, relative dates, and plain numbers that are not amounts, dates, or percentages.
- **Results**: one `CheckResult` per value found. A correctly derived amount that is not written in the evidence fails, with the note `value_not_in_evidence`. This is the known limitation in the spec.

## Config Keys

```toml
[checks]
amount = true
date = true
percentage = true
reference = true
currencies = ["GBP"]
day_first = true
reference_patterns = ['(?i)\b(section|clause|paragraph|article)\s+\d+(\.\d+)*[a-z]?\b']
required_fields = []
```

## Test Approach

- **Amount variants**: "£150" against "£150.00", "GBP 150", "150 pounds", "£1,250" against "£1250.00"; "£150" against "£75" fails with the right offsets.
- **Date variants**: "3 March 2025", "3rd Mar 2025", "03/03/2025", "2025-03-03" all equal; "03/04/2025" is 3 April with day first and 4 March without; a date with no year.
- **Percentages**: "5%", "5 per cent", "5.0 percent".
- **References**: present and absent, with different case and spacing.
- **Required fields**: JSON answer and labelled-line answer; empty list runs nothing.
- **Mixed**: three amounts with one missing gives exactly one failure.
- **Repeats**: the same value twice gives two results with different offsets.
- **Offsets**: for every result with offsets, `answer[start:end] == value`.
- **Switches**: turning a check off removes its results.
- **Determinism**: the same input gives identical results over repeated runs.

## Risks and Items to Verify

- The default reference pattern is a guess until real examples are supplied.
- False failures on amounts the answer derives from the evidence. The harness in feature 007 will show how common this is.
- An account number or reference code that looks like a date or an amount. The tests include these as negative cases.

## Assumptions Carried From the Spec

Pounds sterling only, day-first dates, durations and relative dates not checked, required fields off by default, and a failed check is reported beside the verdict without changing it.
