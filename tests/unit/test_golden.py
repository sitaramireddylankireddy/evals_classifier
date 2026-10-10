import json

import pytest

from evalsvc.config import GoldenSettings, InputSettings
from evalsvc.harness.golden import load_golden
from evalsvc.ingest.json_list import InputFileError, JsonListParser
from evalsvc.types import ReasonCode

PARSER = JsonListParser(InputSettings())
SETTINGS = GoldenSettings()


def obj(item_id, **extra):
    base = {"id": item_id, "question": "q", "evidence": "alpha beta.", "answer": "Alpha beta."}
    return base | extra


def write_jsonl(tmp_path, lines):
    path = tmp_path / "golden.jsonl"
    path.write_text(
        "\n".join(line if isinstance(line, str) else json.dumps(line) for line in lines) + "\n",
        encoding="utf-8",
    )
    return path


def test_labels_map_to_failure_or_pass(tmp_path):
    path = write_jsonl(
        tmp_path, [obj("a1", label="grounded"), obj("a2", label="ungrounded", category="cards")]
    )

    load = load_golden(path, PARSER, SETTINGS)

    assert [(g.item.id, g.is_failure, g.category) for g in load.items] == [
        ("a1", False, None),
        ("a2", True, "cards"),
    ]
    assert load.unlabelled == 0
    assert load.issues == []


def test_missing_and_unknown_labels_are_left_out_and_counted(tmp_path):
    path = write_jsonl(
        tmp_path,
        [obj("a1", label="grounded"), obj("a2"), obj("a3", label="maybe"), obj("a4", label=1)],
    )

    load = load_golden(path, PARSER, SETTINGS)

    assert [g.item.id for g in load.items] == ["a1"]
    assert load.unlabelled == 3


def test_malformed_line_is_reported_with_its_position(tmp_path):
    path = write_jsonl(
        tmp_path, [obj("a1", label="grounded"), '{"id": "a2", ', obj("a3", label="ungrounded")]
    )

    load = load_golden(path, PARSER, SETTINGS)

    assert [g.item.id for g in load.items] == ["a1", "a3"]
    assert [(issue.position, issue.reason) for issue in load.issues] == [
        (1, ReasonCode.NOT_AN_OBJECT)
    ]


def test_blank_or_non_text_category_counts_as_no_category(tmp_path):
    path = write_jsonl(
        tmp_path,
        [obj("a1", label="grounded", category="  "), obj("a2", label="grounded", category=7)],
    )

    load = load_golden(path, PARSER, SETTINGS)

    assert [g.category for g in load.items] == [None, None]


def test_key_names_and_label_values_come_from_config(tmp_path):
    settings = GoldenSettings(
        label_key="verdict", failure_value="bad", pass_value="good", category_key="topic"
    )
    path = write_jsonl(
        tmp_path,
        [obj("a1", verdict="bad", topic="loans"), obj("a2", verdict="good"), obj("a3", label="grounded")],
    )

    load = load_golden(path, PARSER, settings)

    assert [(g.item.id, g.is_failure, g.category) for g in load.items] == [
        ("a1", True, "loans"),
        ("a2", False, None),
    ]
    assert load.unlabelled == 1


def test_item_that_is_not_evaluable_is_still_loaded(tmp_path):
    path = write_jsonl(tmp_path, [obj("a1", label="ungrounded", answer="")])

    load = load_golden(path, PARSER, SETTINGS)

    assert load.items[0].item.evaluable is False


def test_missing_file_gives_a_clear_error(tmp_path):
    with pytest.raises(InputFileError):
        load_golden(tmp_path / "absent.jsonl", PARSER, SETTINGS)


def test_synthetic_golden_set_loads(fixtures_dir):
    load = load_golden(fixtures_dir / "golden_synthetic.jsonl", PARSER, SETTINGS)

    assert [g.item.id for g in load.items] == [f"g-{n:02d}" for n in range(1, 11)]
    assert sum(g.is_failure for g in load.items) == 5
    assert {g.category for g in load.items} == {"cards", "loans"}
    assert load.unlabelled == 0
    assert load.issues == []
