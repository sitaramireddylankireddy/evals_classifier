from pathlib import Path

import pytest

from evalsvc.config import ConfigError, InputSettings, Settings, load_settings

REPO_ROOT = Path(__file__).resolve().parents[2]


def write_config(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "config.toml"
    path.write_text(text, encoding="utf-8")
    return path


def test_defaults_apply_when_input_section_is_absent(tmp_path):
    settings = load_settings(write_config(tmp_path, ""))

    assert settings == Settings()
    assert settings.input == InputSettings(
        parser="json_list",
        key_id="id",
        key_question="question",
        key_evidence="evidence",
        key_answer="answer",
    )


def test_file_values_override_defaults(tmp_path):
    path = write_config(tmp_path, '[input]\nkey_id = "uid"\nkey_answer = "response"\n')

    settings = load_settings(path)

    assert settings.input.key_id == "uid"
    assert settings.input.key_answer == "response"
    assert settings.input.key_question == "question"


def test_example_config_matches_the_defaults():
    assert load_settings(REPO_ROOT / "config.example.toml") == Settings()


def test_unknown_key_gives_a_clear_error(tmp_path):
    path = write_config(tmp_path, '[input]\nkey_identifier = "uid"\n')

    with pytest.raises(ConfigError, match="input.key_identifier"):
        load_settings(path)


def test_unknown_section_gives_a_clear_error(tmp_path):
    path = write_config(tmp_path, "[unexpected]\nvalue = 1\n")

    with pytest.raises(ConfigError, match="unexpected"):
        load_settings(path)


def test_wrong_value_type_gives_a_clear_error(tmp_path):
    path = write_config(tmp_path, "[input]\nkey_id = 5\n")

    with pytest.raises(ConfigError, match="input.key_id"):
        load_settings(path)


def test_missing_file_gives_a_clear_error(tmp_path):
    with pytest.raises(ConfigError, match="not found"):
        load_settings(tmp_path / "absent.toml")


def test_invalid_toml_gives_a_clear_error(tmp_path):
    path = write_config(tmp_path, "[input\nkey_id = ")

    with pytest.raises(ConfigError, match="not valid TOML"):
        load_settings(path)


# --- Text preparation settings (feature 002) ---


def test_text_preparation_defaults():
    settings = Settings()

    assert settings.chunking.min_tokens == 300
    assert settings.chunking.max_tokens == 500
    assert len(settings.chunking.heading_patterns) == 4
    assert settings.sentences.spacy_pipeline == "blank_en"
    assert [rule.name for rule in settings.sentences.non_factual_rules] == [
        "apology",
        "empathy",
        "thanks",
        "next_step",
    ]
    assert settings.checks.currencies == ["GBP"]
    assert len(settings.checks.reference_patterns) == 1


def test_chunk_sizes_can_be_set(tmp_path):
    path = write_config(tmp_path, "[chunking]\nmin_tokens = 100\nmax_tokens = 200\n")

    settings = load_settings(path)

    assert (settings.chunking.min_tokens, settings.chunking.max_tokens) == (100, 200)


def test_min_tokens_above_max_tokens_is_rejected(tmp_path):
    path = write_config(tmp_path, "[chunking]\nmin_tokens = 600\nmax_tokens = 500\n")

    with pytest.raises(ConfigError, match="min_tokens"):
        load_settings(path)


def test_rule_list_in_the_file_replaces_the_defaults(tmp_path):
    path = write_config(
        tmp_path,
        "[[sentences.non_factual_rules]]\nname = \"greeting\"\npattern = '(?i)^hello\\b'\n",
    )

    settings = load_settings(path)

    assert [(rule.name, rule.pattern) for rule in settings.sentences.non_factual_rules] == [
        ("greeting", r"(?i)^hello\b")
    ]


def test_rule_with_an_invalid_pattern_gives_a_clear_error(tmp_path):
    path = write_config(
        tmp_path,
        "[[sentences.non_factual_rules]]\nname = \"broken\"\npattern = '(unclosed'\n",
    )

    with pytest.raises(ConfigError, match="invalid regular expression"):
        load_settings(path)


def test_invalid_heading_pattern_gives_a_clear_error(tmp_path):
    path = write_config(tmp_path, "[chunking]\nheading_patterns = ['[a-']\n")

    with pytest.raises(ConfigError, match="chunking.heading_patterns"):
        load_settings(path)
