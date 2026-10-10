"""Run the whole check for one item or for a list of items."""

import hashlib
import logging
import threading
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from spacy.language import Language

from evalsvc.config import DetectionSettings, Settings
from evalsvc.detector.model import HFTokenCounter, TransformerDetector
from evalsvc.detector.select import detection_settings_for, gpu_available, select_model
from evalsvc.evaluators.groundedness import evaluate_groundedness
from evalsvc.interfaces import (
    DeterministicChecks,
    Detector,
    LargeJudge,
    ReasonGenerator,
    ResultStore,
    TokenCounter,
)
from evalsvc.judge import build_judge
from evalsvc.records import (
    EscalationRecord,
    GroundednessRecord,
    ResultRecord,
    RunSummary,
    SpanRecord,
)
from evalsvc.safelog import log_event
from evalsvc.store.results import build_store
from evalsvc.text.chunking import chunk_evidence
from evalsvc.text.nlp import build_nlp
from evalsvc.text.sentences import split_answer
from evalsvc.types import Item, JudgeRequest, Sentence, Span

STAGE_CHECKS = "deterministic_checks"
STAGE_EXPLANATIONS = "explanations"


@dataclass
class Components:
    settings: Settings
    detection: DetectionSettings  # with the selected model's threshold in force
    nlp: Language
    detector: Detector
    counter: TokenCounter
    judge: LargeJudge
    store: ResultStore
    # Optional stages. None means the stage is skipped and named in the record.
    checks: DeterministicChecks | None = None
    reasons: ReasonGenerator | None = None


def build_components(
    settings: Settings,
    *,
    detector: Detector | None = None,
    judge: LargeJudge | None = None,
    store: ResultStore | None = None,
    checks: DeterministicChecks | None = None,
    reasons: ReasonGenerator | None = None,
) -> Components:
    """Build everything a run needs. Without a detector passed in, the model is
    selected from the hardware and loaded."""
    detection = settings.detection
    if detector is None:
        selected = select_model(settings, gpu_available())
        detector = TransformerDetector(selected, settings.model)
        detection = detection_settings_for(settings, selected)

    return Components(
        settings=settings,
        detection=detection,
        nlp=build_nlp(settings.sentences),
        detector=detector,
        counter=HFTokenCounter(detector),
        judge=judge if judge is not None else build_judge(settings),
        store=store if store is not None else build_store(settings),
        checks=checks,
        reasons=reasons,
    )


def is_sampled(item_id: str, rate: float, seed: str) -> bool:
    """Whether an item is in the random sample sent to the judge.

    The answer depends only on the ID and the seed, so it is the same on every run.
    """
    digest = hashlib.sha256(f"{seed}:{item_id}".encode()).digest()
    return int.from_bytes(digest[:8], "big") / 2**64 < rate


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds")


def _new_run_id() -> str:
    return f"{datetime.now(UTC):%Y%m%dT%H%M%S}-{uuid.uuid4().hex[:8]}"


@dataclass
class _Evaluated:
    item: Item
    record: ResultRecord
    claims: list[str]


def _claims(spans: list[Span], sentences: list[Sentence]) -> list[str]:
    """The answer sentences that hold a counted span, in order."""
    counted = [span for span in spans if not span.excluded]
    return [
        sentence.text
        for sentence in sentences
        if any(span.start < sentence.end and sentence.start < span.end for span in counted)
    ]


def _evaluate(item: Item, c: Components, run_id: str) -> _Evaluated:
    skipped = [
        name
        for name, stage in ((STAGE_CHECKS, c.checks), (STAGE_EXPLANATIONS, c.reasons))
        if stage is None
    ]
    common: dict[str, Any] = {
        "id": item.id,
        "run_id": run_id,
        "model": c.detector.info,
        "metadata": item.metadata,
        "stages_skipped": skipped,
    }

    def not_evaluable(reason: str, counts: dict[str, int] | None = None) -> _Evaluated:
        log_event("item.not_evaluable", item_id=item.id, reason=reason)
        record = ResultRecord(
            **common,
            evaluated_at=_now(),
            evaluable=False,
            not_evaluable_reason=reason,
            counts=counts or {},
        )
        return _Evaluated(item=item, record=record, claims=[])

    if not item.evaluable:
        return not_evaluable(str(item.not_evaluable_reason))

    stage = "chunking"
    try:
        chunks = chunk_evidence(item.evidence, c.counter, c.nlp, c.settings.chunking)
        stage = "sentences"
        sentences = split_answer(item.answer, c.nlp, c.settings.sentences, c.settings.checks)
        counts = {
            "evidence_items": len(item.evidence),
            "chunks": len(chunks),
            "evidence_tokens": sum(chunk.token_count for chunk in chunks),
            "sentences": len(sentences),
            "factual_sentences": sum(1 for sentence in sentences if sentence.factual),
        }

        stage = "detection"
        result = evaluate_groundedness(
            item.question, chunks, item.answer, sentences, c.detector, c.detection
        )
        if not result.evaluable:
            return not_evaluable(str(result.not_evaluable_reason), counts)

        stage = STAGE_CHECKS
        check_results = c.checks.run(item.answer, item.evidence) if c.checks else []

        stage = STAGE_EXPLANATIONS
        spans = []
        for span in result.unsupported_spans:
            explanation = (
                c.reasons.explain(span, item.answer, sentences, chunks) if c.reasons else None
            )
            spans.append(
                SpanRecord(
                    start=span.start,
                    end=span.end,
                    text=span.text,
                    confidence=span.confidence,
                    excluded=span.excluded,
                    reason_type=explanation.reason_type if explanation else None,
                    reason=explanation.reason if explanation else None,
                    nearest_chunk_id=explanation.nearest_chunk_id if explanation else None,
                )
            )
    except Exception:
        # The exception text may quote the item, so only the stage is logged.
        log_event("item.stage_failed", level=logging.ERROR, item_id=item.id, stage=stage)
        return not_evaluable(f"{stage}_failed")

    assert result.verdict is not None
    record = ResultRecord(
        **common,
        evaluated_at=_now(),
        evaluable=True,
        groundedness=GroundednessRecord(
            verdict=result.verdict,
            score=result.score,
            max_span_confidence=result.max_span_confidence,
            max_token_probability=result.max_token_probability,
            threshold=result.threshold,
            unsupported_spans=spans,
            token_scores=result.token_scores,
        ),
        deterministic_checks=check_results,
        sampled=is_sampled(item.id, c.settings.run.sample_rate, c.settings.run.sample_seed),
        windows_run=result.windows_run,
        counts=counts,
    )
    log_event(
        "item.evaluated", item_id=item.id, status=result.verdict, windows=result.windows_run
    )
    return _Evaluated(
        item=item, record=record, claims=_claims(result.unsupported_spans, sentences)
    )


def evaluate_item(item: Item, c: Components, run_id: str) -> ResultRecord:
    """Evaluate one item. Never raises for a problem with the item itself."""
    return _evaluate(item, c, run_id).record


def _escalation_cause(record: ResultRecord) -> str | None:
    if not record.evaluable or record.groundedness is None:
        return None
    failed = record.groundedness.verdict == "fail"
    if failed and record.sampled:
        return "fail_and_sample"
    if failed:
        return "fail"
    if record.sampled:
        return "sample"
    return None


def _call_with_timeout(function: Any, argument: Any, timeout: float) -> Any:
    """Call a function in a background thread and give up after `timeout` seconds."""
    outcome: dict[str, Any] = {}

    def run() -> None:
        try:
            outcome["value"] = function(argument)
        except Exception as exc:
            outcome["error"] = exc

    # A daemon thread, so a judge that never answers cannot keep the process alive.
    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    thread.join(timeout)
    if thread.is_alive():
        raise TimeoutError
    if "error" in outcome:
        raise outcome["error"]
    return outcome["value"]


def _escalate(evaluated: _Evaluated, cause: str, c: Components) -> EscalationRecord:
    item = evaluated.item
    request = JudgeRequest(
        item_id=item.id,
        question=item.question,
        answer=item.answer,
        claims=evaluated.claims,
        evidence=[evidence.text for evidence in item.evidence],
    )
    try:
        response = _call_with_timeout(c.judge.judge, request, c.settings.judge.timeout_seconds)
    except TimeoutError:
        error_code = "judge_timeout"
    except Exception:
        error_code = "judge_error"
    else:
        log_event("item.escalated", item_id=item.id, reason=cause, status="ok")
        return EscalationRecord(
            attempted=True,
            cause=cause,
            status="ok",
            judge_verdict=response.verdict,
            judge_rationale=response.rationale,
        )
    log_event(
        "item.escalated",
        level=logging.WARNING,
        item_id=item.id,
        reason=cause,
        status="failed",
        error_code=error_code,
    )
    return EscalationRecord(attempted=True, cause=cause, status="failed", error_code=error_code)


def evaluate_items(items: list[Item], c: Components, skipped_at_input: int = 0) -> RunSummary:
    """Evaluate a list and write one record per item.

    Phase 1 evaluates and stores every item. Phase 2 sends failed and sampled
    items to the judge and stores a new version of their records, so a slow
    judge never delays detection.
    """
    run_id = _new_run_id()

    evaluated: list[_Evaluated] = []
    for item in items:
        outcome = _evaluate(item, c, run_id)
        c.store.write(outcome.record)
        evaluated.append(outcome)

    escalated = 0
    escalation_failed = 0
    for outcome in evaluated:
        cause = _escalation_cause(outcome.record)
        if cause is None:
            continue
        escalation = _escalate(outcome, cause, c)
        outcome.record = outcome.record.model_copy(
            update={"escalated": True, "escalation": escalation, "evaluated_at": _now()}
        )
        c.store.write(outcome.record)
        escalated += 1
        if escalation.status == "failed":
            escalation_failed += 1

    records = [outcome.record for outcome in evaluated]
    verdicts = [r.groundedness.verdict for r in records if r.groundedness is not None]
    summary = RunSummary(
        run_id=run_id,
        model=c.detector.info.name,
        device=c.detector.info.device,
        threshold=c.detection.threshold,
        received=len(items) + skipped_at_input,
        skipped_at_input=skipped_at_input,
        evaluated=len(verdicts),
        passed=verdicts.count("pass"),
        failed=verdicts.count("fail"),
        not_evaluable=sum(1 for r in records if not r.evaluable),
        escalated=escalated,
        escalation_failed=escalation_failed,
    )
    log_event(
        "run.done",
        run_id=run_id,
        evaluated=summary.evaluated,
        passed=summary.passed,
        failed=summary.failed,
        not_evaluable=summary.not_evaluable,
        escalated=summary.escalated,
    )
    return summary
