"""Contracts for the parts of the service that can be replaced."""

from typing import Any, Protocol, runtime_checkable

from evalsvc.types import IngestResult, ModelInfo, TokenScore


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
