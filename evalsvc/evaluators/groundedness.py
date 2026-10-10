"""Groundedness: find the parts of an answer that the evidence does not support."""

from typing import Literal

from evalsvc.config import DetectionSettings
from evalsvc.detector.windows import aggregate_min, merge_spans, plan_windows
from evalsvc.interfaces import Detector, DetectorInputError
from evalsvc.safelog import log_event
from evalsvc.types import Chunk, GroundednessResult, Sentence, Span, TokenScore

EMPTY_EVIDENCE = "empty_evidence"
NO_ROOM_FOR_EVIDENCE = "no_room_for_evidence"
INPUT_TOO_LONG = "input_too_long"

Verdict = Literal["pass", "fail"]


def verdict_from_tokens(
    tokens: list[TokenScore], answer: str, sentences: list[Sentence], threshold: float
) -> tuple[Verdict, float | None, list[Span]]:
    """Spans, score, and verdict for one threshold, with no detector call.

    The score is the share of factual sentences that no counted span touches.
    """
    spans = merge_spans(tokens, answer, threshold, sentences)
    counted = [span for span in spans if not span.excluded]
    factual = [sentence for sentence in sentences if sentence.factual]

    score = None
    if factual:
        flagged = sum(
            1
            for sentence in factual
            if any(span.start < sentence.end and sentence.start < span.end for span in counted)
        )
        score = (len(factual) - flagged) / len(factual)

    verdict: Verdict = "fail" if counted else "pass"
    return verdict, score, spans


def evaluate_groundedness(
    question: str,
    chunks: list[Chunk],
    answer: str,
    sentences: list[Sentence],
    detector: Detector,
    settings: DetectionSettings,
) -> GroundednessResult:
    def not_evaluable(reason: str) -> GroundednessResult:
        log_event("groundedness.not_evaluable", reason=reason)
        return GroundednessResult(
            evaluable=False,
            not_evaluable_reason=reason,
            threshold=settings.threshold,
            model=detector.info,
        )

    if not chunks:
        return not_evaluable(EMPTY_EVIDENCE)

    costs = [detector.passage_cost(chunk.context_text) for chunk in chunks]
    budget = (
        detector.max_tokens
        - detector.fixed_cost(question, answer)
        - settings.safety_margin_tokens
    )
    if budget < max(costs):
        return not_evaluable(NO_ROOM_FOR_EVIDENCE)

    if sum(costs) <= budget:
        windows = [(0, len(chunks))]
    else:
        capacity = max(min(settings.window_evidence_tokens, budget), max(costs))
        windows = plan_windows(costs, capacity, settings.window_overlap_tokens)

    contexts = [[chunk.context_text for chunk in chunks[start:end]] for start, end in windows]
    try:
        per_window = detector.score_batch(contexts, question, answer)
    except DetectorInputError:
        return not_evaluable(INPUT_TOO_LONG)

    tokens = aggregate_min(per_window)
    verdict, score, spans = verdict_from_tokens(tokens, answer, sentences, settings.threshold)

    factual = [(sentence.start, sentence.end) for sentence in sentences if sentence.factual]
    factual_probs = [
        token.prob
        for token in tokens
        if any(start < token.end and token.start < end for start, end in factual)
    ]
    counted = [span.confidence for span in spans if not span.excluded]

    log_event("groundedness.done", windows=len(windows), tokens=sum(costs), status=verdict)
    return GroundednessResult(
        verdict=verdict,
        score=score,
        max_span_confidence=max(counted, default=0.0),
        max_token_probability=max(factual_probs, default=0.0),
        unsupported_spans=spans,
        token_scores=tokens,
        windows_run=len(windows),
        threshold=settings.threshold,
        model=detector.info,
    )
