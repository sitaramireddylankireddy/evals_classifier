"""The real detector: a token classifier loaded from a local folder.

Behaviour verified against lettucedetect 0.2.3:
- input is the pair (prompt, answer), laid out as [CLS] prompt [SEP] answer [SEP];
- output label 1 means "not supported by the evidence".
"""

from pathlib import Path
from typing import Any

from evalsvc.config import ConfigError, ModelSettings
from evalsvc.detector.prompt import format_context, passage_line
from evalsvc.detector.select import SelectedModel
from evalsvc.interfaces import DetectorInputError
from evalsvc.runtime import set_offline_env
from evalsvc.types import ModelInfo, TokenScore

UNSUPPORTED_LABEL = 1
_SPECIAL_TOKENS = 3
# Passage lines are numbered in the prompt. Costing uses a three-digit number
# so the estimate is never too low.
_COSTING_PASSAGE_NUMBER = 999

Piece = tuple[int, int, float]  # start, end, probability for one tokenizer token


def _load_tokenizer(folder: Path) -> Any:
    from transformers import AutoTokenizer

    return AutoTokenizer.from_pretrained(str(folder), local_files_only=True)


def _load_model(folder: Path) -> Any:
    from transformers import AutoModelForTokenClassification

    return AutoModelForTokenClassification.from_pretrained(
        str(folder), local_files_only=True, use_safetensors=True
    )


def _check_model_folder(folder: Path) -> None:
    if not folder.is_dir():
        raise ConfigError(f"Model folder not found: {folder}")
    if not any(folder.glob("*.safetensors")):
        raise ConfigError(
            f"No safetensors weights in {folder}. Only safetensors weights may be loaded."
        )


def merge_word_pieces(answer: str, pieces: list[Piece]) -> list[TokenScore]:
    """Join tokenizer tokens that touch each other into whole words.

    A word takes the highest probability of its pieces, so a span never starts
    or ends inside a word.
    """
    words: list[TokenScore] = []
    for start, end, prob in pieces:
        while start < end and answer[start].isspace():
            start += 1
        while end > start and answer[end - 1].isspace():
            end -= 1
        if start >= end:
            continue
        if words and words[-1].end == start:
            previous = words[-1]
            words[-1] = TokenScore(start=previous.start, end=end, prob=max(previous.prob, prob))
        else:
            words.append(TokenScore(start=start, end=end, prob=prob))
    return words


class TransformerDetector:
    def __init__(self, selected: SelectedModel, settings: ModelSettings) -> None:
        set_offline_env()
        folder = Path(selected.path)
        _check_model_folder(folder)

        self._tokenizer = _load_tokenizer(folder)
        model = _load_model(folder)

        labels = getattr(model.config, "num_labels", 2)
        if labels != 2:
            raise ConfigError(f"The model in {folder} has {labels} labels; 2 are expected.")
        limit = getattr(model.config, "max_position_embeddings", None)
        if limit is not None and settings.max_tokens > limit:
            raise ConfigError(
                f"model.max_tokens is {settings.max_tokens}, but the model in {folder} "
                f"reads at most {limit} tokens."
            )

        self._model = model.to(selected.device).eval()
        self._device = selected.device
        self._batch_size = settings.batch_size
        self.max_tokens = settings.max_tokens
        self.info = ModelInfo(name=selected.name, revision=selected.revision, device=selected.device)

    def count_tokens(self, text: str) -> int:
        return len(self._tokenizer(text, add_special_tokens=False)["input_ids"])

    def fixed_cost(self, question: str, answer: str) -> int:
        prompt_without_passages = format_context([], question)
        return (
            self.count_tokens(prompt_without_passages)
            + self.count_tokens(answer)
            + _SPECIAL_TOKENS
        )

    def passage_cost(self, text: str) -> int:
        # One more for the line break that separates passages.
        return self.count_tokens(passage_line(_COSTING_PASSAGE_NUMBER, text)) + 1

    def score_batch(
        self, contexts: list[list[str]], question: str, answer: str
    ) -> list[list[TokenScore]]:
        return [
            merge_word_pieces(answer, pieces)
            for pieces in self._piece_scores(contexts, question, answer)
        ]

    def _piece_scores(
        self, contexts: list[list[str]], question: str, answer: str
    ) -> list[list[Piece]]:
        """Probability and answer character range for every tokenizer token of the answer."""
        import torch

        prompts = [format_context(passages, question) for passages in contexts]
        results: list[list[Piece]] = []

        for first in range(0, len(prompts), self._batch_size):
            batch = prompts[first : first + self._batch_size]
            encoding = self._tokenizer(
                batch,
                [answer] * len(batch),
                truncation=False,
                padding=True,
                add_special_tokens=True,
                return_offsets_mapping=True,
                return_tensors="pt",
            )
            # Nothing is ever truncated: cutting the prompt would silently drop evidence.
            length = encoding["input_ids"].shape[1]
            if length > self.max_tokens:
                raise DetectorInputError(
                    f"input of {length} tokens exceeds the limit of {self.max_tokens}"
                )

            offsets = encoding["offset_mapping"].tolist()
            with torch.inference_mode():
                logits = self._model(
                    input_ids=encoding["input_ids"].to(self._device),
                    attention_mask=encoding["attention_mask"].to(self._device),
                ).logits
            probs = torch.softmax(logits.float(), dim=-1)[..., UNSUPPORTED_LABEL].cpu().tolist()

            for row in range(len(batch)):
                # Sequence 1 is the answer; offsets there are relative to the answer text.
                results.append(
                    [
                        (offsets[row][i][0], offsets[row][i][1], probs[row][i])
                        for i, sequence in enumerate(encoding.sequence_ids(row))
                        if sequence == 1 and offsets[row][i][1] > offsets[row][i][0]
                    ]
                )
        return results


class HFTokenCounter:
    """Counts tokens the way the detector does, for sizing evidence chunks."""

    def __init__(self, detector: TransformerDetector) -> None:
        self._detector = detector

    def count(self, text: str) -> int:
        return self._detector.count_tokens(text)
