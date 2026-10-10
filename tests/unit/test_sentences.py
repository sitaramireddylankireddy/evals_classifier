import pytest

from evalsvc.config import ChecksSettings, NonFactualRule, SentenceSettings
from evalsvc.text.nlp import build_nlp
from evalsvc.text.sentences import split_answer

SETTINGS = SentenceSettings()
CHECKS = ChecksSettings()


@pytest.fixture(scope="module")
def nlp():
    return build_nlp(SETTINGS)


def split(answer, nlp, settings=SETTINGS):
    return split_answer(answer, nlp, settings, CHECKS)


def texts(sentences):
    return [sentence.text for sentence in sentences]


def assert_offsets(answer, sentences):
    for sentence in sentences:
        assert answer[sentence.start : sentence.end] == sentence.text


# --- Offsets (T010) ---


def test_offsets_reproduce_every_sentence(nlp):
    answer = "The daily limit is £500. It can be reviewed after 3 months. Ask in any branch!"

    sentences = split(answer, nlp)

    assert texts(sentences) == [
        "The daily limit is £500.",
        "It can be reviewed after 3 months.",
        "Ask in any branch!",
    ]
    assert_offsets(answer, sentences)
    assert [sentence.index for sentence in sentences] == [0, 1, 2]


def test_sentences_are_in_order_and_do_not_overlap(nlp):
    answer = "First point here. Second point here.\nThird point here. Fourth point here."

    sentences = split(answer, nlp)

    assert len(sentences) == 4
    assert all(a.end <= b.start for a, b in zip(sentences, sentences[1:]))


def test_amounts_and_abbreviations_are_not_split(nlp):
    answer = "The fee is £1,250.00 for this plan. It applies e.g. to large loans."

    sentences = split(answer, nlp)

    assert texts(sentences) == [
        "The fee is £1,250.00 for this plan.",
        "It applies e.g. to large loans.",
    ]
    assert_offsets(answer, sentences)


@pytest.mark.parametrize("answer", ["", "   ", "\n\t \n"])
def test_empty_answer_gives_no_sentences(nlp, answer):
    assert split(answer, nlp) == []


def test_whitespace_does_not_break_offsets(nlp):
    answer = "  First point here.\t\r\n\n   Second   point here.  "

    sentences = split(answer, nlp)

    assert texts(sentences) == ["First point here.", "Second   point here."]
    assert_offsets(answer, sentences)


# --- List items (T011) ---


def test_bulleted_items_are_separate_units(nlp):
    answer = "Here is a summary:\n- The fee is £5.\n- The card arrives in 5 days.\n* Keep your old card"

    sentences = split(answer, nlp)

    assert texts(sentences) == [
        "Here is a summary:",
        "The fee is £5.",
        "The card arrives in 5 days.",
        "Keep your old card",
    ]
    assert_offsets(answer, sentences)


def test_numbered_items_are_separate_units(nlp):
    answer = "1. Call the helpline.\n2) Visit a branch.\n  3. Use the app."

    sentences = split(answer, nlp)

    assert texts(sentences) == ["Call the helpline.", "Visit a branch.", "Use the app."]
    assert_offsets(answer, sentences)


def test_lines_without_full_stops_are_separate_units(nlp):
    answer = "Account type: current\nMonthly fee: none"

    sentences = split(answer, nlp)

    assert texts(sentences) == ["Account type: current", "Monthly fee: none"]
    assert_offsets(answer, sentences)


# --- Non-factual sentences (T012) ---


def test_apology_is_marked_non_factual_with_the_rule_name(nlp):
    answer = "We are sorry for the delay. The card was sent by post."

    sentences = split(answer, nlp)

    assert [(s.factual, s.matched_rule) for s in sentences] == [(False, "apology"), (True, None)]


def test_non_factual_sentences_stay_in_the_output_with_offsets(nlp):
    answer = "Thank you for contacting us. The card was sent by post."

    sentences = split(answer, nlp)

    assert len(sentences) == 2
    assert sentences[0].factual is False
    assert sentences[0].matched_rule == "thanks"
    assert_offsets(answer, sentences)


@pytest.mark.parametrize(
    "answer",
    [
        "We are sorry that you were charged £50.",
        "We are sorry the payment on 3 March 2025 failed.",
        "We are sorry the rate rose to 5%.",
        "We are sorry that section 4.2 was not applied.",
    ],
)
def test_sentence_with_a_checkable_value_stays_factual(nlp, answer):
    sentences = split(answer, nlp)

    assert [(s.factual, s.matched_rule) for s in sentences] == [(True, None)]


def test_changing_the_rule_list_changes_the_result(nlp):
    custom = SentenceSettings(
        non_factual_rules=[NonFactualRule(name="greeting", pattern=r"(?i)^hello\b")]
    )
    answer = "Hello and welcome back. We are sorry for the delay."

    sentences = split(answer, nlp, custom)

    assert [(s.factual, s.matched_rule) for s in sentences] == [(False, "greeting"), (True, None)]


def test_no_rules_means_every_sentence_is_factual(nlp):
    answer = "We are sorry for the delay. Thank you for waiting."

    sentences = split(answer, nlp, SentenceSettings(non_factual_rules=[]))

    assert all(sentence.factual for sentence in sentences)
