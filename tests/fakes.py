"""Stand-ins for the parts of the service that need a model or an outside system."""

import re

from evalsvc.interfaces import DetectorInputError
from evalsvc.types import ModelInfo, TokenScore

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

    def __init__(self, max_tokens: int = 8192, reject_input: bool = False) -> None:
        self.info = ModelInfo(name="fake-detector", revision="test")
        self.max_tokens = max_tokens
        self.reject_input = reject_input
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
