import logging
import re

import pytest

from evalsvc.config import DetectionSettings
from evalsvc.evaluators.groundedness import (
    EMPTY_EVIDENCE,
    INPUT_TOO_LONG,
    NO_ROOM_FOR_EVIDENCE,
    evaluate_groundedness,
    verdict_from_tokens,
)
from evalsvc.types import Chunk, Sentence, TokenScore
from tests.fakes import SUPPORTED_PROB, UNSUPPORTED_PROB, FakeDetector

SETTINGS = DetectionSettings()
EVIDENCE = "alpha beta gamma delta epsilon"


def make_chunks(texts, heading=None):
    return [
        Chunk(
            chunk_id=f"c{i + 1}",
            evidence_index=i,
            start=0,
            end=len(text),
            text=text,
            heading=heading,
            token_count=len(text.split()),
        )
        for i, text in enumerate(texts)
    ]


def make_sentences(answer, non_factual=()):
    sentences = []
    for match in re.finditer(r"\S[^.!?]*[.!?]", answer):
        index = len(sentences)
        sentences.append(
            Sentence(
                index=index,
                start=match.start(),
                end=match.end(),
                text=match.group(),
                factual=index not in non_factual,
            )
        )
    return sentences


def word_tokens(answer, probs):
    words = list(re.finditer(r"\S+", answer))
    return [TokenScore(start=w.start(), end=w.end(), prob=p) for w, p in zip(words, probs)]


def evaluate(answer, evidence=(EVIDENCE,), detector=None, settings=SETTINGS, non_factual=()):
    detector = detector or FakeDetector()
    result = evaluate_groundedness(
        "alpha question",
        make_chunks(list(evidence)),
        answer,
        make_sentences(answer, non_factual),
        detector,
        settings,
    )
    return result, detector


# --- verdict_from_tokens (T007) ---


def test_one_flagged_sentence_out_of_seven_scores_six_sevenths():
    answer = "Alpha beta. Beta gamma. Gamma delta. Alpha unicorn. Delta alpha. Beta delta. Gamma alpha."
    probs = [0.1] * 14
    probs[7] = 0.9  # "unicorn."

    verdict, score, spans = verdict_from_tokens(
        word_tokens(answer, probs), answer, make_sentences(answer), 0.5
    )

    assert verdict == "fail"
    assert score == pytest.approx(6 / 7)
    assert [span.text for span in spans] == ["unicorn."]


def test_no_spans_gives_pass_and_a_full_score():
    answer = "Alpha beta. Beta gamma."

    verdict, score, spans = verdict_from_tokens(
        word_tokens(answer, [0.1] * 4), answer, make_sentences(answer), 0.5
    )

    assert (verdict, score, spans) == ("pass", 1.0, [])


def test_excluded_span_does_not_lower_the_score_or_fail():
    answer = "Sorry unicorn. Alpha beta."

    verdict, score, spans = verdict_from_tokens(
        word_tokens(answer, [0.1, 0.9, 0.1, 0.1]),
        answer,
        make_sentences(answer, non_factual={0}),
        0.5,
    )

    assert verdict == "pass"
    assert score == 1.0
    assert [(span.text, span.excluded) for span in spans] == [("unicorn.", True)]


def test_no_factual_sentences_gives_an_empty_score_and_pass():
    answer = "Sorry unicorn."

    verdict, score, _ = verdict_from_tokens(
        word_tokens(answer, [0.1, 0.9]), answer, make_sentences(answer, non_factual={0}), 0.5
    )

    assert verdict == "pass"
    assert score is None


def test_a_higher_threshold_can_turn_fail_into_pass():
    answer = "Alpha unicorn."
    tokens = word_tokens(answer, [0.1, 0.7])
    sentences = make_sentences(answer)

    assert verdict_from_tokens(tokens, answer, sentences, 0.5)[0] == "fail"
    assert verdict_from_tokens(tokens, answer, sentences, 0.8)[0] == "pass"


# --- evaluate_groundedness (T008) ---


def test_supported_answer_passes_in_one_call():
    result, detector = evaluate("Alpha beta gamma. Delta epsilon.")

    assert result.evaluable is True
    assert result.verdict == "pass"
    assert result.score == 1.0
    assert result.unsupported_spans == []
    assert result.max_span_confidence == 0.0
    assert result.max_token_probability == SUPPORTED_PROB
    assert result.windows_run == 1
    assert detector.calls == [[[EVIDENCE]]]


def test_unsupported_claim_is_flagged_with_exact_offsets():
    answer = "Alpha beta gamma. Delta unicorn epsilon."

    result, _ = evaluate(answer)

    assert result.verdict == "fail"
    assert result.score == 0.5
    assert len(result.unsupported_spans) == 1
    span = result.unsupported_spans[0]
    assert span.text == "unicorn"
    assert answer[span.start : span.end] == span.text
    assert span.confidence == UNSUPPORTED_PROB
    assert result.max_span_confidence == UNSUPPORTED_PROB
    assert result.max_token_probability == UNSUPPORTED_PROB


def test_result_carries_model_threshold_and_token_scores():
    answer = "Alpha beta."
    settings = DetectionSettings(threshold=0.7)

    result, detector = evaluate(answer, settings=settings)

    assert result.model == detector.info
    assert result.threshold == 0.7
    assert [answer[t.start : t.end] for t in result.token_scores] == ["Alpha", "beta."]


def test_heading_is_part_of_the_context_given_to_the_detector():
    detector = FakeDetector()
    chunks = make_chunks(["alpha beta"], heading="Gamma")
    answer = "Gamma alpha."

    result = evaluate_groundedness(
        "question", chunks, answer, make_sentences(answer), detector, SETTINGS
    )

    assert detector.calls == [[["Gamma\nalpha beta"]]]
    assert result.verdict == "pass"


def test_excluded_span_is_recorded_but_does_not_fail_the_item():
    result, _ = evaluate("Sorry unicorn. Alpha beta.", non_factual={0})

    assert result.verdict == "pass"
    assert result.score == 1.0
    # "Sorry" is not in the evidence either, so the whole sentence is one span.
    assert [(s.text, s.excluded) for s in result.unsupported_spans] == [("Sorry unicorn.", True)]
    assert result.max_span_confidence == 0.0
    assert result.max_token_probability == SUPPORTED_PROB


# --- Windows (T008) ---

FILLER = "the limit applies filler filler filler filler filler filler filler"
WITH_ZEBRA = "the limit applies zebra filler filler filler filler filler filler"
WINDOW_SETTINGS = DetectionSettings(
    window_evidence_tokens=30, window_overlap_tokens=10, safety_margin_tokens=0
)


def window_evidence():
    texts = [FILLER] * 10
    texts[5] = WITH_ZEBRA
    return texts


def test_large_evidence_is_checked_in_windows_within_the_limit():
    detector = FakeDetector(max_tokens=60)

    result, _ = evaluate(
        "The zebra limit applies.", window_evidence(), detector, WINDOW_SETTINGS
    )

    assert result.windows_run == 5
    assert len(detector.calls) == 1
    windows = detector.calls[0]
    assert len(windows) == 5
    assert all(sum(len(passage.split()) for passage in window) <= 30 for window in windows)


def test_claim_supported_only_in_the_third_window_is_not_flagged():
    detector = FakeDetector(max_tokens=60)

    result, _ = evaluate(
        "The zebra limit applies.", window_evidence(), detector, WINDOW_SETTINGS
    )

    windows = detector.calls[0]
    assert [i for i, window in enumerate(windows) if WITH_ZEBRA in window] == [2]
    assert result.verdict == "pass"
    assert result.unsupported_spans == []


def test_claim_supported_in_no_window_is_flagged():
    detector = FakeDetector(max_tokens=60)

    result, _ = evaluate(
        "The unicorn limit applies.", window_evidence(), detector, WINDOW_SETTINGS
    )

    assert result.verdict == "fail"
    assert [span.text for span in result.unsupported_spans] == ["unicorn"]


# --- Items that cannot be checked (T009) ---


def assert_not_evaluable(result, reason):
    assert result.evaluable is False
    assert result.not_evaluable_reason == reason
    assert result.verdict is None
    assert result.score is None
    assert result.windows_run == 0
    assert result.unsupported_spans == []


def test_no_room_for_evidence():
    detector = FakeDetector(max_tokens=6)

    result, _ = evaluate("Alpha beta gamma.", detector=detector)

    assert_not_evaluable(result, NO_ROOM_FOR_EVIDENCE)
    assert detector.calls == []


def test_no_chunks():
    detector = FakeDetector()

    result, _ = evaluate("Alpha beta gamma.", evidence=(), detector=detector)

    assert_not_evaluable(result, EMPTY_EVIDENCE)
    assert detector.calls == []


def test_detector_rejecting_the_input():
    result, _ = evaluate("Alpha beta gamma.", detector=FakeDetector(reject_input=True))

    assert_not_evaluable(result, INPUT_TOO_LONG)


def test_logs_hold_no_text_from_the_item(caplog, sentinel):
    caplog.set_level(logging.DEBUG)

    evaluate(f"Alpha {sentinel}.", evidence=(f"alpha {sentinel} evidence",))

    assert caplog.records
    assert sentinel not in caplog.text
