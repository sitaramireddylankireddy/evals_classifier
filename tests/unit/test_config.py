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
