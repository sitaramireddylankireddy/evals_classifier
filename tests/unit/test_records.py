from evalsvc.records import (
    SCHEMA_VERSION,
    EscalationRecord,
    GroundednessRecord,
    ResultRecord,
    SpanRecord,
)
from evalsvc.types import CheckResult, ModelInfo, TokenScore


def full_record() -> ResultRecord:
    return ResultRecord(
        id="a1",
        run_id="20261010T120000-abcd1234",
        evaluated_at="2026-10-10T12:00:00.000000+00:00",
        model=ModelInfo(name="m", revision="r", device="cpu"),
        evaluable=True,
        groundedness=GroundednessRecord(
            verdict="fail",
            score=0.5,
            max_span_confidence=0.95,
            max_token_probability=0.95,
            threshold=0.5,
            unsupported_spans=[
                SpanRecord(
                    start=6,
                    end=13,
                    text="unicorn",
                    confidence=0.95,
                    reason_type="no_related_evidence",
                    reason="No related evidence found for this statement.",
                    nearest_chunk_id="c1",
                )
            ],
            token_scores=[TokenScore(start=6, end=13, prob=0.95)],
        ),
        deterministic_checks=[CheckResult(check="amount_in_evidence", passed=False, start=0, end=4)],
        stages_skipped=[],
        escalated=True,
        sampled=False,
        escalation=EscalationRecord(
            attempted=True, cause="fail", status="ok", judge_verdict="v", judge_rationale="r"
        ),
        windows_run=2,
        counts={"sentences": 2},
        metadata={"category": "cards", "nested": {"a": [1, 2]}},
    )


def test_record_survives_a_round_trip_through_json():
    record = full_record()

    assert ResultRecord.model_validate_json(record.model_dump_json()) == record


def test_record_has_every_required_field():
    assert set(ResultRecord.model_fields) >= {
        "id",
        "model",
        "groundedness",
        "deterministic_checks",
        "escalated",
        "windows_run",
        "evaluated_at",
        "metadata",
        "stages_skipped",
        "sampled",
        "escalation",
    }
    assert set(GroundednessRecord.model_fields) >= {
        "verdict",
        "score",
        "max_span_confidence",
        "unsupported_spans",
        "threshold",
    }
    assert set(SpanRecord.model_fields) >= {
        "start",
        "end",
        "text",
        "confidence",
        "reason_type",
        "reason",
        "nearest_chunk_id",
    }


def test_not_evaluable_record_needs_no_verdict():
    record = ResultRecord(
        id="a1",
        run_id="r",
        evaluated_at="2026-10-10T12:00:00.000000+00:00",
        model=ModelInfo(name="m", revision="r"),
        evaluable=False,
        not_evaluable_reason="empty_answer",
    )

    assert record.schema_version == SCHEMA_VERSION
    assert record.groundedness is None
    assert record.escalated is False
    assert record.escalation.attempted is False
    assert record.deterministic_checks == []
    assert record.windows_run == 0
