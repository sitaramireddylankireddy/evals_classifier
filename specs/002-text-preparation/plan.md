# Implementation Plan: Text Preparation

**Feature**: `002-text-preparation` | **Date**: 2026-10-10 | **Spec**: [spec.md](spec.md)

## Summary

Three pure functions: chunk the evidence, split the answer into sentences with offsets, and mark non-factual sentences. All work on character ranges of the untouched original text, so every later finding can be mapped back exactly.

## Technical Context

Shared stack: see [001 plan](../001-input-ingestion/plan.md), Technical Context.

- **New dependency**: `spacy`, used only for its rule-based sentence splitter on a blank English pipeline. This needs no downloaded language model, which suits the offline environment. A config key allows an installed pipeline to be used instead.
- **Token counting**: through a `TokenCounter` protocol. Tests use a whitespace counter. Feature 003 supplies a counter backed by the detector's own tokenizer, which satisfies FR-002.

## Constitution Check

| Principle | How this plan meets it |
|---|---|
| I. Offline, safe model loading | The blank spaCy pipeline loads nothing from the network. An installed pipeline, if configured, is loaded by name from the local environment only. |
| II. Customer data stays in the store | No text is logged. Functions return data and raise no errors that include text. |
| III. Observes only | Pure functions with no side effects. |
| IV. Interfaces | Token counting sits behind `TokenCounter`, so this feature does not depend on the model. |
| V. Configuration over constants | Chunk sizes, heading patterns, the pipeline name, and the non-factual rules come from config. The default rules are generic courtesy phrases, not tied to an application. |
| VI. Tested without the model, exact offsets | All tests use the whitespace counter. Offset round-trip is asserted for every chunk and sentence. |
| VII. Log every signal | Non-factual sentences are kept, with the name of the rule that matched. |

## Project Structure

```
evalsvc/
  types.py              # add Chunk, Sentence
  config.py             # add ChunkingSettings, SentenceSettings, and ChecksSettings with
                        # currencies and reference_patterns only (feature 004 adds the rest)
  interfaces.py         # add TokenCounter protocol
  text/
    __init__.py
    tokens.py           # WhitespaceTokenCounter
    nlp.py              # build_nlp
    patterns.py         # find_amounts, find_dates, find_percentages, find_references
    chunking.py         # chunk_evidence
    sentences.py        # split_answer
tests/unit/
  test_chunking.py
  test_sentences.py
  test_patterns.py
```

## Design

### Data structures

```python
class Chunk:
    chunk_id: str         # "c1", "c2", ... numbered across the whole item, in order
    evidence_index: int
    start: int            # character range in the evidence item
    end: int
    text: str             # evidence_item.text[start:end]
    heading: str | None   # heading of the section the chunk belongs to
    token_count: int
    @property
    def context_text(self) -> str: ...   # heading + newline + text, unless text already starts with the heading

class Sentence:
    index: int
    start: int            # character range in the answer
    end: int
    text: str             # answer[start:end]
    factual: bool
    matched_rule: str | None

class Match:              # returned by the pattern finders
    start: int
    end: int
    text: str
    kind: str             # "amount", "date", "percentage", "reference"
```

### Functions

```python
# evalsvc/interfaces.py
class TokenCounter(Protocol):
    def count(self, text: str) -> int: ...

# evalsvc/text/nlp.py
def build_nlp(settings: SentenceSettings) -> spacy.Language: ...

# evalsvc/text/chunking.py
def chunk_evidence(evidence: list[EvidenceItem], counter: TokenCounter,
                   nlp: spacy.Language, settings: ChunkingSettings) -> list[Chunk]: ...

# evalsvc/text/sentences.py
def split_answer(answer: str, nlp: spacy.Language,
                 settings: SentenceSettings, checks: ChecksSettings) -> list[Sentence]: ...

# evalsvc/text/patterns.py
def find_amounts(text: str, currencies: list[str]) -> list[Match]: ...
def find_dates(text: str) -> list[Match]: ...
def find_percentages(text: str) -> list[Match]: ...
def find_references(text: str, patterns: list[str]) -> list[Match]: ...
```

### Chunking rules

1. Split each evidence item into sentence units with character ranges. Units are contiguous: each starts where the previous one ended, so whitespace between sentences belongs to a unit and no character is lost.
2. Pack units greedily into a chunk. Close the chunk when adding the next unit would exceed `max_tokens`.
3. A unit that is itself longer than `max_tokens` is split at whitespace into pieces within the limit.
4. A final chunk shorter than `min_tokens` is merged into the previous chunk if the result stays within `max_tokens`. Otherwise it stays as a short remainder.
5. An evidence item shorter than `min_tokens` is one chunk.
6. A line matching a heading pattern starts a new section and prefers to start a new chunk. Every chunk in the section carries that heading in `heading`.
7. `chunk_id` is assigned by counting chunks across the item in order. The same input always gives the same IDs.

Consequence: joining the `text` of an evidence item's chunks in order reproduces the item exactly (SC-003).

### Sentence rules

1. Split the answer into segments at line breaks that begin a list item (bullet or number marker). Each list item is its own segment.
2. Run the sentence splitter inside each segment and add the segment's start offset.
3. Shrink each range to remove leading and trailing whitespace. Drop ranges that become empty.
4. Mark a sentence non-factual when a rule pattern matches, unless any pattern finder returns a match inside it, in which case it stays factual.

`patterns.py` in this feature only needs to find values and their offsets. Feature 004 adds normalisation on top of the same finders.

## Config Keys

```toml
[chunking]
min_tokens = 300
max_tokens = 500
heading_patterns = ['^#{1,6}\s+\S', '^\d+(\.\d+)*\s+[A-Z]', '^[A-Z][A-Z \-]{3,60}$']

[sentences]
spacy_pipeline = "blank_en"

[[sentences.non_factual_rules]]
name = "apology"
pattern = '(?i)\b(we are|we\'re|i am|i\'m) (very |truly )?sorry\b|\bapologi[sz]e\b'

[[sentences.non_factual_rules]]
name = "empathy"
pattern = '(?i)\b(we|i) (understand|appreciate) (how|that)\b'

[[sentences.non_factual_rules]]
name = "next_step"
pattern = '(?i)\b(please (contact|let us know)|if you have any (further )?questions)\b'
```

## Test Approach

- **Chunking**: size bounds with the whitespace counter; identical output over 10 runs; chunk texts join back to the source; headings carried; short item is one chunk; oversize sentence is split and not dropped; no headings gives `heading=None`.
- **Sentences**: offset round-trip for every sentence; no overlap and in order; "£1,250.00" and "e.g." are not split; list items are separate; empty answer gives no sentences; tabs, line breaks, and repeated spaces keep offsets valid.
- **Non-factual**: a rule match marks the sentence; a rule match plus an amount stays factual; changing the rule list changes the result; flagged sentences stay in the output.

## Risks and Items to Verify

- That the blank pipeline's splitter keeps abbreviations and formatted amounts intact. The tests above settle this. If it does not, the fallback is a short list of protected patterns applied before splitting.
- The default heading patterns are guesses until real evidence is seen.

## Assumptions Carried From the Spec

Chunks do not overlap. The starter rule list stands in until the real patterns are supplied. Answers may be prose or lists; named-field answers are treated as lists, one line per field.
