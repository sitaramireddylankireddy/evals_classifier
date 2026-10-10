import logging

import pytest

from evalsvc.config import ConfigError, JudgeSettings, Settings
from evalsvc.interfaces import LargeJudge
from evalsvc.judge import STUB_RATIONALE, STUB_VERDICT, StubLargeJudge, build_judge
from evalsvc.pipeline import evaluate_items, is_sampled
from evalsvc.store.results import FILE_NAME, JsonlResultStore
from evalsvc.types import ReasonCode
from tests.fakes import (
    EVIDENCE,
    UNSUPPORTED_ANSWER,
    RaisingJudge,
    SlowJudge,
    make_components,
    make_item,
)

# --- The stand-in judge (T005) ---


def test_stub_judge_satisfies_the_protocol():
    assert isinstance(StubLargeJudge(), LargeJudge)
    assert isinstance(build_judge(Settings()), StubLargeJudge)


def test_unknown_judge_kind_gives_a_clear_error():
    with pytest.raises(ConfigError, match="oracle"):
        build_judge(Settings(judge=JudgeSettings(kind="oracle")))


# --- Sampling (T010) ---


def test_sampling_is_the_same_on_every_call():
    answers = [is_sampled("item-42", 0.5, "seed") for _ in range(20)]

    assert len(set(answers)) == 1


def test_rate_zero_samples_nothing_and_rate_one_samples_everything():
    ids = [f"item-{n}" for n in range(500)]

    assert not any(is_sampled(item_id, 0.0, "seed") for item_id in ids)
    assert all(is_sampled(item_id, 1.0, "seed") for item_id in ids)


def test_sampled_share_is_close_to_the_rate():
    ids = [f"item-{n}" for n in range(10_000)]

    share = sum(is_sampled(item_id, 0.02, "evalsvc") for item_id in ids) / len(ids)

    assert 0.015 <= share <= 0.025


def test_a_different_seed_gives_a_different_sample():
    ids = [f"item-{n}" for n in range(2_000)]

    first = {item_id for item_id in ids if is_sampled(item_id, 0.1, "seed-a")}
    second = {item_id for item_id in ids if is_sampled(item_id, 0.1, "seed-b")}

    assert first != second


# --- Escalation (T011) ---


def test_failed_item_is_sent_to_the_judge_with_its_claims_and_evidence(tmp_path):
    judge = StubLargeJudge()
    components = make_components(tmp_path, judge=judge)
    items = [make_item("a1"), make_item("a2", answer=f"Alpha beta. {UNSUPPORTED_ANSWER}")]

    summary = evaluate_items(items, components)

    assert [request.item_id for request in judge.requests] == ["a2"]
    request = judge.requests[0]
    assert request.claims == [UNSUPPORTED_ANSWER]
    assert request.evidence == [EVIDENCE]
    assert request.question == "alpha question"
    assert request.answer == f"Alpha beta. {UNSUPPORTED_ANSWER}"

    record = components.store.get_current("a2")
    assert record.escalated is True
    assert record.sampled is False
    assert record.escalation.attempted is True
    assert record.escalation.cause == "fail"
    assert record.escalation.status == "ok"
    assert record.escalation.judge_verdict == STUB_VERDICT
    assert record.escalation.judge_rationale == STUB_RATIONALE
    assert (summary.escalated, summary.escalation_failed) == (1, 0)


def test_passing_item_that_is_not_sampled_is_not_sent(tmp_path):
    judge = StubLargeJudge()
    components = make_components(tmp_path, judge=judge)

    summary = evaluate_items([make_item("a1")], components)

    record = components.store.get_current("a1")
    assert judge.requests == []
    assert record.escalated is False
    assert record.escalation.attempted is False
    assert summary.escalated == 0


def test_sampled_items_are_sent_whatever_their_verdict(tmp_path):
    judge = StubLargeJudge()
    components = make_components(tmp_path, judge=judge, sample_rate=1.0)
    items = [make_item("a1"), make_item("a2", answer=UNSUPPORTED_ANSWER)]

    summary = evaluate_items(items, components)

    passed = components.store.get_current("a1")
    failed = components.store.get_current("a2")
    assert (passed.sampled, passed.escalation.cause) == (True, "sample")
    assert (failed.sampled, failed.escalation.cause) == (True, "fail_and_sample")
    assert judge.requests[0].claims == []
    assert summary.escalated == 2


def test_not_evaluable_item_is_never_sent(tmp_path):
    judge = StubLargeJudge()
    components = make_components(tmp_path, judge=judge, sample_rate=1.0)
    item = make_item(answer="", evaluable=False, not_evaluable_reason=ReasonCode.EMPTY_ANSWER)

    evaluate_items([item], components)

    assert judge.requests == []


def test_every_item_is_stored_before_the_first_judge_call(tmp_path):
    store = JsonlResultStore(tmp_path / "store")
    seen = []

    class CountingJudge(StubLargeJudge):
        def judge(self, request):
            seen.append(len(list(store.iter_current())))
            return super().judge(request)

    components = make_components(tmp_path, judge=CountingJudge(), store=store)
    items = [make_item(f"a{n}", answer=UNSUPPORTED_ANSWER) for n in range(1, 4)]

    evaluate_items(items, components)

    assert seen == [3, 3, 3]


def test_escalation_adds_a_new_version_and_keeps_the_first(tmp_path):
    components = make_components(tmp_path)

    evaluate_items([make_item("a1", answer=UNSUPPORTED_ANSWER)], components)

    lines = (tmp_path / "store" / FILE_NAME).read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert [record.escalated for record in components.store.iter_current()] == [True]


# --- Judge failures (T012) ---


def test_judge_that_raises_is_recorded_and_the_rest_are_still_escalated(
    tmp_path, caplog, sentinel
):
    caplog.set_level(logging.DEBUG)
    judge = RaisingJudge()
    components = make_components(tmp_path, judge=judge)
    items = [
        make_item("a1", answer=f"Alpha {sentinel} gamma."),
        make_item("a2", answer=UNSUPPORTED_ANSWER),
    ]

    summary = evaluate_items(items, components)

    assert judge.calls == 2
    for item_id in ("a1", "a2"):
        record = components.store.get_current(item_id)
        assert record.escalated is True
        assert record.escalation.attempted is True
        assert record.escalation.status == "failed"
        assert record.escalation.error_code == "judge_error"
        assert record.escalation.judge_verdict is None
        assert record.groundedness.verdict == "fail"
    assert (summary.escalated, summary.escalation_failed) == (2, 2)
    # The judge's error quoted the answer; it must not have reached the logs.
    assert sentinel not in caplog.text


def test_judge_that_is_too_slow_is_recorded_as_a_timeout(tmp_path):
    components = make_components(tmp_path, judge=SlowJudge(seconds=0.5), timeout_seconds=0.05)

    summary = evaluate_items([make_item("a1", answer=UNSUPPORTED_ANSWER)], components)

    record = components.store.get_current("a1")
    assert record.escalation.status == "failed"
    assert record.escalation.error_code == "judge_timeout"
    assert summary.escalation_failed == 1
