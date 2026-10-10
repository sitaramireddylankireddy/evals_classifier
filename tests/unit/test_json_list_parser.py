import json
import logging

import pytest

from evalsvc.config import ConfigError, InputSettings, Settings, load_settings
from evalsvc.ingest.json_list import InputFileError, JsonListParser, build_parser, load_json_file
from evalsvc.interfaces import InputParser
from evalsvc.types import ReasonCode


@pytest.fixture
def parser() -> JsonListParser:
    return JsonListParser(InputSettings())


def make_object(**overrides):
    obj = {
        "id": "a1",
        "question": "What is the limit?",
        "evidence": ["The limit is £500."],
        "answer": "The limit is £500.",
    }
    obj.update(overrides)
    return obj


def without(key):
    obj = make_object()
    del obj[key]
    return obj


# --- User Story 1: read a list of items (T008) ---


def test_parser_satisfies_the_protocol(parser):
    assert isinstance(parser, InputParser)


def test_one_object_gives_one_item(parser):
    result = parser.parse([make_object()])

    assert result.issues == []
    assert len(result.items) == 1
    item = result.items[0]
    assert item.id == "a1"
    assert item.question == "What is the limit?"
    assert [e.text for e in item.evidence] == ["The limit is £500."]
    assert item.answer == "The limit is £500."
    assert item.evaluable is True


def test_many_objects_keep_their_order(parser):
    raw = [make_object(id=f"a{n}") for n in range(1, 6)]

    result = parser.parse(raw)

    assert [item.id for item in result.items] == ["a1", "a2", "a3", "a4", "a5"]


def test_evidence_given_as_text_becomes_one_evidence_item(parser):
    result = parser.parse([make_object(evidence="The limit is £500.")])

    evidence = result.items[0].evidence
    assert len(evidence) == 1
    assert evidence[0].index == 0
    assert evidence[0].text == "The limit is £500."


def test_evidence_given_as_a_list_keeps_each_passage_in_order(parser):
    result = parser.parse([make_object(evidence=["First passage.", "Second passage."])])

    evidence = result.items[0].evidence
    assert [(e.index, e.text) for e in evidence] == [(0, "First passage."), (1, "Second passage.")]


def test_repeated_passages_are_both_kept(parser):
    result = parser.parse([make_object(evidence=["Same passage.", "Same passage."])])

    assert len(result.items[0].evidence) == 2


def test_extra_keys_are_stored_as_metadata(parser):
    result = parser.parse([make_object(category="cards", source={"app": "helpdesk"})])

    assert result.issues == []
    assert result.items[0].metadata == {"category": "cards", "source": {"app": "helpdesk"}}


def test_integer_id_is_stored_as_text(parser):
    result = parser.parse([make_object(id=42)])

    assert result.items[0].id == "42"


def test_empty_list_gives_no_items_and_no_issues(parser):
    result = parser.parse([])

    assert result.items == []
    assert result.issues == []


def test_valid_fixture_file(parser, fixtures_dir):
    result = parser.parse(load_json_file(fixtures_dir / "items_valid.json"))

    assert result.issues == []
    assert [item.id for item in result.items] == ["item-001", "item-002", "item-003"]
    assert [len(item.evidence) for item in result.items] == [2, 1, 1]
    assert result.items[2].metadata == {"category": "cards"}


# --- Text is preserved (T009) ---


@pytest.mark.parametrize(
    "text",
    [
        "  leading and trailing spaces  ",
        "\tTabbed\ttext\t",
        "Line one\n\nLine two\r\nLine three\n",
        "Café fee of £1,250.00 — paid in €",
        "Repeated    spaces   inside",
    ],
)
def test_answer_and_evidence_text_are_unchanged(parser, text):
    result = parser.parse([make_object(answer=text, evidence=[text, text + " "])])

    item = result.items[0]
    assert item.answer == text
    assert item.evidence[0].text == text
    assert item.evidence[1].text == text + " "


def test_evidence_text_given_as_one_string_is_unchanged(parser):
    text = "  Section 4.2\n\nThe limit is £500.  \n"

    result = parser.parse([make_object(evidence=text)])

    assert result.items[0].evidence[0].text == text


# --- User Story 2: survive bad input (T010) ---


@pytest.mark.parametrize("raw", [make_object(), "some text", None, 5])
def test_input_that_is_not_a_list_is_reported(parser, raw):
    result = parser.parse(raw)

    assert result.items == []
    assert len(result.issues) == 1
    assert result.issues[0].reason is ReasonCode.NOT_A_LIST
    assert result.issues[0].position is None


@pytest.mark.parametrize("entry", ["some text", 5, None, ["nested"]])
def test_entry_that_is_not_an_object_is_reported(parser, entry):
    result = parser.parse([entry])

    assert result.items == []
    assert result.issues[0].reason is ReasonCode.NOT_AN_OBJECT
    assert result.issues[0].position == 0


@pytest.mark.parametrize(
    "obj",
    [without("id"), make_object(id=None), make_object(id=""), make_object(id="   ")],
)
def test_missing_or_empty_id_is_reported(parser, obj):
    result = parser.parse([obj])

    assert result.items == []
    assert result.issues[0].reason is ReasonCode.MISSING_ID
    assert result.issues[0].position == 0
    assert result.issues[0].item_id is None


def test_duplicate_id_is_reported_and_the_first_is_kept(parser):
    raw = [make_object(answer="First answer."), make_object(answer="Second answer.")]

    result = parser.parse(raw)

    assert len(result.items) == 1
    assert result.items[0].answer == "First answer."
    assert len(result.issues) == 1
    assert result.issues[0].reason is ReasonCode.DUPLICATE_ID
    assert result.issues[0].position == 1
    assert result.issues[0].item_id == "a1"


def test_id_can_be_used_again_after_an_object_that_was_skipped(parser):
    raw = [without("answer"), make_object()]

    result = parser.parse(raw)

    assert [item.id for item in result.items] == ["a1"]
    assert [issue.reason for issue in result.issues] == [ReasonCode.MISSING_FIELD]


@pytest.mark.parametrize("key", ["question", "evidence", "answer"])
def test_missing_field_is_reported_with_its_key_name(parser, key):
    result = parser.parse([without(key)])

    assert result.items == []
    issue = result.issues[0]
    assert issue.reason is ReasonCode.MISSING_FIELD
    assert issue.field == key
    assert issue.item_id == "a1"
    assert issue.position == 0


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("id", 1.5),
        ("id", True),
        ("id", ["a1"]),
        ("question", None),
        ("question", 7),
        ("evidence", 5),
        ("evidence", None),
        ("evidence", ["A passage.", 5]),
        ("evidence", {"text": "A passage."}),
        ("answer", 123),
        ("answer", None),
        ("answer", ["The limit is £500."]),
    ],
)
def test_wrong_type_is_reported_with_its_key_name(parser, key, value):
    result = parser.parse([make_object(**{key: value})])

    assert result.items == []
    issue = result.issues[0]
    assert issue.reason is ReasonCode.WRONG_TYPE
    assert issue.field == key
    assert issue.position == 0


def test_bad_object_does_not_affect_its_neighbours(parser):
    raw = [make_object(id="a1"), without("id"), make_object(id="a3")]

    result = parser.parse(raw)

    assert [item.id for item in result.items] == ["a1", "a3"]
    assert [(issue.position, issue.reason) for issue in result.issues] == [
        (1, ReasonCode.MISSING_ID)
    ]


def test_bad_fixture_file(parser, fixtures_dir):
    result = parser.parse(load_json_file(fixtures_dir / "items_bad.json"))

    assert [item.id for item in result.items] == ["bad-001", "bad-006", "bad-007", "bad-008"]
    assert [(issue.position, issue.reason, issue.field) for issue in result.issues] == [
        (1, ReasonCode.NOT_AN_OBJECT, None),
        (2, ReasonCode.MISSING_ID, None),
        (3, ReasonCode.DUPLICATE_ID, None),
        (4, ReasonCode.MISSING_FIELD, "answer"),
        (5, ReasonCode.WRONG_TYPE, "evidence"),
    ]
    assert [(item.id, item.not_evaluable_reason) for item in result.items if not item.evaluable] == [
        ("bad-006", ReasonCode.EMPTY_ANSWER),
        ("bad-007", ReasonCode.EMPTY_EVIDENCE),
    ]


# --- Not-evaluable items (T011) ---


@pytest.mark.parametrize("answer", ["", "   ", "\n\t "])
def test_empty_answer_gives_a_not_evaluable_item(parser, answer):
    result = parser.parse([make_object(answer=answer)])

    assert result.issues == []
    item = result.items[0]
    assert item.evaluable is False
    assert item.not_evaluable_reason is ReasonCode.EMPTY_ANSWER
    assert item.answer == answer


@pytest.mark.parametrize("evidence", ["", "  ", [], ["", "  \n"]])
def test_empty_evidence_gives_a_not_evaluable_item(parser, evidence):
    result = parser.parse([make_object(evidence=evidence)])

    assert result.issues == []
    item = result.items[0]
    assert item.evaluable is False
    assert item.not_evaluable_reason is ReasonCode.EMPTY_EVIDENCE


def test_empty_question_stays_evaluable(parser):
    result = parser.parse([make_object(question="")])

    assert result.issues == []
    assert result.items[0].evaluable is True
    assert result.items[0].question == ""


# --- No customer text in logs (T012) ---


def test_no_customer_text_in_logs_or_issues(parser, fixtures_dir, sentinel, caplog):
    caplog.set_level(logging.DEBUG)
    raw = load_json_file(fixtures_dir / "items_bad.json")
    assert sentinel in json.dumps(raw)

    result = parser.parse(raw)

    assert caplog.records
    assert sentinel not in caplog.text
    assert all(sentinel not in record.getMessage() for record in caplog.records)
    assert all(sentinel not in issue.model_dump_json() for issue in result.issues)


def test_input_that_is_not_a_list_logs_no_customer_text(parser, sentinel, caplog):
    caplog.set_level(logging.DEBUG)

    parser.parse(f"{sentinel} a text value where a list was expected")

    assert caplog.records
    assert sentinel not in caplog.text


# --- User Story 3: file loading and parser selection (T013) ---


def test_json_and_jsonl_files_give_equal_items(parser, fixtures_dir):
    from_json = parser.parse(load_json_file(fixtures_dir / "items_valid.json"))
    from_jsonl = parser.parse(load_json_file(fixtures_dir / "items.jsonl"))

    assert from_jsonl.issues == []
    assert from_jsonl.items == from_json.items


def test_malformed_jsonl_line_is_reported_at_its_position(parser, tmp_path):
    lines = [
        json.dumps(make_object(id="a1")),
        '{"id": "a2", "question": ',
        "",
        json.dumps(make_object(id="a3")),
    ]
    path = tmp_path / "items.jsonl"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    result = parser.parse(load_json_file(path))

    assert [item.id for item in result.items] == ["a1", "a3"]
    assert [(issue.position, issue.reason) for issue in result.issues] == [
        (1, ReasonCode.NOT_AN_OBJECT)
    ]


def test_invalid_json_file_gives_an_error_without_its_content(tmp_path, sentinel):
    path = tmp_path / "items.json"
    path.write_text(f'[{{"id": "a1", "answer": "{sentinel} unfinished', encoding="utf-8")

    with pytest.raises(InputFileError, match="not valid JSON") as error:
        load_json_file(path)

    assert sentinel not in str(error.value)
    assert error.value.__cause__ is None


def test_missing_input_file_gives_a_clear_error(tmp_path):
    with pytest.raises(InputFileError, match="Cannot read"):
        load_json_file(tmp_path / "absent.json")


def test_file_with_a_byte_order_mark_is_read(parser, tmp_path):
    path = tmp_path / "items.json"
    path.write_text(json.dumps([make_object()]), encoding="utf-8-sig")

    result = parser.parse(load_json_file(path))

    assert [item.id for item in result.items] == ["a1"]


def test_build_parser_returns_the_json_list_parser_by_default():
    parser = build_parser(Settings())

    assert isinstance(parser, JsonListParser)
    assert isinstance(parser, InputParser)


def test_key_names_from_config_are_used(tmp_path):
    config = tmp_path / "config.toml"
    config.write_text(
        '[input]\nkey_id = "uid"\nkey_question = "q"\nkey_evidence = "context"\nkey_answer = "response"\n',
        encoding="utf-8",
    )
    parser = build_parser(load_settings(config))
    raw = [{"uid": "a1", "q": "What is the limit?", "context": "The limit is £500.", "response": "It is £500.", "id": "kept"}]

    result = parser.parse(raw)

    assert result.issues == []
    item = result.items[0]
    assert item.id == "a1"
    assert item.question == "What is the limit?"
    assert item.evidence[0].text == "The limit is £500."
    assert item.answer == "It is £500."
    assert item.metadata == {"id": "kept"}


def test_unknown_parser_name_gives_a_clear_error():
    settings = Settings(input=InputSettings(parser="xml_feed"))

    with pytest.raises(ConfigError, match="xml_feed"):
        build_parser(settings)
