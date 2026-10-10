# Tasks: Input Ingestion

**Feature**: `001-input-ingestion` | **Inputs**: [spec.md](spec.md), [plan.md](plan.md)

Do the tasks in order. After each task, run its test file with `pytest <test file> -q`. A task is done when the tests named under "Done when" pass.

## Setup

- [x] **T001** Confirm the Python version
  - Files: none
  - Done when: `python --version` reports 3.14. If it reports anything else, install Python 3.14 and create the virtual environment with it before continuing.

- [x] **T002** Create the package skeleton
  - Files: `pyproject.toml`, `evalsvc/__init__.py`, `tests/__init__.py`, `.gitignore`
  - Content: package `evalsvc`; `requires-python = ">=3.14"`; dependency `pydantic>=2`; a `dev` extra with `pytest`; pytest settings that register a `slow` marker and exclude it by default.
  - Done when: `pip install -e ".[dev]"` succeeds and `python -c "import evalsvc"` prints nothing.

## Shared foundations

- [x] **T003** Define the shared types
  - Files: `evalsvc/types.py`, `tests/unit/test_types.py`
  - Content: `ReasonCode`, `EvidenceItem`, `Item`, `IngestIssue`, `IngestResult`, all frozen.
  - Done when: tests show each model can be built, cannot be changed after creation, and `ReasonCode` has the eight codes in the plan.

- [x] **T004** Add the config loader
  - Files: `evalsvc/config.py`, `config.example.toml`, `tests/unit/test_config.py`
  - Content: `InputSettings`, `Settings`, `load_settings`.
  - Done when: tests show defaults apply when `[input]` is absent, values in the file override defaults, and an unknown key or a missing file gives a clear error.

- [x] **T005** Add the safe logging helper
  - Files: `evalsvc/safelog.py`, `tests/unit/test_safelog.py`
  - Content: `log_event` with a fixed allow-list of field names.
  - Done when: tests show an allowed field is logged, and a field name outside the allow-list raises an error.

- [x] **T006** Define the parser protocol
  - Files: `evalsvc/interfaces.py`
  - Content: `InputParser` protocol, checkable at run time.
  - Done when: the test in T008 asserts that `JsonListParser` is an instance of `InputParser`.

- [x] **T007** Create synthetic fixtures
  - Files: `tests/conftest.py`, `tests/fixtures/items_valid.json`, `tests/fixtures/items_bad.json`, `tests/fixtures/items.jsonl`
  - Content: invented banking questions, evidence, and answers. Every text value contains the sentinel word `ZZSENTINEL`. A fixture in `conftest.py` exposes the sentinel.
  - Done when: the files load as valid JSON in T008.

## User Story 1: Read a list of items

- [x] **T008** Parse valid objects
  - Files: `evalsvc/ingest/__init__.py`, `evalsvc/ingest/json_list.py`, `tests/unit/test_json_list_parser.py`
  - Content: `JsonListParser.parse` for valid input only.
  - Done when: tests cover one object; many objects in the same order; evidence given as text; evidence given as a list; extra keys stored in `metadata`; an empty list returns no items and no issues.

- [x] **T009** Prove text is preserved
  - Files: `tests/unit/test_json_list_parser.py`
  - Done when: tests show answers and evidence with leading and trailing spaces, tabs, line breaks, and non-ASCII characters come back character for character equal.

## User Story 2: Survive bad input

- [x] **T010** Report and skip invalid objects
  - Files: `evalsvc/ingest/json_list.py`, `tests/unit/test_json_list_parser.py`
  - Content: `NOT_A_LIST`, `NOT_AN_OBJECT`, `MISSING_ID`, `DUPLICATE_ID`, `MISSING_FIELD`, `WRONG_TYPE`, checked in the order given in the plan.
  - Done when: one test per reason code passes; a bad object in the middle of a list leaves its neighbours unaffected; for a duplicate ID the first object is kept; each issue carries the right `position`.

- [x] **T011** Mark not-evaluable items
  - Files: `evalsvc/ingest/json_list.py`, `tests/unit/test_json_list_parser.py`
  - Content: `EMPTY_ANSWER` and `EMPTY_EVIDENCE` produce an item with `evaluable=False`.
  - Done when: tests cover an empty answer, a whitespace-only answer, empty evidence, evidence with only blank passages, and an empty question that stays evaluable.

- [x] **T012** Prove no customer text is logged
  - Files: `tests/unit/test_json_list_parser.py`
  - Done when: a test parses `items_bad.json` while capturing all log output and asserts the sentinel word never appears.

## User Story 3: Plug in another format

- [x] **T013** Add file loading and parser selection
  - Files: `evalsvc/ingest/json_list.py`, `tests/unit/test_json_list_parser.py`
  - Content: `load_json_file` for `.json` arrays and `.jsonl` files; `build_parser`.
  - Done when: tests show both file types give equal items; changing the key names in config reads a list that uses those names; an unknown parser name in config gives a clear error.

## Finish

- [x] **T014** Run the whole suite
  - Files: none
  - Done when: `pytest -q` passes with no failures.
