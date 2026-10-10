"""Data types shared across the service."""

from enum import StrEnum
from typing import Any

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
