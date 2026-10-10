"""Service settings, read from one TOML file."""

import re
import tomllib
from pathlib import Path
from typing import Annotated, Literal

from pydantic import AfterValidator, Field, ValidationError, model_validator

from evalsvc.types import FrozenModel


class ConfigError(Exception):
    """The config file is missing, unreadable, or has invalid content."""


def _check_pattern(pattern: str) -> str:
    try:
        re.compile(pattern)
    except re.error as exc:
        raise ValueError(f"invalid regular expression: {exc}") from None
    return pattern


Pattern = Annotated[str, AfterValidator(_check_pattern)]


class InputSettings(FrozenModel):
    parser: str = "json_list"
    key_id: str = "id"
    key_question: str = "question"
    key_evidence: str = "evidence"
    key_answer: str = "answer"


DEFAULT_HEADING_PATTERNS = [
    r"^#{1,6}\s+\S",
    r"^\d+(?:\.\d+)*\.?\s+[A-Z]",
    r"^[A-Z][A-Z \-]{3,60}$",
    r"(?i)^(?:section|clause|article|part|chapter|schedule|appendix)\s+\d",
]


class ChunkingSettings(FrozenModel):
    min_tokens: int = Field(default=300, ge=1)
    max_tokens: int = Field(default=500, ge=1)
    heading_patterns: list[Pattern] = Field(default_factory=lambda: list(DEFAULT_HEADING_PATTERNS))
    max_heading_chars: int = Field(default=120, ge=1)

    @model_validator(mode="after")
    def _min_not_above_max(self) -> "ChunkingSettings":
        if self.min_tokens > self.max_tokens:
            raise ValueError("min_tokens must not be larger than max_tokens")
        return self


class NonFactualRule(FrozenModel):
    name: str
    pattern: Pattern


def _default_non_factual_rules() -> list[NonFactualRule]:
    return [
        NonFactualRule(name="apology", pattern=r"(?i)\b(?:sorry|apologi[sz]e|apologies)\b"),
        NonFactualRule(
            name="empathy",
            pattern=r"(?i)\b(?:we|i) (?:understand|appreciate|realise|realize)\b",
        ),
        NonFactualRule(name="thanks", pattern=r"(?i)^\W*thank(?:s| you)\b"),
        NonFactualRule(
            name="next_step",
            pattern=(
                r"(?i)\b(?:please (?:contact|let us know|get in touch)"
                r"|if you have any (?:further |other )?questions|do not hesitate)\b"
            ),
        ),
    ]


class SentenceSettings(FrozenModel):
    spacy_pipeline: str = "blank_en"
    non_factual_rules: list[NonFactualRule] = Field(default_factory=_default_non_factual_rules)


DEFAULT_REFERENCE_PATTERNS = [
    r"(?i)\b(?:section|clause|paragraph|article)\s+\d+(?:\.\d+)*[a-z]?\b",
]


class ChecksSettings(FrozenModel):
    currencies: list[str] = Field(default_factory=lambda: ["GBP"])
    reference_patterns: list[Pattern] = Field(
        default_factory=lambda: list(DEFAULT_REFERENCE_PATTERNS)
    )


class ModelVariantSettings(FrozenModel):
    name: str
    path: str = ""  # local folder holding the weights; never a hub name
    revision: str = ""  # pinned commit hash, recorded in every result
    # Threshold chosen for this model from the golden set. None means use [detection].threshold.
    threshold: float | None = Field(default=None, ge=0.0, le=1.0)


class LargeModelSettings(ModelVariantSettings):
    name: str = "lettucedect-large-modernbert-en-v1"


class BaseModelSettings(ModelVariantSettings):
    name: str = "lettucedect-base-modernbert-en-v1"


class ModelSettings(FrozenModel):
    # "auto" runs the large model on a GPU and the base model on CPU.
    select: Literal["auto", "large", "base"] = "auto"
    device: Literal["auto", "cpu", "cuda"] = "auto"
    batch_size: int = Field(default=4, ge=1)
    # The models read up to 8,192 tokens, but lettucedetect trains and runs them at 4,096.
    max_tokens: int = Field(default=4096, ge=16)
    large: LargeModelSettings = LargeModelSettings()
    base: BaseModelSettings = BaseModelSettings()


class DetectionSettings(FrozenModel):
    threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    window_evidence_tokens: int = Field(default=6000, ge=1)
    window_overlap_tokens: int = Field(default=500, ge=0)
    safety_margin_tokens: int = Field(default=32, ge=0)

    @model_validator(mode="after")
    def _overlap_below_window(self) -> "DetectionSettings":
        if self.window_overlap_tokens >= self.window_evidence_tokens:
            raise ValueError("window_overlap_tokens must be smaller than window_evidence_tokens")
        return self


class Settings(FrozenModel):
    input: InputSettings = InputSettings()
    chunking: ChunkingSettings = ChunkingSettings()
    sentences: SentenceSettings = SentenceSettings()
    checks: ChecksSettings = ChecksSettings()
    model: ModelSettings = ModelSettings()
    detection: DetectionSettings = DetectionSettings()


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
