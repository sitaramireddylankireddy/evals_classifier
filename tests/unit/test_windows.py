import re

import pytest

from evalsvc.detector.windows import aggregate_min, merge_spans, plan_windows
from evalsvc.types import Sentence, TokenScore


def word_tokens(answer, probs):
    words = list(re.finditer(r"\S+", answer))
    assert len(words) == len(probs)
    return [TokenScore(start=w.start(), end=w.end(), prob=p) for w, p in zip(words, probs)]


def whole_answer(answer, factual=True):
    return [Sentence(index=0, start=0, end=len(answer), text=answer, factual=factual)]


# --- plan_windows (T004) ---


def test_chunks_that_fit_give_one_window():
    assert plan_windows([10, 10, 10], capacity=100, overlap_tokens=10) == [(0, 3)]


def test_no_chunks_give_no_windows():
    assert plan_windows([], capacity=100, overlap_tokens=10) == []


def test_windows_overlap_and_cover_every_chunk():
    costs = [100] * 25

    windows = plan_windows(costs, capacity=1000, overlap_tokens=250)

    assert windows == [(0, 10), (7, 17), (14, 24), (21, 25)]


@pytest.mark.parametrize(
    ("costs", "capacity", "overlap"),
    [
        ([100] * 25, 1000, 250),
        ([120, 80, 300, 40, 40, 260, 90, 10, 200, 150, 75, 310], 500, 100),
        ([50] * 40, 175, 60),
        ([400, 400, 400], 500, 200),
    ],
)
def test_window_rules_hold(costs, capacity, overlap):
    windows = plan_windows(costs, capacity, overlap)

    # Whole chunks in order, within capacity.
    assert all(start < end for start, end in windows)
    assert all(sum(costs[start:end]) <= capacity for start, end in windows)
    # Every chunk is in at least one window.
    covered = {i for start, end in windows for i in range(start, end)}
    assert covered == set(range(len(costs)))
    # Each window moves forward and starts no later than where the previous one ended.
    for (prev_start, prev_end), (start, end) in zip(windows, windows[1:]):
        assert prev_start < start <= prev_end
        assert end > prev_end


def test_consecutive_windows_repeat_at_least_the_overlap():
    costs = [50] * 40

    windows = plan_windows(costs, capacity=500, overlap_tokens=120)

    for (_, prev_end), (start, _) in zip(windows, windows[1:]):
        assert sum(costs[start:prev_end]) >= 120


def test_overlap_is_reduced_when_it_would_block_progress():
    assert plan_windows([60, 60, 60], capacity=120, overlap_tokens=100) == [(0, 2), (1, 3)]
    assert plan_windows([60, 60, 60], capacity=119, overlap_tokens=100) == [(0, 1), (1, 2), (2, 3)]


def test_chunk_larger_than_capacity_gets_its_own_window():
    assert plan_windows([50, 200, 50], capacity=100, overlap_tokens=0) == [(0, 1), (1, 2), (2, 3)]


# --- aggregate_min (T005) ---


def test_each_token_takes_its_lowest_probability():
    answer = "alpha beta gamma"
    windows = [
        word_tokens(answer, [0.9, 0.9, 0.2]),
        word_tokens(answer, [0.1, 0.8, 0.9]),
        word_tokens(answer, [0.5, 0.7, 0.6]),
    ]

    combined = aggregate_min(windows)

    assert [token.prob for token in combined] == [0.1, 0.7, 0.2]
    assert [(t.start, t.end) for t in combined] == [(t.start, t.end) for t in windows[0]]


def test_one_window_passes_through_unchanged():
    tokens = word_tokens("alpha beta", [0.3, 0.6])

    assert aggregate_min([tokens]) == tokens


def test_no_windows_give_no_tokens():
    assert aggregate_min([]) == []


def test_mismatched_token_ranges_raise():
    first = word_tokens("alpha beta", [0.3, 0.6])
    shorter = word_tokens("alpha", [0.3])
    shifted = [TokenScore(start=0, end=4, prob=0.3), TokenScore(start=6, end=10, prob=0.6)]

    with pytest.raises(ValueError, match="different answer tokens"):
        aggregate_min([first, shorter])
    with pytest.raises(ValueError, match="different answer tokens"):
        aggregate_min([first, shifted])


# --- merge_spans (T006) ---

ANSWER = "The fee is fifty pounds today."


def test_neighbouring_tokens_above_the_threshold_form_one_span():
    tokens = word_tokens(ANSWER, [0.1, 0.1, 0.1, 0.9, 0.8, 0.1])

    spans = merge_spans(tokens, ANSWER, 0.5, whole_answer(ANSWER))

    assert len(spans) == 1
    span = spans[0]
    assert span.text == "fifty pounds"
    assert ANSWER[span.start : span.end] == span.text
    assert span.confidence == 0.9
    assert span.excluded is False


def test_token_at_or_below_the_threshold_splits_spans():
    tokens = word_tokens(ANSWER, [0.9, 0.5, 0.9, 0.1, 0.7, 0.8])

    spans = merge_spans(tokens, ANSWER, 0.5, whole_answer(ANSWER))

    assert [span.text for span in spans] == ["The", "is", "pounds today."]
    assert [span.confidence for span in spans] == [0.9, 0.9, 0.8]
    assert all(ANSWER[span.start : span.end] == span.text for span in spans)


def test_no_tokens_above_the_threshold_give_no_spans():
    tokens = word_tokens(ANSWER, [0.1] * 6)

    assert merge_spans(tokens, ANSWER, 0.5, whole_answer(ANSWER)) == []


def test_span_inside_a_non_factual_sentence_is_excluded():
    tokens = word_tokens(ANSWER, [0.1, 0.1, 0.1, 0.9, 0.8, 0.1])

    spans = merge_spans(tokens, ANSWER, 0.5, whole_answer(ANSWER, factual=False))

    assert [span.excluded for span in spans] == [True]


def test_span_reaching_into_a_factual_sentence_is_not_excluded():
    answer = "Sorry about that. The fee is fifty."
    sentences = [
        Sentence(index=0, start=0, end=17, text="Sorry about that.", factual=False),
        Sentence(index=1, start=18, end=35, text="The fee is fifty.", factual=True),
    ]
    tokens = word_tokens(answer, [0.1, 0.1, 0.9, 0.9, 0.1, 0.1, 0.1])

    spans = merge_spans(tokens, answer, 0.5, sentences)

    assert [span.text for span in spans] == ["that. The"]
    assert spans[0].excluded is False
