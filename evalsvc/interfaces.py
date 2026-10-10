"""Contracts for the parts of the service that can be replaced."""

from collections.abc import Iterator
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from evalsvc.types import (
    CheckResult,
    Chunk,
    EvidenceItem,
    IngestResult,
    JudgeRequest,
    JudgeResponse,
    ModelInfo,
    Sentence,
    Span,
    SpanExplanation,
    TokenScore,
)

if TYPE_CHECKING:
    from evalsvc.records import ResultRecord


@runtime_checkable
class LargeJudge(Protocol):
    """The existing large judge. Only a stand-in lives in this service."""

    def judge(self, request: JudgeRequest) -> JudgeResponse: ...


@runtime_checkable
class ResultStore(Protocol):
    def write(self, record: "ResultRecord") -> None: ...

    def get_current(self, item_id: str) -> "ResultRecord | None": ...

    def iter_current(self) -> "Iterator[ResultRecord]": ...


@runtime_checkable
class DeterministicChecks(Protocol):
    """Rule-based checks on amounts, dates, percentages, and references (feature 004)."""

    def run(self, answer: str, evidence: list[EvidenceItem]) -> list[CheckResult]: ...


@runtime_checkable
class ReasonGenerator(Protocol):
    """Explains a flagged span (feature 005)."""

    def explain(
        self, span: Span, answer: str, sentences: list[Sentence], chunks: list[Chunk]
    ) -> SpanExplanation: ...


@runtime_checkable
class InputParser(Protocol):
    def parse(self, raw: Any) -> IngestResult: ...


@runtime_checkable
class TokenCounter(Protocol):
    def count(self, text: str) -> int: ...


class DetectorInputError(Exception):
    """The detector was given more text than it can read in one pass."""


@runtime_checkable
class Detector(Protocol):
    info: ModelInfo
    max_tokens: int  # most tokens the detector reads in one pass

    def count_tokens(self, text: str) -> int: ...

    def fixed_cost(self, question: str, answer: str) -> int:
        """Tokens used by everything except the passages: question, answer, and prompt wording."""
        ...

    def passage_cost(self, text: str) -> int:
        """Tokens one passage adds to the input, including any wrapper around it."""
        ...

    def score_batch(
        self, contexts: list[list[str]], question: str, answer: str
    ) -> list[list[TokenScore]]:
        """Score the answer once per window of passages.

        Returns one list per window. Every list covers the same answer tokens
        in the same order. Raises DetectorInputError when a window does not fit.
        """
        ...
