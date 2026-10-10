"""Tests that select and load a real model. Run with: pytest -m slow

Model folders come from two environment variables:
    EVALSVC_TEST_MODEL_PATH        the base model
    EVALSVC_TEST_LARGE_MODEL_PATH  the large model
A test is skipped when the folder it needs is not set. All text here is invented.
"""

import os

import pytest

from evalsvc.config import BaseModelSettings, LargeModelSettings, ModelSettings, Settings
from evalsvc.detector.model import TransformerDetector
from evalsvc.detector.select import gpu_available, select_model

pytestmark = pytest.mark.slow

BASE_ENV = "EVALSVC_TEST_MODEL_PATH"
LARGE_ENV = "EVALSVC_TEST_LARGE_MODEL_PATH"

QUESTION = "What is the capital of France? What is the population of France?"
PASSAGES = [
    "France is a country in Europe. The capital of France is Paris.",
    "The population of France is 67 million.",
]
ANSWER = "The capital of France is Paris. The population of France is 69 million."


def settings_from_env(select: str = "auto", device: str = "auto") -> Settings:
    return Settings(
        model=ModelSettings(
            select=select,
            device=device,
            large=LargeModelSettings(path=os.environ.get(LARGE_ENV, ""), revision="test"),
            base=BaseModelSettings(path=os.environ.get(BASE_ENV, ""), revision="test"),
        )
    )


def require(env_name: str) -> None:
    if not os.environ.get(env_name):
        pytest.skip(f"{env_name} is not set")


def flagged_words(detector: TransformerDetector) -> list[str]:
    [words] = detector.score_batch([PASSAGES], QUESTION, ANSWER)
    assert [ANSWER[w.start : w.end] for w in words] == ANSWER.split()
    return [ANSWER[w.start : w.end] for w in words if w.prob > 0.5]


def test_large_model_loads_and_flags_the_wrong_number():
    require(LARGE_ENV)
    settings = settings_from_env(select="large")
    has_gpu = gpu_available()

    selected = select_model(settings, has_gpu)
    detector = TransformerDetector(selected, settings.model)

    assert selected.variant == "large"
    assert detector.info.name == "lettucedect-large-modernbert-en-v1"
    assert detector.info.device == ("cuda" if has_gpu else "cpu")
    assert "69" in flagged_words(detector)


def load_large_on(device: str) -> TransformerDetector:
    require(LARGE_ENV)
    if device == "cuda" and not gpu_available():
        pytest.skip("no GPU is visible to torch, so the GPU run cannot be tested on this machine")
    settings = settings_from_env(select="large", device=device)
    selected = select_model(settings, gpu_available())
    assert (selected.variant, selected.device) == ("large", device)
    return TransformerDetector(selected, settings.model)


def weights_device(detector: TransformerDetector) -> str:
    """Where the model weights really are, read from the model itself."""
    return next(detector._model.parameters()).device.type


def test_large_model_runs_on_cpu():
    detector = load_large_on("cpu")

    assert detector.info.device == "cpu"
    assert weights_device(detector) == "cpu"
    assert "69" in flagged_words(detector)


def test_large_model_runs_on_gpu():
    import torch

    detector = load_large_on("cuda")

    assert detector.info.device == "cuda"
    assert weights_device(detector) == "cuda"
    # The weights take up GPU memory only if they were really moved there.
    assert torch.cuda.memory_allocated() > 0
    assert "69" in flagged_words(detector)


def test_large_model_gives_the_same_scores_on_cpu_and_gpu():
    on_gpu = load_large_on("cuda")
    on_cpu = load_large_on("cpu")

    [gpu_words] = on_gpu.score_batch([PASSAGES], QUESTION, ANSWER)
    [cpu_words] = on_cpu.score_batch([PASSAGES], QUESTION, ANSWER)

    assert [(w.start, w.end) for w in gpu_words] == [(w.start, w.end) for w in cpu_words]
    for gpu_word, cpu_word in zip(gpu_words, cpu_words):
        assert gpu_word.prob == pytest.approx(cpu_word.prob, abs=0.01)


def test_automatic_selection_loads_the_right_model_for_this_machine():
    has_gpu = gpu_available()
    require(LARGE_ENV if has_gpu else BASE_ENV)
    settings = settings_from_env()

    selected = select_model(settings, has_gpu)
    detector = TransformerDetector(selected, settings.model)

    assert selected.variant == ("large" if has_gpu else "base")
    assert detector.info.device == ("cuda" if has_gpu else "cpu")
    assert "69" in flagged_words(detector)
