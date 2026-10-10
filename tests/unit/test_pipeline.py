import logging

from evalsvc import pipeline
from evalsvc.config import (
    BaseModelSettings,
    LargeModelSettings,
    ModelSettings,
    Settings,
    StoreSettings,
)
from evalsvc.pipeline import STAGE_CHECKS, STAGE_EXPLANATIONS, evaluate_item, evaluate_items
from evalsvc.store.results import FILE_NAME
from evalsvc.types import ReasonCode
from tests.fakes import (
    EVIDENCE,
    SUPPORTED_ANSWER,
    UNSUPPORTED_ANSWER,
    FakeChecks,
    FakeDetector,
    FakeReasons,
    make_components,
    make_item,
)

# --- Components (T006) ---


def test_components_are_built_on_stand_ins_without_a_model(tmp_path):
    components = make_components(tmp_path)

    assert components.detector.info.name == "fake-detector"
    assert components.detection.threshold == 0.5
    assert components.checks is None
    assert components.reasons is None
    assert (tmp_path / "store").is_dir()


class LoadedDetector(FakeDetector):
    """Takes the place of the real detector class and remembers what was selected."""

    def __init__(self, selected, model_settings):
        super().__init__()
        self.selected = selected


def selection_settings(tmp_path):
    return Settings(
        store=StoreSettings(path=str(tmp_path / "store")),
        model=ModelSettings(
            large=LargeModelSettings(path="C:/models/large", revision="l1", threshold=0.7),
            base=BaseModelSettings(path="C:/models/base", revision="b1", threshold=0.4),
        ),
    )


def test_large_model_is_requested_when_a_gpu_is_reported(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "gpu_available", lambda: True)
    monkeypatch.setattr(pipeline, "TransformerDetector", LoadedDetector)

    components = pipeline.build_components(selection_settings(tmp_path))

    assert components.detector.selected.variant == "large"
    assert components.detector.selected.device == "cuda"
    assert components.detection.threshold == 0.7


def test_base_model_is_requested_when_no_gpu_is_reported(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "gpu_available", lambda: False)
    monkeypatch.setattr(pipeline, "TransformerDetector", LoadedDetector)

    components = pipeline.build_components(selection_settings(tmp_path))

    assert components.detector.selected.variant == "base"
    assert components.detector.selected.device == "cpu"
    assert components.detection.threshold == 0.4


# --- One item (T007) ---


def test_supported_answer_gives_a_pass_record(tmp_path):
    components = make_components(tmp_path)

    record = evaluate_item(make_item(), components, "run-1")

    assert record.id == "a1"
    assert record.run_id == "run-1"
    assert record.evaluable is True
    assert record.groundedness.verdict == "pass"
    assert record.groundedness.score == 1.0
    assert record.groundedness.unsupported_spans == []
    assert record.groundedness.threshold == 0.5
    assert record.model == components.detector.info
    assert record.windows_run == 1
    assert record.evaluated_at.endswith("+00:00")
    assert record.counts == {
        "evidence_items": 1,
        "chunks": 1,
        "evidence_tokens": 5,
        "sentences": 1,
        "factual_sentences": 1,
    }


def test_unsupported_answer_gives_a_fail_record_with_exact_spans(tmp_path):
    components = make_components(tmp_path)
    item = make_item(answer=UNSUPPORTED_ANSWER)

    record = evaluate_item(item, components, "run-1")

    assert record.groundedness.verdict == "fail"
    assert [span.text for span in record.groundedness.unsupported_spans] == ["unicorn"]
    assert all(
        item.answer[span.start : span.end] == span.text
        for span in record.groundedness.unsupported_spans
    )
    assert record.groundedness.max_span_confidence > 0.5
    assert len(record.groundedness.token_scores) == 3


def test_stages_that_are_not_built_are_skipped_and_named(tmp_path):
    components = make_components(tmp_path)

    record = evaluate_item(make_item(answer=UNSUPPORTED_ANSWER), components, "run-1")

    assert record.stages_skipped == [STAGE_CHECKS, STAGE_EXPLANATIONS]
    assert record.deterministic_checks == []
    span = record.groundedness.unsupported_spans[0]
    assert (span.reason_type, span.reason, span.nearest_chunk_id) == (None, None, None)


def test_optional_stages_fill_the_record_when_they_exist(tmp_path):
    components = make_components(tmp_path, checks=FakeChecks(), reasons=FakeReasons())

    record = evaluate_item(make_item(answer=UNSUPPORTED_ANSWER), components, "run-1")

    assert record.stages_skipped == []
    assert [check.check for check in record.deterministic_checks] == ["fake_check"]
    span = record.groundedness.unsupported_spans[0]
    assert span.reason_type == "fake_reason"
    assert span.reason == "No support found for 7 characters."
    assert span.nearest_chunk_id == "c1"


def test_item_metadata_is_kept_in_the_record(tmp_path):
    components = make_components(tmp_path)
    item = make_item(metadata={"category": "cards"})

    record = evaluate_item(item, components, "run-1")

    assert record.metadata == {"category": "cards"}


# --- A list (T008) ---


def test_three_items_give_three_current_records_and_a_summary(tmp_path):
    components = make_components(tmp_path)
    items = [
        make_item("a1"),
        make_item("a2", answer=UNSUPPORTED_ANSWER),
        make_item("a3", answer="Delta epsilon."),
    ]

    summary = evaluate_items(items, components, skipped_at_input=2)

    current = {record.id: record for record in components.store.iter_current()}
    assert set(current) == {"a1", "a2", "a3"}
    assert current["a2"].groundedness.verdict == "fail"
    assert all(record.run_id == summary.run_id for record in current.values())
    assert summary.received == 5
    assert summary.skipped_at_input == 2
    assert (summary.evaluated, summary.passed, summary.failed) == (3, 2, 1)
    assert summary.not_evaluable == 0
    assert summary.model == "fake-detector"
    assert summary.threshold == 0.5


def test_empty_list_writes_nothing(tmp_path):
    components = make_components(tmp_path)

    summary = evaluate_items([], components)

    assert not (tmp_path / "store" / FILE_NAME).exists()
    assert (summary.received, summary.evaluated, summary.escalated) == (0, 0, 0)


def test_evaluating_the_same_id_again_keeps_history_and_one_current_record(tmp_path):
    components = make_components(tmp_path)

    evaluate_items([make_item("a1")], components)
    second = evaluate_items([make_item("a1", answer="Delta epsilon.")], components)

    lines = (tmp_path / "store" / FILE_NAME).read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert [record.run_id for record in components.store.iter_current()] == [second.run_id]


# --- Items that cannot be evaluated (T009) ---


def test_item_marked_not_evaluable_at_input_gets_a_record_with_no_verdict(tmp_path):
    components = make_components(tmp_path)
    item = make_item(
        answer="  ", evaluable=False, not_evaluable_reason=ReasonCode.EMPTY_ANSWER
    )

    summary = evaluate_items([item], components)

    record = components.store.get_current("a1")
    assert record.evaluable is False
    assert record.not_evaluable_reason == "empty_answer"
    assert record.groundedness is None
    assert record.escalated is False
    assert (summary.evaluated, summary.not_evaluable) == (0, 1)


def test_detector_crash_on_one_item_leaves_the_others_untouched(tmp_path, caplog, sentinel):
    caplog.set_level(logging.DEBUG)
    components = make_components(tmp_path, detector=FakeDetector(fail_on=sentinel))
    items = [
        make_item("a1"),
        make_item("a2", answer=f"Alpha {sentinel} gamma."),
        make_item("a3", answer=UNSUPPORTED_ANSWER),
    ]

    summary = evaluate_items(items, components)

    crashed = components.store.get_current("a2")
    assert crashed.evaluable is False
    assert crashed.not_evaluable_reason == "detection_failed"
    assert components.store.get_current("a1").groundedness.verdict == "pass"
    assert components.store.get_current("a3").groundedness.verdict == "fail"
    assert (summary.evaluated, summary.not_evaluable) == (2, 1)
    # The crash message quoted the answer; it must not have reached the logs.
    assert sentinel not in caplog.text


def test_item_the_detector_cannot_fit_is_not_evaluable(tmp_path):
    components = make_components(tmp_path, detector=FakeDetector(max_tokens=3))

    record = evaluate_item(make_item(), components, "run-1")

    assert record.evaluable is False
    assert record.not_evaluable_reason == "no_room_for_evidence"
    assert record.counts["chunks"] == 1


def test_evidence_text_never_reaches_the_logs(tmp_path, caplog, sentinel):
    caplog.set_level(logging.DEBUG)
    components = make_components(tmp_path)
    item = make_item(answer=f"Alpha {sentinel}.", evidence=(f"{EVIDENCE} {sentinel}x",))

    evaluate_items([item], components)

    assert caplog.records
    assert sentinel not in caplog.text
    assert SUPPORTED_ANSWER not in caplog.text
