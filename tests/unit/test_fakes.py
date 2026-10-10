from evalsvc.interfaces import Detector
from tests.fakes import SUPPORTED_PROB, UNSUPPORTED_PROB, FakeDetector


def test_fake_detector_satisfies_the_protocol():
    assert isinstance(FakeDetector(), Detector)


def test_word_in_the_context_is_supported_and_other_words_are_not():
    detector = FakeDetector()
    answer = "The limit is £900."

    [scores] = detector.score_batch([["The daily limit is £500."]], "What is the limit?", answer)

    assert [(answer[s.start : s.end], s.prob) for s in scores] == [
        ("The", SUPPORTED_PROB),
        ("limit", SUPPORTED_PROB),
        ("is", SUPPORTED_PROB),
        ("£900.", UNSUPPORTED_PROB),
    ]


def test_one_score_list_per_window_and_calls_are_recorded():
    detector = FakeDetector()
    contexts = [["first passage"], ["second passage", "third passage"]]

    result = detector.score_batch(contexts, "question", "second answer")

    assert len(result) == 2
    assert [score.prob for score in result[0]] == [UNSUPPORTED_PROB, UNSUPPORTED_PROB]
    assert [score.prob for score in result[1]] == [SUPPORTED_PROB, UNSUPPORTED_PROB]
    assert detector.calls == [contexts]


def test_costs_are_word_counts():
    detector = FakeDetector()

    assert detector.count_tokens("three short words") == 3
    assert detector.passage_cost("two words") == 2
    assert detector.fixed_cost("one two", "three four five") == 5
