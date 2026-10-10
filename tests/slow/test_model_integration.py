"""Tests that load the real model. Run with: pytest -m slow

They need the model on local disk, named by the environment variable
EVALSVC_TEST_MODEL_PATH. All text here is invented.
"""

import importlib.util
import os
import socket
from pathlib import Path
from string import Template

import pytest

from evalsvc.config import ChecksSettings, DetectionSettings, ModelSettings, SentenceSettings
from evalsvc.detector.model import HFTokenCounter, TransformerDetector
from evalsvc.detector.prompt import format_context
from evalsvc.detector.select import SelectedModel, gpu_available
from evalsvc.evaluators.groundedness import evaluate_groundedness
from evalsvc.interfaces import DetectorInputError
from evalsvc.text.nlp import build_nlp
from evalsvc.text.sentences import split_answer
from evalsvc.types import Chunk

pytestmark = pytest.mark.slow

QUESTION = "What is the capital of France? What is the population of France?"
PASSAGES = [
    "France is a country in Europe. The capital of France is Paris.",
    "The population of France is 67 million.",
]
SUPPORTED_ANSWER = "The capital of France is Paris. The population of France is 67 million."
UNSUPPORTED_ANSWER = "The capital of France is Paris. The population of France is 69 million."


@pytest.fixture(scope="module")
def model_path() -> Path:
    value = os.environ.get("EVALSVC_TEST_MODEL_PATH")
    if not value:
        pytest.skip("EVALSVC_TEST_MODEL_PATH is not set")
    return Path(value)


@pytest.fixture(scope="module")
def device() -> str:
    return "cuda" if gpu_available() else "cpu"


@pytest.fixture(scope="module")
def detector(model_path, device) -> TransformerDetector:
    selected = SelectedModel(
        variant="base",
        name=model_path.name,
        path=str(model_path),
        revision="test",
        device=device,
        threshold=0.5,
    )
    return TransformerDetector(selected, ModelSettings())


def make_chunks(texts):
    return [
        Chunk(chunk_id=f"c{i + 1}", evidence_index=i, start=0, end=len(t), text=t, token_count=0)
        for i, t in enumerate(texts)
    ]


def evaluate(detector, answer):
    nlp = build_nlp(SentenceSettings())
    sentences = split_answer(answer, nlp, SentenceSettings(), ChecksSettings())
    return evaluate_groundedness(
        QUESTION, make_chunks(PASSAGES), answer, sentences, detector, DetectionSettings()
    )


# --- Scoring (T015) ---


def test_word_ranges_reproduce_the_answer(detector):
    [words] = detector.score_batch([PASSAGES], QUESTION, UNSUPPORTED_ANSWER)

    texts = [UNSUPPORTED_ANSWER[w.start : w.end] for w in words]
    assert texts == UNSUPPORTED_ANSWER.split()
    assert all(0.0 <= w.prob <= 1.0 for w in words)


def test_every_window_returns_the_same_answer_tokens(detector):
    first, second = detector.score_batch([PASSAGES[:1], PASSAGES[1:]], QUESTION, SUPPORTED_ANSWER)

    assert [(w.start, w.end) for w in first] == [(w.start, w.end) for w in second]


def test_cost_estimate_is_close_to_the_real_input_length(detector):
    estimate = detector.fixed_cost(QUESTION, SUPPORTED_ANSWER) + sum(
        detector.passage_cost(passage) for passage in PASSAGES
    )

    prompt = format_context(PASSAGES, QUESTION)
    real = len(detector._tokenizer(prompt, SUPPORTED_ANSWER)["input_ids"])

    assert abs(estimate - real) <= 10


def test_token_counter_counts_like_the_detector(detector):
    counter = HFTokenCounter(detector)

    assert counter.count("The capital of France is Paris.") == detector.count_tokens(
        "The capital of France is Paris."
    )
    assert counter.count("") == 0


def test_supported_answer_passes(detector):
    result = evaluate(detector, SUPPORTED_ANSWER)

    assert result.evaluable is True
    assert result.verdict == "pass"
    assert result.windows_run == 1


def test_unsupported_answer_fails_on_the_wrong_number(detector):
    result = evaluate(detector, UNSUPPORTED_ANSWER)

    assert result.verdict == "fail"
    assert any("69" in span.text for span in result.unsupported_spans)
    assert all(
        UNSUPPORTED_ANSWER[span.start : span.end] == span.text
        for span in result.unsupported_spans
    )
    assert result.model.device in ("cpu", "cuda")


def test_input_over_the_limit_is_rejected_not_truncated(model_path, device):
    selected = SelectedModel(
        variant="base",
        name=model_path.name,
        path=str(model_path),
        revision="test",
        device=device,
        threshold=0.5,
    )
    small = TransformerDetector(selected, ModelSettings(max_tokens=64))

    with pytest.raises(DetectorInputError):
        small.score_batch([PASSAGES * 10], QUESTION, SUPPORTED_ANSWER)


# --- Parity and no network use (T016) ---


def test_prompt_wording_matches_the_installed_package():
    spec = importlib.util.find_spec("lettucedetect")
    if spec is None or not spec.submodule_search_locations:
        pytest.skip("lettucedetect is not installed")
    prompts = Path(next(iter(spec.submodule_search_locations))) / "prompts"
    qa = Template((prompts / "qa_prompt_en.txt").read_text(encoding="utf-8"))
    summary = Template((prompts / "summary_prompt_en.txt").read_text(encoding="utf-8"))
    block = "passage 1: First passage.\npassage 2: Second passage."

    assert format_context(["First passage.", "Second passage."], QUESTION) == qa.substitute(
        question=QUESTION, num_passages=2, context=block
    )
    assert format_context(["First passage.", "Second passage."], None) == summary.substitute(
        text=block
    )


def test_token_probabilities_match_the_lettucedetect_package(detector, model_path, device):
    try:
        from lettucedetect.detectors.transformer import TransformerDetector as Reference
    except Exception as exc:  # the package's optional dependencies may be absent
        pytest.skip(f"lettucedetect cannot be imported: {exc}")

    reference = Reference(
        model_path=str(model_path), max_length=4096, device=device, local_files_only=True
    )
    theirs = reference.predict(
        context=PASSAGES, answer=UNSUPPORTED_ANSWER, question=QUESTION, output_format="tokens"
    )
    [ours] = detector._piece_scores([PASSAGES], QUESTION, UNSUPPORTED_ANSWER)

    # The package's list also holds the closing [SEP] token.
    assert len(theirs) == len(ours) + 1
    for (_, _, our_prob), their_token in zip(ours, theirs):
        assert our_prob == pytest.approx(their_token["prob"], abs=1e-3)


def test_scoring_makes_no_network_call(detector, monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("network call attempted")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)

    [words] = detector.score_batch([PASSAGES], QUESTION, SUPPORTED_ANSWER)

    assert words
    assert os.environ["HF_HUB_OFFLINE"] == "1"
