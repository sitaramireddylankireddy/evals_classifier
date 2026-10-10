"""The spaCy pipeline used for sentence splitting."""

import spacy
from spacy.language import Language

from evalsvc.config import ConfigError, SentenceSettings

BLANK_PIPELINE = "blank_en"
_SENTENCE_COMPONENTS = ("sentencizer", "senter", "parser")


def build_nlp(settings: SentenceSettings) -> Language:
    if settings.spacy_pipeline == BLANK_PIPELINE:
        nlp = spacy.blank("en")
    else:
        try:
            nlp = spacy.load(settings.spacy_pipeline)
        except OSError:
            raise ConfigError(
                f"spaCy pipeline '{settings.spacy_pipeline}' is not installed. "
                f"Use '{BLANK_PIPELINE}' or install the pipeline."
            ) from None

    if not any(nlp.has_pipe(name) for name in _SENTENCE_COMPONENTS):
        nlp.add_pipe("sentencizer")
    return nlp


def trim_range(text: str, start: int, end: int) -> tuple[int, int]:
    """Shrink a character range so it neither starts nor ends with whitespace."""
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return start, end


def sentence_ranges(text: str, nlp: Language) -> list[tuple[int, int]]:
    """Character ranges of the sentences in `text`, without surrounding whitespace."""
    if not text.strip():
        return []
    ranges = []
    for sentence in nlp(text).sents:
        start, end = trim_range(text, sentence.start_char, sentence.end_char)
        if start < end:
            ranges.append((start, end))
    return ranges
