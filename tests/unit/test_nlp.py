import pytest

from evalsvc.config import ConfigError, SentenceSettings
from evalsvc.text.nlp import build_nlp, sentence_ranges, trim_range


@pytest.fixture(scope="module")
def nlp():
    return build_nlp(SentenceSettings())


def test_default_pipeline_splits_two_sentences(nlp):
    text = "The limit is five hundred pounds. It can be reviewed on request."

    ranges = sentence_ranges(text, nlp)

    assert [text[start:end] for start, end in ranges] == [
        "The limit is five hundred pounds.",
        "It can be reviewed on request.",
    ]


def test_ranges_have_no_surrounding_whitespace(nlp):
    text = "   First sentence here.   Second sentence here!  "

    ranges = sentence_ranges(text, nlp)

    assert [text[start:end] for start, end in ranges] == [
        "First sentence here.",
        "Second sentence here!",
    ]


def test_blank_text_gives_no_ranges(nlp):
    assert sentence_ranges("", nlp) == []
    assert sentence_ranges("  \t ", nlp) == []


def test_trim_range_removes_whitespace_at_both_ends():
    text = "  word  "

    assert trim_range(text, 0, len(text)) == (2, 6)
    assert trim_range("    ", 0, 4) == (4, 4)


def test_pipeline_that_is_not_installed_gives_a_clear_error():
    with pytest.raises(ConfigError, match="no_such_pipeline"):
        build_nlp(SentenceSettings(spacy_pipeline="no_such_pipeline"))
