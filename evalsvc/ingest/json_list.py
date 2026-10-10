"""Parser for the project-owned input format: a list of JSON objects."""

import json
from pathlib import Path
from typing import Any

from evalsvc.config import ConfigError, InputSettings, Settings
from evalsvc.interfaces import InputParser
from evalsvc.safelog import log_event
from evalsvc.types import EvidenceItem, IngestIssue, IngestResult, Item, ReasonCode


class InputFileError(Exception):
    """The input file cannot be read or is not valid JSON."""


class JsonListParser:
    def __init__(self, keys: InputSettings) -> None:
        self._keys = keys

    def parse(self, raw: Any) -> IngestResult:
        if not isinstance(raw, list):
            issue = IngestIssue(position=None, reason=ReasonCode.NOT_A_LIST)
            _log_issue(issue)
            return IngestResult(items=[], issues=[issue])

        items: list[Item] = []
        issues: list[IngestIssue] = []
        seen_ids: set[str] = set()

        for position, obj in enumerate(raw):
            outcome = self._parse_object(position, obj, seen_ids)
            if isinstance(outcome, IngestIssue):
                issues.append(outcome)
                _log_issue(outcome)
                continue
            items.append(outcome)
            seen_ids.add(outcome.id)
            if not outcome.evaluable:
                log_event(
                    "ingest.not_evaluable",
                    item_id=outcome.id,
                    position=position,
                    reason=outcome.not_evaluable_reason,
                )

        log_event("ingest.done", items=len(items), issues=len(issues))
        return IngestResult(items=items, issues=issues)

    def _parse_object(self, position: int, obj: Any, seen_ids: set[str]) -> Item | IngestIssue:
        keys = self._keys

        def issue(
            reason: ReasonCode, item_id: str | None = None, field: str | None = None
        ) -> IngestIssue:
            return IngestIssue(position=position, item_id=item_id, reason=reason, field=field)

        if not isinstance(obj, dict):
            return issue(ReasonCode.NOT_AN_OBJECT)

        raw_id = obj.get(keys.key_id)
        if raw_id is None or (isinstance(raw_id, str) and not raw_id.strip()):
            return issue(ReasonCode.MISSING_ID)
        # bool is a subclass of int, so it has to be ruled out by name
        if isinstance(raw_id, bool) or not isinstance(raw_id, (str, int)):
            return issue(ReasonCode.WRONG_TYPE, field=keys.key_id)
        item_id = str(raw_id)

        if item_id in seen_ids:
            return issue(ReasonCode.DUPLICATE_ID, item_id)

        for key in (keys.key_question, keys.key_evidence, keys.key_answer):
            if key not in obj:
                return issue(ReasonCode.MISSING_FIELD, item_id, key)

        question = obj[keys.key_question]
        evidence = obj[keys.key_evidence]
        answer = obj[keys.key_answer]

        if not isinstance(question, str):
            return issue(ReasonCode.WRONG_TYPE, item_id, keys.key_question)
        if isinstance(evidence, str):
            passages = [evidence]
        elif isinstance(evidence, list) and all(isinstance(p, str) for p in evidence):
            passages = evidence
        else:
            return issue(ReasonCode.WRONG_TYPE, item_id, keys.key_evidence)
        if not isinstance(answer, str):
            return issue(ReasonCode.WRONG_TYPE, item_id, keys.key_answer)

        reason = None
        if not answer.strip():
            reason = ReasonCode.EMPTY_ANSWER
        elif not any(passage.strip() for passage in passages):
            reason = ReasonCode.EMPTY_EVIDENCE

        known_keys = {keys.key_id, keys.key_question, keys.key_evidence, keys.key_answer}
        return Item(
            id=item_id,
            question=question,
            evidence=[EvidenceItem(index=i, text=text) for i, text in enumerate(passages)],
            answer=answer,
            metadata={key: value for key, value in obj.items() if key not in known_keys},
            evaluable=reason is None,
            not_evaluable_reason=reason,
        )


def _log_issue(issue: IngestIssue) -> None:
    log_event(
        "ingest.skipped",
        position=issue.position,
        item_id=issue.item_id,
        reason=issue.reason,
        field=issue.field,
    )


def load_json_file(path: Path) -> Any:
    """Read a .json file holding an array, or a .jsonl file with one object per line."""
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError:
        raise InputFileError(f"Cannot read input file: {path}") from None

    if path.suffix.lower() == ".jsonl":
        # Split on "\n" only: str.splitlines also breaks on characters that
        # are legal inside a JSON string.
        return [_decode_line(line) for line in text.split("\n") if line.strip()]

    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        # The original exception carries the file content, so it is not chained.
        raise InputFileError(
            f"Input file is not valid JSON: {path} (line {exc.lineno}, column {exc.colno})"
        ) from None


def _decode_line(line: str) -> Any:
    try:
        return json.loads(line)
    except json.JSONDecodeError:
        # Kept as a placeholder so the parser reports it as NOT_AN_OBJECT
        # at the right position.
        return None


_PARSERS = {"json_list": JsonListParser}


def build_parser(settings: Settings) -> InputParser:
    try:
        factory = _PARSERS[settings.input.parser]
    except KeyError:
        known = ", ".join(sorted(_PARSERS))
        raise ConfigError(
            f"Unknown input parser '{settings.input.parser}'. Known parsers: {known}"
        ) from None
    return factory(settings.input)
