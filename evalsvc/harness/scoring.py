"""Run the detector once per golden item and keep a score that works for any threshold."""

import logging
import time

from evalsvc.evaluators.groundedness import evaluate_groundedness
from evalsvc.harness.golden import GoldenItem
from evalsvc.pipeline import Components
from evalsvc.safelog import log_event
from evalsvc.text.chunking import chunk_evidence
from evalsvc.text.sentences import split_answer
from evalsvc.types import FrozenModel


class ScoredItem(FrozenModel):
    item_id: str
    is_failure: bool
    category: str | None = None
    evaluable: bool
    not_evaluable_reason: str | None = None
    # Highest token probability inside factual sentences. The verdict at any
    # threshold t is "fail" exactly when score > t, so no second detector run is needed.
    score: float | None = None
    seconds: float | None = None  # time spent in detection


def score_items(golden: list[GoldenItem], c: Components) -> list[ScoredItem]:
    scored: list[ScoredItem] = []
    for entry in golden:
        item = entry.item
        common = {"item_id": item.id, "is_failure": entry.is_failure, "category": entry.category}

        if not item.evaluable:
            scored.append(
                ScoredItem(
                    **common, evaluable=False, not_evaluable_reason=str(item.not_evaluable_reason)
                )
            )
            continue

        try:
            chunks = chunk_evidence(item.evidence, c.counter, c.nlp, c.settings.chunking)
            sentences = split_answer(item.answer, c.nlp, c.settings.sentences, c.settings.checks)
            started = time.perf_counter()
            result = evaluate_groundedness(
                item.question, chunks, item.answer, sentences, c.detector, c.detection
            )
            seconds = time.perf_counter() - started
        except Exception:
            # The exception text may quote the item, so it is not logged.
            log_event("golden.item_failed", level=logging.ERROR, item_id=item.id)
            scored.append(
                ScoredItem(**common, evaluable=False, not_evaluable_reason="evaluation_failed")
            )
            continue

        if not result.evaluable:
            scored.append(
                ScoredItem(
                    **common, evaluable=False, not_evaluable_reason=result.not_evaluable_reason
                )
            )
        else:
            scored.append(
                ScoredItem(
                    **common,
                    evaluable=True,
                    score=result.max_token_probability,
                    seconds=seconds,
                )
            )
    return scored
