import os
from types import SimpleNamespace

import pytest

from evalsvc.config import ConfigError, ModelSettings
from evalsvc.detector import model as model_module
from evalsvc.detector.model import TransformerDetector, merge_word_pieces
from evalsvc.detector.select import SelectedModel
from evalsvc.interfaces import Detector


class FakeModel:
    def __init__(self, num_labels=2, max_position_embeddings=8192):
        self.config = SimpleNamespace(
            num_labels=num_labels, max_position_embeddings=max_position_embeddings
        )
        self.device = None
        self.in_eval_mode = False

    def to(self, device):
        self.device = device
        return self

    def eval(self):
        self.in_eval_mode = True
        return self


class FakeTokenizer:
    def __call__(self, text, add_special_tokens=True):
        return {"input_ids": text.split()}


@pytest.fixture
def model_folder(tmp_path):
    folder = tmp_path / "model"
    folder.mkdir()
    (folder / "model.safetensors").write_bytes(b"")
    return folder


@pytest.fixture
def loader_calls(monkeypatch):
    """Replace the transformers loaders and record how they are called."""
    import transformers

    calls = {}
    fake_model = FakeModel()

    def load_tokenizer(path, **kwargs):
        calls["tokenizer"] = (path, kwargs)
        return FakeTokenizer()

    def load_model(path, **kwargs):
        calls["model"] = (path, kwargs)
        return fake_model

    monkeypatch.setattr(transformers.AutoTokenizer, "from_pretrained", load_tokenizer)
    monkeypatch.setattr(
        transformers.AutoModelForTokenClassification, "from_pretrained", load_model
    )
    calls["fake_model"] = fake_model
    return calls


def selected(folder, device="cpu"):
    return SelectedModel(
        variant="base",
        name="lettucedect-base-modernbert-en-v1",
        path=str(folder),
        revision="abc123",
        device=device,
        threshold=0.5,
    )


# --- Safe loading (T014) ---


def test_loaders_are_called_with_the_safety_settings(model_folder, loader_calls):
    TransformerDetector(selected(model_folder), ModelSettings())

    tokenizer_path, tokenizer_kwargs = loader_calls["tokenizer"]
    model_path, model_kwargs = loader_calls["model"]
    assert tokenizer_path == str(model_folder)
    assert model_path == str(model_folder)
    assert tokenizer_kwargs["local_files_only"] is True
    assert model_kwargs["local_files_only"] is True
    assert model_kwargs["use_safetensors"] is True
    assert "trust_remote_code" not in tokenizer_kwargs
    assert "trust_remote_code" not in model_kwargs


def test_offline_mode_is_set_before_loading(model_folder, loader_calls, monkeypatch):
    monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)

    TransformerDetector(selected(model_folder), ModelSettings())

    assert os.environ["HF_HUB_OFFLINE"] == "1"
    assert os.environ["TRANSFORMERS_OFFLINE"] == "1"


def test_folder_without_safetensors_weights_is_rejected(tmp_path, loader_calls):
    folder = tmp_path / "model"
    folder.mkdir()
    (folder / "pytorch_model.bin").write_bytes(b"")

    with pytest.raises(ConfigError, match="safetensors"):
        TransformerDetector(selected(folder), ModelSettings())

    assert "model" not in loader_calls


def test_missing_folder_is_rejected(tmp_path, loader_calls):
    with pytest.raises(ConfigError, match="not found"):
        TransformerDetector(selected(tmp_path / "absent"), ModelSettings())


@pytest.mark.parametrize("device", ["cpu", "cuda"])
def test_model_is_moved_to_the_selected_device(model_folder, loader_calls, device):
    TransformerDetector(selected(model_folder, device), ModelSettings())

    assert loader_calls["fake_model"].device == device
    assert loader_calls["fake_model"].in_eval_mode is True


def test_info_carries_name_revision_and_device(model_folder, loader_calls):
    detector = TransformerDetector(selected(model_folder), ModelSettings(max_tokens=2048))

    assert detector.info.name == "lettucedect-base-modernbert-en-v1"
    assert detector.info.revision == "abc123"
    assert detector.info.device == "cpu"
    assert detector.max_tokens == 2048
    assert isinstance(detector, Detector)


def test_max_tokens_above_the_models_limit_is_rejected(model_folder, loader_calls):
    with pytest.raises(ConfigError, match="max_tokens"):
        TransformerDetector(selected(model_folder), ModelSettings(max_tokens=9000))


def test_model_with_the_wrong_number_of_labels_is_rejected(model_folder, monkeypatch):
    monkeypatch.setattr(model_module, "_load_tokenizer", lambda folder: FakeTokenizer())
    monkeypatch.setattr(model_module, "_load_model", lambda folder: FakeModel(num_labels=5))

    with pytest.raises(ConfigError, match="5 labels"):
        TransformerDetector(selected(model_folder), ModelSettings())


def test_costs_follow_the_prompt_wording(model_folder, loader_calls):
    detector = TransformerDetector(selected(model_folder), ModelSettings())

    assert detector.count_tokens("three short words") == 3
    # "passage 999: two words" is four words, plus one for the line break.
    assert detector.passage_cost("two words") == 5
    with_question = detector.fixed_cost("What is the limit?", "It is high.")
    without_question = detector.fixed_cost("", "It is high.")
    assert with_question > without_question > 3


# --- Whole words from tokenizer tokens ---


def test_touching_pieces_are_joined_and_take_the_highest_probability():
    answer = "The unbelievable fee."
    pieces = [(0, 3, 0.1), (4, 6, 0.2), (6, 12, 0.9), (12, 16, 0.3), (17, 20, 0.1), (20, 21, 0.4)]

    words = merge_word_pieces(answer, pieces)

    assert [(answer[w.start : w.end], w.prob) for w in words] == [
        ("The", 0.1),
        ("unbelievable", 0.9),
        ("fee.", 0.4),
    ]


def test_leading_spaces_in_piece_ranges_are_removed():
    answer = "The fee is £5."
    pieces = [(0, 3, 0.1), (3, 7, 0.2), (7, 10, 0.3), (10, 12, 0.8), (12, 13, 0.7), (13, 14, 0.2)]

    words = merge_word_pieces(answer, pieces)

    assert [answer[w.start : w.end] for w in words] == ["The", "fee", "is", "£5."]
    assert words[-1].prob == 0.8


def test_whitespace_only_pieces_are_dropped():
    answer = "One\n\nTwo"
    pieces = [(0, 3, 0.1), (3, 5, 0.9), (5, 8, 0.2)]

    words = merge_word_pieces(answer, pieces)

    assert [(answer[w.start : w.end], w.prob) for w in words] == [("One", 0.1), ("Two", 0.2)]


def test_no_pieces_give_no_words():
    assert merge_word_pieces("", []) == []
