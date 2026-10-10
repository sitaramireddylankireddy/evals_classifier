"""Split an answer into sentences that keep their position in the original text."""

import re

from spacy.language import Language

from evalsvc.config import ChecksSettings, SentenceSettings
from evalsvc.text.nlp import sentence_ranges
from evalsvc.text.patterns import has_checkable_value
from evalsvc.types import Sentence

# A bullet or a number at the start of a line. It is left out of the sentence.
_LIST_MARKER = re.compile(r"\s*(?:[-*•–]|\d+[.)])(?:\s+|$)")


def split_answer(
    answer: str,
    nlp: Language,
    settings: SentenceSettings,
    checks: ChecksSettings,
) -> list[Sentence]:
    rules = [(rule.name, re.compile(rule.pattern)) for rule in settings.non_factual_rules]
    sentences: list[Sentence] = []
    position = 0
    # Each line is split on its own, so a list item or a named field never
    # runs into the line after it.
    for line in answer.split("\n"):
        marker = _LIST_MARKER.match(line)
        body_start = marker.end() if marker else 0
        for start, end in sentence_ranges(line[body_start:], nlp):
            sentence_start = position + body_start + start
            sentence_end = position + body_start + end
            text = answer[sentence_start:sentence_end]
            rule = _matched_rule(text, rules, checks)
            sentences.append(
                Sentence(
                    index=len(sentences),
                    start=sentence_start,
                    end=sentence_end,
                    text=text,
                    factual=rule is None,
                    matched_rule=rule,
                )
            )
        position += len(line) + 1
    return sentences


def _matched_rule(
    text: str, rules: list[tuple[str, re.Pattern[str]]], checks: ChecksSettings
) -> str | None:
    """Name of the non-factual rule that applies, or None when the sentence is factual."""
    if has_checkable_value(text, checks):
        return None
    for name, pattern in rules:
        if pattern.search(text):
            return name
    return None
