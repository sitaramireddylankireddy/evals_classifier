import logging

import pytest

from evalsvc.config import DetectionSettings
from evalsvc.evaluators.groundedness import evaluate_groundedness
from evalsvc.harness.golden import GoldenItem
from evalsvc.harness.scoring import score_items
from evalsvc.text.chunking import chunk_evidence
from evalsvc.text.sentences import split_answer
from evalsvc.types import ReasonCode
from tests.fakes import (
    SUPPORTED_PROB,
    UNSUPPORTED_ANSWER,
    UNSUPPORTED_PROB,
    FakeDetector,
    make_components,
    make_item,
)


def golden(item, is_failure=False, category=None):
    return GoldenItem(item=item, is_failure=is_failure, category=category)


def test_one_scored_item_per_golden_item(tmp_path):
    components = make_components(tmp_path)
    items = [
        golden(make_item("a1"), is_failure=False, category="cards"),
        golden(make_item("a2", answer=UNSUPPORTED_ANSWER), is_failure=True),
    ]

    scored = score_items(items, components)

    assert [(s.item_id, s.is_failure, s.category, s.evaluable) for s in scored] == [
        ("a1", False, "cards", True),
        ("a2", True, None, True),
    ]
    assert [s.score for s in scored] == [SUPPORTED_PROB, UNSUPPORTED_PROB]
    assert all(s.seconds is not None and s.seconds >= 0 for s in scored)


def test_the_detector_is_called_once_per_evaluable_item(tmp_path):
    detector = FakeDetector()
    components = make_components(tmp_path, detector=detector)
    items = [
        golden(make_item("a1")),
        golden(make_item("a2", answer=UNSUPPORTED_ANSWER)),
        golden(
            make_item(
                "a3", answer="", evaluable=False, not_evaluable_reason=ReasonCode.EMPTY_ANSWER
            )
        ),
    ]

    scored = score_items(items, components)

    assert len(detector.calls) == 2
    assert (scored[2].evaluable, scored[2].not_evaluable_reason) == (False, "empty_answer")
    assert scored[2].score is None
    assert scored[2].seconds is None


def test_item_the_detector_cannot_fit_is_not_evaluable(tmp_path):
    components = make_components(tmp_path, detector=FakeDetector(max_tokens=3))

    [scored] = score_items([golden(make_item("a1"))], components)

    assert (scored.evaluable, scored.not_evaluable_reason) == (False, "no_room_for_evidence")


def test_detector_crash_marks_the_item_and_logs_no_text(tmp_path, caplog, sentinel):
    caplog.set_level(logging.DEBUG)
    components = make_components(tmp_path, detector=FakeDetector(fail_on=sentinel))
    items = [golden(make_item("a1", answer=f"Alpha {sentinel}.")), golden(make_item("a2"))]

    scored = score_items(items, components)

    assert (scored[0].evaluable, scored[0].not_evaluable_reason) == (False, "evaluation_failed")
    assert scored[1].evaluable is True
    assert sentinel not in caplog.text


@pytest.mark.parametrize(
    "answer",
    [
        "Alpha beta gamma.",
        UNSUPPORTED_ANSWER,
        "Alpha beta. Delta unicorn epsilon. Gamma.",
        "We are sorry about the unicorn. Alpha beta.",
    ],
)
@pytest.mark.parametrize("threshold", [0.01, 0.05, 0.5, 0.94, 0.95, 0.99])
def test_score_above_the_threshold_means_exactly_a_fail_verdict(tmp_path, answer, threshold):
    """The harness relies on this to apply any threshold without running the detector again."""
    components = make_components(tmp_path)
    item = make_item("a1", answer=answer)

    [scored] = score_items([golden(item)], components)
    chunks = chunk_evidence(item.evidence, components.counter, components.nlp, components.settings.chunking)
    sentences = split_answer(
        item.answer, components.nlp, components.settings.sentences, components.settings.checks
    )
    result = evaluate_groundedness(
        item.question,
        chunks,
        item.answer,
        sentences,
        components.detector,
        DetectionSettings(threshold=threshold),
    )

    assert (result.verdict == "fail") == (scored.score > threshold)
