"""Service settings, read from one TOML file."""

import tomllib
from pathlib import Path

from pydantic import ValidationError

from evalsvc.types import FrozenModel


class ConfigError(Exception):
    """The config file is missing, unreadable, or has invalid content."""


class InputSettings(FrozenModel):
    parser: str = "json_list"
    key_id: str = "id"
    key_question: str = "question"
    key_evidence: str = "evidence"
    key_answer: str = "answer"


class Settings(FrozenModel):
    input: InputSettings = InputSettings()


def load_settings(path: Path) -> Settings:
    try:
        with path.open("rb") as handle:
            raw = tomllib.load(handle)
    except FileNotFoundError:
        raise ConfigError(f"Config file not found: {path}") from None
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"Config file is not valid TOML: {path} ({exc})") from None

    try:
        return Settings.model_validate(raw)
    except ValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
            for error in exc.errors()
        )
        raise ConfigError(f"Invalid config in {path}: {problems}") from None
