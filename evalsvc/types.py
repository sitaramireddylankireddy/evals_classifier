"""Data types shared across the service."""

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class FrozenModel(BaseModel):
    """Base for all data types: read-only once built, and no unknown fields."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class ReasonCode(StrEnum):
    NOT_A_LIST = "not_a_list"
    NOT_AN_OBJECT = "not_an_object"
    MISSING_ID = "missing_id"
    DUPLICATE_ID = "duplicate_id"
    MISSING_FIELD = "missing_field"
    WRONG_TYPE = "wrong_type"
    EMPTY_ANSWER = "empty_answer"
    EMPTY_EVIDENCE = "empty_evidence"


class EvidenceItem(FrozenModel):
    index: int
    text: str


class Item(FrozenModel):
    id: str
    question: str
    evidence: list[EvidenceItem]
    answer: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    evaluable: bool = True
    not_evaluable_reason: ReasonCode | None = None


class IngestIssue(FrozenModel):
    """A problem found while reading input. Holds no field values, only where and why."""

    position: int | None  # index of the object in the list; None when the input is not a list
    item_id: str | None = None
    reason: ReasonCode
    field: str | None = None  # key name only


class IngestResult(FrozenModel):
    items: list[Item]
    issues: list[IngestIssue]


class Chunk(FrozenModel):
    chunk_id: str
    evidence_index: int
    start: int  # character range in the evidence item
    end: int
    text: str
    heading: str | None = None  # heading of the section the chunk starts in
    token_count: int

    @property
    def context_text(self) -> str:
        """The text given to the detector: the chunk with its section heading in front."""
        if self.heading is None or self.text.lstrip().startswith(self.heading):
            return self.text
        return f"{self.heading}\n{self.text}"


class Sentence(FrozenModel):
    index: int
    start: int  # character range in the answer
    end: int
    text: str
    factual: bool = True
    matched_rule: str | None = None  # name of the non-factual rule that matched


class Match(FrozenModel):
    """A value found in text by one of the pattern finders."""

    start: int
    end: int
    text: str
    kind: str  # "amount", "date", "percentage", or "reference"


class TokenScore(FrozenModel):
    start: int  # character range in the answer
    end: int
    prob: float  # probability that the token is not supported by the evidence


class Span(FrozenModel):
    start: int  # character range in the answer
    end: int
    text: str
    confidence: float  # highest token probability in the span
    excluded: bool = False  # touches no factual sentence, so it is left out of scoring


class ModelInfo(FrozenModel):
    name: str
    revision: str
    device: str | None = None  # "cpu" or "cuda"


class GroundednessResult(FrozenModel):
    evaluable: bool = True
    not_evaluable_reason: str | None = None
    verdict: Literal["pass", "fail"] | None = None
    score: float | None = None  # None when the answer has no factual sentences
    max_span_confidence: float = 0.0
    max_token_probability: float = 0.0  # over factual sentences, independent of the threshold
    unsupported_spans: list[Span] = Field(default_factory=list)
    token_scores: list[TokenScore] = Field(default_factory=list)  # after combining windows
    windows_run: int = 0
    threshold: float
    model: ModelInfo
