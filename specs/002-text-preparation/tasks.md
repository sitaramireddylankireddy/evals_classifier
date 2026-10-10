# Tasks: Text Preparation

**Feature**: `002-text-preparation` | **Inputs**: [spec.md](spec.md), [plan.md](plan.md)

**Depends on**: feature 001 complete.

Do the tasks in order. After each task, run its test file with `pytest <test file> -q`. A task is done when the tests named under "Done when" pass.

## Setup

- [ ] **T001** Add spaCy
  - Files: `pyproject.toml`
  - Done when: `pip install -e ".[dev]"` succeeds and `python -c "import spacy; spacy.blank('en')"` prints nothing. No language model is downloaded.

- [ ] **T002** Add the types
  - Files: `evalsvc/types.py`, `tests/unit/test_types.py`
  - Content: `Chunk` with the `context_text` property, `Sentence`, `Match`.
  - Done when: tests show `context_text` joins heading and text, returns text alone when there is no heading, and does not repeat a heading the text already starts with.

- [ ] **T003** Add the config sections
  - Files: `evalsvc/config.py`, `config.example.toml`, `tests/unit/test_config.py`
  - Content: `ChunkingSettings`, `SentenceSettings` with the non-factual rule list, and `ChecksSettings` with `currencies` and `reference_patterns` only.
  - Done when: tests show the defaults in the plan load, and a rule with an invalid pattern gives a clear error at load time.

- [ ] **T004** Add token counting
  - Files: `evalsvc/interfaces.py`, `evalsvc/text/__init__.py`, `evalsvc/text/tokens.py`, `tests/unit/test_tokens.py`
  - Content: `TokenCounter` protocol; `WhitespaceTokenCounter`.
  - Done when: tests show the counter counts whitespace-separated words and satisfies the protocol.

- [ ] **T005** Build the sentence pipeline
  - Files: `evalsvc/text/nlp.py`, `tests/unit/test_nlp.py`
  - Content: `build_nlp`, giving a blank English pipeline with the rule-based splitter, or an installed pipeline named in config.
  - Done when: tests show the default pipeline splits two plain sentences, and a pipeline name that is not installed gives a clear error.

- [ ] **T006** Add the pattern finders
  - Files: `evalsvc/text/patterns.py`, `tests/unit/test_patterns.py`
  - Content: `find_amounts`, `find_dates`, `find_percentages`, `find_references`, each returning matches with offsets.
  - Done when: tests show each finder returns the right offsets for a simple example, and none of them matches plain prose or an account number.

## User Story 1: Chunk evidence with stable IDs

- [ ] **T007** Pack evidence into chunks
  - Files: `evalsvc/text/chunking.py`, `tests/unit/test_chunking.py`
  - Content: contiguous sentence units, then greedy packing up to `max_tokens`.
  - Done when: tests show every chunk is within the size range apart from a final remainder; joining an evidence item's chunk texts reproduces the item exactly; a short item becomes one chunk; each chunk's range reproduces its text from the source.

- [ ] **T008** Handle the size edge cases
  - Files: `evalsvc/text/chunking.py`, `tests/unit/test_chunking.py`
  - Content: split a single unit longer than `max_tokens`; merge a short final chunk into the previous one when it fits.
  - Done when: tests show an oversize sentence is split and none of its text is lost; a short remainder is merged when the result fits and kept when it does not.

- [ ] **T009** Add headings and chunk IDs
  - Files: `evalsvc/text/chunking.py`, `tests/unit/test_chunking.py`
  - Content: heading detection from config patterns; `chunk_id` numbered across the item.
  - Done when: tests show chunks carry their section's heading; evidence with no headings gives `heading=None`; IDs and texts are identical across 10 runs; IDs are unique within an item with several evidence items.

## User Story 2: Split the answer into sentences

- [ ] **T010** Split with exact offsets
  - Files: `evalsvc/text/sentences.py`, `tests/unit/test_sentences.py`
  - Content: `split_answer` without the non-factual marking.
  - Done when: tests show `answer[start:end] == text` for every sentence; sentences are in order with no overlap; "£1,250.00" and "e.g." are not split; an empty or whitespace-only answer gives no sentences; tabs, line breaks, and repeated spaces keep offsets valid.

- [ ] **T011** Treat list items as separate units
  - Files: `evalsvc/text/sentences.py`, `tests/unit/test_sentences.py`
  - Done when: tests show a bulleted answer and a numbered answer each give one unit per list item, with correct offsets.

## User Story 3: Mark non-factual sentences

- [ ] **T012** Apply the rule list
  - Files: `evalsvc/text/sentences.py`, `tests/unit/test_sentences.py`
  - Content: mark `factual` and `matched_rule`; a sentence containing an amount, date, percentage, or reference stays factual.
  - Done when: tests show an apology is marked non-factual with the rule name; an apology containing "£50" stays factual; flagged sentences remain in the output with offsets; replacing the rule list in config changes the result.

## Finish

- [ ] **T013** Run the whole suite
  - Files: none
  - Done when: `pytest -q` passes with no failures and no test loads a model.
