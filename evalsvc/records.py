"""The stored outcome of evaluating one item, and the summary of a run."""

from typing import Any, Literal

from pydantic import Field

from evalsvc.types import CheckResult, FrozenModel, ModelInfo, TokenScore

SCHEMA_VERSION = 1


class SpanRecord(FrozenModel):
    start: int
    end: int
    text: str
    confidence: float
    excluded: bool = False
    # Empty until the explanation stage exists.
    reason_type: str | None = None
    reason: str | None = None
    nearest_chunk_id: str | None = None


class GroundednessRecord(FrozenModel):
    verdict: Literal["pass", "fail"]
    score: float | None
    max_span_confidence: float
    max_token_probability: float
    threshold: float
    unsupported_spans: list[SpanRecord] = Field(default_factory=list)
    token_scores: list[TokenScore] = Field(default_factory=list)


class EscalationRecord(FrozenModel):
    attempted: bool = False
    cause: Literal["fail", "sample", "fail_and_sample"] | None = None
    status: Literal["ok", "failed"] | None = None
    error_code: str | None = None
    judge_verdict: str | None = None
    judge_rationale: str | None = None


class ResultRecord(FrozenModel):
    schema_version: int = SCHEMA_VERSION
    id: str
    run_id: str
    evaluated_at: str  # UTC, ISO 8601
    model: ModelInfo
    evaluable: bool
    not_evaluable_reason: str | None = None
    groundedness: GroundednessRecord | None = None
    deterministic_checks: list[CheckResult] = Field(default_factory=list)
    stages_skipped: list[str] = Field(default_factory=list)
    escalated: bool = False
    sampled: bool = False
    escalation: EscalationRecord = EscalationRecord()
    windows_run: int = 0
    counts: dict[str, int] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RunSummary(FrozenModel):
    run_id: str
    model: str
    device: str | None
    threshold: float
    received: int
    skipped_at_input: int
    evaluated: int
    passed: int
    failed: int
    not_evaluable: int
    escalated: int
    escalation_failed: int
