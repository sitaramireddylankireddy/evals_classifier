# Implementation Plan: Input Ingestion

**Feature**: `001-input-ingestion` | **Date**: 2026-10-10 | **Spec**: [spec.md](spec.md)

## Summary

Read a list of JSON objects and return validated items plus a list of issues. Reading goes through the `InputParser` protocol, with one implementation, `JsonListParser`. This feature also sets up the package, the config loader, the shared types, and the safe logging helper that every later feature uses.

## Technical Context

This section is the shared stack for all seven features. Later plans refer back to it.

- **Language**: Python 3.14. `pyproject.toml` sets `requires-python = ">=3.14"`, and the code may use 3.14 language features. Verify the installed version before starting.
- **Package**: `evalsvc`, defined in `pyproject.toml`, installed in editable mode.
- **Dependencies for this feature**: `pydantic` version 2 for typed, validated data. Test dependency: `pytest`.
- **Config**: one TOML file read with the standard library and validated by a pydantic `Settings` model. Each feature adds its own section.
- **Dependencies added by later features**: `spacy` (002), `torch` and `transformers` (003), `lettucedetect` as a test-only dependency (003). No other third-party packages are planned. Lexical ranking and metrics are written in-house to keep the dependency list short for the bank environment.
- **Testing**: `pytest`, with a `slow` marker for tests that need model weights. The default run excludes `slow`.

## Constitution Check

| Principle | How this plan meets it |
|---|---|
| I. Offline, safe model loading | No model and no network use in this feature. |
| II. Customer data stays in the store | All logging goes through `log_event`, which accepts only identifiers, positions, counts, scores, and reason codes. Issues carry a position and a reason code, never field values. Fixtures are synthetic. |
| III. Observes only | Reads input and changes nothing outside the service. |
| IV. Interfaces | Input is read through the `InputParser` protocol. The parser is chosen by config. |
| V. Configuration over constants | Parser choice and the four key names come from config. No application-specific names in code. |
| VI. Tested without the model, exact offsets | All tests are unit tests. A test asserts that answer and evidence text are unchanged character for character. |
| VII. Log every signal | Extra keys are kept as item metadata. Every skipped object produces an issue. |

## Project Structure

```
pyproject.toml
config.example.toml
evalsvc/
  __init__.py
  types.py            # Item, EvidenceItem, ReasonCode, IngestIssue, IngestResult
  config.py           # Settings, InputSettings, load_settings
  interfaces.py       # InputParser protocol
  safelog.py          # log_event
  ingest/
    __init__.py
    json_list.py      # JsonListParser, load_json_file, build_parser
tests/
  conftest.py
  fixtures/items_valid.json, items_bad.json, items.jsonl
  unit/test_json_list_parser.py
  unit/test_config.py
  unit/test_safelog.py
```

## Design

### Data structures (`evalsvc/types.py`)

All are frozen pydantic models.

```python
class ReasonCode(str, Enum):
    NOT_A_LIST, NOT_AN_OBJECT, MISSING_ID, DUPLICATE_ID,
    MISSING_FIELD, WRONG_TYPE, EMPTY_ANSWER, EMPTY_EVIDENCE

class EvidenceItem:
    index: int            # position in the object's evidence
    text: str             # exactly as received

class Item:
    id: str
    question: str         # may be empty
    evidence: list[EvidenceItem]
    answer: str           # exactly as received
    metadata: dict[str, Any]          # extra keys from the object
    evaluable: bool
    not_evaluable_reason: ReasonCode | None

class IngestIssue:
    position: int         # index of the object in the list
    item_id: str | None
    reason: ReasonCode
    field: str | None     # key name only, never the value

class IngestResult:
    items: list[Item]
    issues: list[IngestIssue]
```

### Functions

```python
# evalsvc/interfaces.py
class InputParser(Protocol):
    def parse(self, raw: Any) -> IngestResult: ...

# evalsvc/ingest/json_list.py
class JsonListParser:
    def __init__(self, keys: InputSettings) -> None: ...
    def parse(self, raw: Any) -> IngestResult: ...

def load_json_file(path: Path) -> Any: ...          # .json array or .jsonl, one object per line
def build_parser(settings: Settings) -> InputParser: ...

# evalsvc/config.py
def load_settings(path: Path) -> Settings: ...

# evalsvc/safelog.py
def log_event(event: str, **fields: str | int | float | bool | None) -> None: ...
```

### Behaviour rules

- `raw` is already-decoded JSON. If it is not a list, return no items and one `NOT_A_LIST` issue.
- Per object, in this order: not an object → `NOT_AN_OBJECT`; ID missing or empty → `MISSING_ID`; ID already seen → `DUPLICATE_ID` (first one wins); question, evidence, or answer key absent → `MISSING_FIELD`; wrong type → `WRONG_TYPE`. All of these skip the object.
- Types accepted: ID is a string or an integer (stored as a string); question and answer are strings; evidence is a string or a list of strings. Nothing is coerced or trimmed.
- An empty or whitespace-only answer gives an item with `evaluable=False` and `EMPTY_ANSWER`. Evidence that is empty, or has only blank passages, gives `EMPTY_EVIDENCE`. These items are kept so they still get a result record.
- An empty question is valid.
- Keys other than the four go into `metadata`.
- `log_event` rejects any field name outside a fixed allow-list (`item_id`, `position`, `reason`, `count`, `field`, and similar), so free text cannot be logged by mistake.

## Config Keys

```toml
[input]
parser = "json_list"
key_id = "id"
key_question = "question"
key_evidence = "evidence"
key_answer = "answer"
```

## Test Approach

- One valid object, many valid objects in order, evidence as text and as a list.
- Each reason code, each with a fixture that triggers only that code.
- A bad object in the middle of a list does not affect its neighbours.
- Text preservation: answers and evidence with leading spaces, tabs, line breaks, and non-ASCII characters come back unchanged.
- Extra keys land in `metadata`.
- Privacy: every fixture value contains a sentinel word; a test captures all log output during parsing and asserts the sentinel never appears.
- Changing the key names in config reads a list that uses those names.

## Risks and Items to Verify

- Python 3.14 must be the version on the development machine and on the target machine.
- Whether `spacy`, `torch`, and `transformers` have releases that install on Python 3.14 from the internal package mirror. Feature 002 task T001 and feature 003 task T011 are where this shows up. If one of them has no 3.14 build, the choice is to wait for one or to lower the Python version.
- Whether `pydantic` version 2 is available from the internal package mirror.

## Assumptions Carried From the Spec

Key names are `id`, `question`, `evidence`, `answer`. Evidence is text or a list of text. IDs are unique within one list. These are all config or parser details, so changing them later does not affect other features.
