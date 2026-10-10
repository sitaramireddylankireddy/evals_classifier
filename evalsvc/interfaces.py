"""Contracts for the parts of the service that can be replaced."""

from typing import Any, Protocol, runtime_checkable

from evalsvc.types import IngestResult


@runtime_checkable
class InputParser(Protocol):
    def parse(self, raw: Any) -> IngestResult: ...


@runtime_checkable
class TokenCounter(Protocol):
    def count(self, text: str) -> int: ...
