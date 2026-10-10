"""Stand-ins for the parts of the service that need a model or an outside system."""

import re
import time
from pathlib import Path
from typing import Any

from evalsvc.config import JudgeSettings, RunSettings, Settings, StoreSettings
from evalsvc.interfaces import DetectorInputError
from evalsvc.judge import StubLargeJudge
from evalsvc.pipeline import Components, build_components
from evalsvc.types import (
    CheckResult,
    Chunk,
    EvidenceItem,
    Item,
    JudgeRequest,
    JudgeResponse,
    ModelInfo,
    Sentence,
    Span,
    SpanExplanation,
    TokenScore,
)

SUPPORTED_PROB = 0.05
UNSUPPORTED_PROB = 0.95

_WORD = re.compile(r"\S+")
_PUNCTUATION = ".,;:!?()\"'"


def _normalise(word: str) -> str:
    return word.strip(_PUNCTUATION).lower()


class FakeDetector:
    """Scores an answer word as supported when the same word appears in the window's passages.

    Tokens are whitespace-separated words. Every call is recorded in `calls`.
    """

    def __init__(
        self, max_tokens: int = 8192, reject_input: bool = False, fail_on: str | None = None
    ) -> None:
        self.info = ModelInfo(name="fake-detector", revision="test")
        self.max_tokens = max_tokens
        self.reject_input = reject_input
        self.fail_on = fail_on  # an answer containing this text makes the detector crash
        self.calls: list[list[list[str]]] = []

    def count_tokens(self, text: str) -> int:
        return len(text.split())

    def fixed_cost(self, question: str, answer: str) -> int:
        return self.count_tokens(question) + self.count_tokens(answer)

    def passage_cost(self, text: str) -> int:
        return self.count_tokens(text)

    def score_batch(
        self, contexts: list[list[str]], question: str, answer: str
    ) -> list[list[TokenScore]]:
        self.calls.append(contexts)
        if self.reject_input:
            raise DetectorInputError("input too long")
        if self.fail_on is not None and self.fail_on in answer:
            # The message quotes the answer on purpose: tests check it never reaches the logs.
            raise RuntimeError(f"detector crashed on: {answer}")
        return [self._score(passages, answer) for passages in contexts]

    def _score(self, passages: list[str], answer: str) -> list[TokenScore]:
        known = {_normalise(word) for passage in passages for word in passage.split()}
        return [
            TokenScore(
                start=match.start(),
                end=match.end(),
                prob=SUPPORTED_PROB if _normalise(match.group()) in known else UNSUPPORTED_PROB,
            )
            for match in _WORD.finditer(answer)
        ]


class FakeChecks:
    """Stand-in for the deterministic checks stage."""

    def run(self, answer: str, evidence: list[EvidenceItem]) -> list[CheckResult]:
        return [CheckResult(check="fake_check", passed=True)]


class FakeReasons:
    """Stand-in for the explanation stage."""

    def explain(
        self, span: Span, answer: str, sentences: list[Sentence], chunks: list[Chunk]
    ) -> SpanExplanation:
        return SpanExplanation(
            reason_type="fake_reason",
            reason=f"No support found for {len(span.text)} characters.",
            nearest_chunk_id=chunks[0].chunk_id,
        )


class RaisingJudge:
    def __init__(self) -> None:
        self.calls = 0

    def judge(self, request: JudgeRequest) -> JudgeResponse:
        self.calls += 1
        # The message quotes the answer on purpose: tests check it never reaches the logs.
        raise RuntimeError(f"judge crashed on: {request.answer}")


class SlowJudge:
    def __init__(self, seconds: float) -> None:
        self.seconds = seconds

    def judge(self, request: JudgeRequest) -> JudgeResponse:
        time.sleep(self.seconds)
        return JudgeResponse(verdict="late", rationale="too late")


EVIDENCE = "alpha beta gamma delta epsilon."
SUPPORTED_ANSWER = "Alpha beta gamma."
UNSUPPORTED_ANSWER = "Alpha unicorn gamma."


def make_item(
    item_id: str = "a1",
    answer: str = SUPPORTED_ANSWER,
    evidence: tuple[str, ...] = (EVIDENCE,),
    question: str = "alpha question",
    **fields: Any,
) -> Item:
    return Item(
        id=item_id,
        question=question,
        evidence=[EvidenceItem(index=i, text=text) for i, text in enumerate(evidence)],
        answer=answer,
        **fields,
    )


def make_components(
    tmp_path: Path,
    *,
    detector: Any = None,
    judge: Any = None,
    sample_rate: float = 0.0,
    timeout_seconds: float = 60.0,
    **slots: Any,
) -> Components:
    """Components built on stand-ins, with the store in a temporary folder."""
    settings = Settings(
        run=RunSettings(sample_rate=sample_rate),
        store=StoreSettings(path=str(tmp_path / "store")),
        judge=JudgeSettings(timeout_seconds=timeout_seconds),
    )
    return build_components(
        settings,
        detector=detector if detector is not None else FakeDetector(),
        judge=judge if judge is not None else StubLargeJudge(),
        **slots,
    )
