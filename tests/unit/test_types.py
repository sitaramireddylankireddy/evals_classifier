import pytest
from pydantic import ValidationError

from evalsvc.types import EvidenceItem, IngestIssue, IngestResult, Item, ReasonCode


def make_item(**overrides):
    values = {
        "id": "a1",
        "question": "What is the limit?",
        "evidence": [EvidenceItem(index=0, text="The limit is £500.")],
        "answer": "The limit is £500.",
    }
    values.update(overrides)
    return Item(**values)


def test_reason_code_has_the_eight_codes():
    assert {code.value for code in ReasonCode} == {
        "not_a_list",
        "not_an_object",
        "missing_id",
        "duplicate_id",
        "missing_field",
        "wrong_type",
        "empty_answer",
        "empty_evidence",
    }


def test_item_defaults_to_evaluable_with_no_metadata():
    item = make_item()

    assert item.evaluable is True
    assert item.not_evaluable_reason is None
    assert item.metadata == {}


def test_item_can_be_marked_not_evaluable():
    item = make_item(evaluable=False, not_evaluable_reason=ReasonCode.EMPTY_ANSWER)

    assert item.evaluable is False
    assert item.not_evaluable_reason is ReasonCode.EMPTY_ANSWER


def test_ingest_result_holds_items_and_issues():
    issue = IngestIssue(position=2, item_id="a2", reason=ReasonCode.MISSING_FIELD, field="answer")
    result = IngestResult(items=[make_item()], issues=[issue])

    assert result.items[0].id == "a1"
    assert result.issues[0].position == 2
    assert result.issues[0].field == "answer"


def test_issue_for_whole_input_has_no_position():
    issue = IngestIssue(position=None, reason=ReasonCode.NOT_A_LIST)

    assert issue.position is None
    assert issue.item_id is None
    assert issue.field is None


def test_models_cannot_be_changed_after_creation():
    item = make_item()
    evidence = EvidenceItem(index=0, text="text")
    issue = IngestIssue(position=0, reason=ReasonCode.MISSING_ID)
    result = IngestResult(items=[], issues=[])

    with pytest.raises(ValidationError):
        item.answer = "changed"
    with pytest.raises(ValidationError):
        evidence.text = "changed"
    with pytest.raises(ValidationError):
        issue.position = 1
    with pytest.raises(ValidationError):
        result.items = [item]


def test_unknown_fields_are_rejected():
    with pytest.raises(ValidationError):
        EvidenceItem(index=0, text="text", source="unexpected")
