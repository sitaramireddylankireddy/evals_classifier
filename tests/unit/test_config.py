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


# --- Model and detection settings (feature 003) ---


def test_model_and_detection_defaults():
    settings = Settings()

    assert settings.model.select == "auto"
    assert settings.model.large.name == "lettucedect-large-modernbert-en-v1"
    assert settings.model.base.name == "lettucedect-base-modernbert-en-v1"
    assert (settings.model.large.path, settings.model.large.revision) == ("", "")
    assert (settings.model.base.path, settings.model.base.revision) == ("", "")
    assert settings.model.large.threshold is None
    assert settings.model.base.threshold is None
    assert settings.model.device == "auto"
    assert settings.model.batch_size == 4
    assert settings.model.max_tokens == 4096
    assert settings.detection.threshold == 0.5
    assert settings.detection.window_evidence_tokens == 6000
    assert settings.detection.window_overlap_tokens == 500
    assert settings.detection.safety_margin_tokens == 32


def test_both_models_can_be_set_in_the_file(tmp_path):
    path = write_config(
        tmp_path,
        '[model]\nselect = "base"\ndevice = "cpu"\n'
        '[model.large]\npath = "C:/models/large"\nrevision = "abc123"\nthreshold = 0.7\n'
        '[model.base]\npath = "C:/models/base"\nrevision = "def456"\n',
    )

    settings = load_settings(path)

    assert settings.model.select == "base"
    assert settings.model.device == "cpu"
    assert settings.model.large.name == "lettucedect-large-modernbert-en-v1"
    assert settings.model.large.path == "C:/models/large"
    assert settings.model.large.revision == "abc123"
    assert settings.model.large.threshold == 0.7
    assert settings.model.base.name == "lettucedect-base-modernbert-en-v1"
    assert settings.model.base.path == "C:/models/base"
    assert settings.model.base.threshold is None


def test_unknown_model_choice_is_rejected(tmp_path):
    path = write_config(tmp_path, '[model]\nselect = "medium"\n')

    with pytest.raises(ConfigError, match="model.select"):
        load_settings(path)


def test_model_threshold_outside_zero_to_one_is_rejected(tmp_path):
    path = write_config(tmp_path, "[model.large]\nthreshold = 1.2\n")

    with pytest.raises(ConfigError, match="model.large.threshold"):
        load_settings(path)


@pytest.mark.parametrize("threshold", ["1.5", "-0.1"])
def test_threshold_outside_zero_to_one_is_rejected(tmp_path, threshold):
    path = write_config(tmp_path, f"[detection]\nthreshold = {threshold}\n")

    with pytest.raises(ConfigError, match="detection.threshold"):
        load_settings(path)


def test_overlap_as_large_as_the_window_is_rejected(tmp_path):
    path = write_config(
        tmp_path, "[detection]\nwindow_evidence_tokens = 500\nwindow_overlap_tokens = 500\n"
    )

    with pytest.raises(ConfigError, match="window_overlap_tokens"):
        load_settings(path)


# --- Run, store, and judge settings (feature 006) ---


def test_run_store_and_judge_defaults():
    settings = Settings()

    assert settings.run.sample_rate == 0.02
    assert settings.run.sample_seed == "evalsvc"
    assert settings.store.kind == "jsonl"
    assert settings.store.path == "store"
    assert settings.store.write_retries == 3
    assert settings.judge.kind == "stub"
    assert settings.judge.timeout_seconds == 60


@pytest.mark.parametrize("rate", ["1.5", "-0.1"])
def test_sample_rate_outside_zero_to_one_is_rejected(tmp_path, rate):
    path = write_config(tmp_path, f"[run]\nsample_rate = {rate}\n")

    with pytest.raises(ConfigError, match="run.sample_rate"):
        load_settings(path)


def test_judge_timeout_must_be_positive(tmp_path):
    path = write_config(tmp_path, "[judge]\ntimeout_seconds = 0\n")

    with pytest.raises(ConfigError, match="judge.timeout_seconds"):
        load_settings(path)


def test_unknown_device_is_rejected(tmp_path):
    path = write_config(tmp_path, '[model]\ndevice = "quantum"\n')

    with pytest.raises(ConfigError, match="model.device"):
        load_settings(path)
