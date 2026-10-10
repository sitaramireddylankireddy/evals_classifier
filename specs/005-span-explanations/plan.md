# Implementation Plan: Span Explanations

**Feature**: `005-span-explanations` | **Date**: 2026-10-10 | **Spec**: [spec.md](spec.md)

## Summary

For each flagged span, rank evidence sentences by lexical relevance, pick the closest, classify the problem with fixed rules, and fill a template. The work sits behind the `ReasonGenerator` protocol so a different generator can replace it later.

## Technical Context

Shared stack: see [001 plan](../001-input-ingestion/plan.md), Technical Context.

- **No new dependencies.** BM25 ranking is about forty lines and is written in-house, which avoids adding a package for the bank environment to approve.
- Reuses the sentence splitter from feature 002 and the finders and normalisers from features 002 and 004.

## Constitution Check

| Principle | How this plan meets it |
|---|---|
| I. Offline, safe model loading | No model and no language-model call. Entity detection uses simple rules unless an installed spaCy pipeline with entity recognition is already configured. |
| II. Customer data stays in the store | Reasons quote customer and evidence text. They are returned as data for the result record and are never passed to `log_event`. |
| III. Observes only | Pure functions. |
| IV. Interfaces | Callers use the `ReasonGenerator` protocol. The implementation is chosen by config. |
| V. Configuration over constants | Minimum overlap, quote length, and the fallback type come from config. Templates use general wording with no application-specific terms. |
| VI. Tested without the model, exact offsets | All tests are unit tests. No offsets are changed by this feature. |
| VII. Log every signal | The explanation keeps the nearest sentence, its chunk ID, the ranking score, and the overlap ratio. |

## Project Structure

```
evalsvc/
  types.py              # add ReasonType, SpanExplanation
  config.py             # add ExplainSettings
  interfaces.py         # add ReasonGenerator protocol
  explain/
    __init__.py
    nearest.py          # EvidenceIndex, tokenize
    reasons.py          # RuleBasedReasonGenerator, build_reason_generator
tests/unit/
  test_nearest.py
  test_reasons.py
```

## Design

### Data structures

```python
class ReasonType(str, Enum):
    NUMBER_MISMATCH = "number_mismatch"
    DATE_MISMATCH = "date_mismatch"
    ENTITY_NOT_IN_EVIDENCE = "entity_not_in_evidence"
    NO_RELATED_EVIDENCE = "no_related_evidence"
    UNSUPPORTED_CLAIM = "unsupported_claim"      # see the note below

class SpanExplanation:
    reason_type: ReasonType
    reason: str
    nearest_chunk_id: str | None
    nearest_sentence: str | None
    rank_score: float
    overlap: float            # share of the span's content words found in the nearest sentence
```

### Functions

```python
# evalsvc/interfaces.py
class ReasonGenerator(Protocol):
    def explain(self, span: Span, answer: str, sentences: list[Sentence],
                chunks: list[Chunk]) -> SpanExplanation: ...

# evalsvc/explain/nearest.py
def tokenize(text: str) -> list[str]: ...          # lower case, punctuation stripped, stop words removed
class EvidenceIndex:
    def __init__(self, chunks: list[Chunk], nlp: spacy.Language) -> None: ...
    def nearest(self, query: str) -> NearestHit | None: ...

# evalsvc/explain/reasons.py
class RuleBasedReasonGenerator:                    # implements ReasonGenerator
    def __init__(self, nlp: spacy.Language, settings: ExplainSettings, checks: ChecksSettings) -> None: ...
def build_reason_generator(settings: Settings, nlp: spacy.Language) -> ReasonGenerator: ...
```

### Rules

1. **Index**: split every chunk into sentences, each remembering its `chunk_id`. Build the index once per item and reuse it for all of that item's spans.
2. **Query**: the query is the full answer sentence or sentences that contain the span, not the span alone. A short span such as an amount has too few words to rank on.
3. **Ranking**: BM25 over the evidence sentences. Ties go to the earliest sentence in evidence order.
4. **Related or not**: compute `overlap`, the share of the query's content words that appear in the top sentence. Below `min_overlap`, the type is `no_related_evidence` and no nearest sentence is returned.
5. **Classification**, in this order of precedence:
   - `number_mismatch`: the span contains an amount, percentage, or number; the nearest sentence contains at least one value of the same kind; and none of the span's values is among them.
   - `date_mismatch`: the same test for dates.
   - `entity_not_in_evidence`: the span contains a name that appears nowhere in the evidence, ignoring case. A name is an entity from the configured spaCy pipeline when it has entity recognition; otherwise a capitalised word or run of words that does not start a sentence.
   - Otherwise the fallback type.
6. **Templates**, one per type, with general wording:
   - `number_mismatch`: `Value "{span_value}" not supported. Closest evidence: "{quote}" ({chunk_id}).`
   - `date_mismatch`: `Date "{span_value}" not supported. Closest evidence: "{quote}" ({chunk_id}).`
   - `entity_not_in_evidence`: `"{entity}" does not appear in the evidence. Closest evidence: "{quote}" ({chunk_id}).`
   - `no_related_evidence`: `No related evidence found for this statement.`
   - `unsupported_claim`: `Statement not supported by the evidence. Closest evidence: "{quote}" ({chunk_id}).`
7. **Quote**: shortened to `max_quote_chars`, centred on the differing value where there is one, with "..." where text was cut.
8. Excluded spans are explained in the same way.

### Note on the fifth reason type

The spec lists four types and raises, as open question 1, the case where related evidence exists but no number, date, or entity difference is found. This plan adds `unsupported_claim` for that case and makes it a config choice. If you prefer to keep four types, set `fallback_type = "no_related_evidence"`. If you accept the fifth type, FR-002 in the spec should be updated to list it.

## Config Keys

```toml
[explain]
generator = "rule_based"
min_overlap = 0.2
max_quote_chars = 120
fallback_type = "unsupported_claim"
```

## Test Approach

- **Nearest**: the sentence sharing most words is chosen and its `chunk_id` returned; a span with no shared words gives `no_related_evidence`; ties resolve to the first sentence.
- **Types**: "£150" against "£75" gives `number_mismatch`; "3 March 2025" against "13 March 2025" gives `date_mismatch`; an unknown name gives `entity_not_in_evidence`; a span with both a number and a date difference gives `number_mismatch`; related evidence with no difference gives the fallback type.
- **Templates**: exact expected text for each type; the quote respects the length limit.
- **Determinism**: the same input gives the same explanation over repeated runs.
- **Swap**: a stub generator selected by config is used in place of the rule-based one.
- **Privacy**: no log output contains the fixture sentinel word.

## Risks and Items to Verify

- Entity detection by capitalisation is rough and will miss or over-detect. It is used only to pick a reason type, never to change a verdict.
- The value of `min_overlap` is a guess. It should be tuned once real flagged spans exist.

## Assumptions Carried From the Spec

General reason wording. No accuracy target for `reason_type` yet. Entities come from rules, with no extra model.
