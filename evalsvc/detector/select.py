"""Choose which model runs: the large one on a GPU, the base one on CPU."""

from typing import Literal

from evalsvc.config import ConfigError, DetectionSettings, Settings
from evalsvc.safelog import log_event
from evalsvc.types import FrozenModel


class SelectedModel(FrozenModel):
    variant: Literal["large", "base"]
    name: str
    path: str
    revision: str
    device: Literal["cpu", "cuda"]
    threshold: float


def gpu_available() -> bool:
    import torch  # imported here so that nothing else in this module needs torch

    return torch.cuda.is_available()


def select_model(settings: Settings, has_gpu: bool) -> SelectedModel:
    model = settings.model

    if model.device == "cuda" and not has_gpu:
        raise ConfigError("model.device is 'cuda' but no GPU is available")
    device = "cuda" if model.device == "cuda" or (model.device == "auto" and has_gpu) else "cpu"

    if model.select == "auto":
        variant = "large" if device == "cuda" else "base"
    else:
        variant = model.select
    chosen = model.large if variant == "large" else model.base

    # No fallback to the other model: a different model gives different results,
    # so that must never happen without the operator knowing.
    if not chosen.path:
        raise ConfigError(
            f"model.{variant}.path is not set. The {variant} model was selected "
            f"(device: {device}), so its local folder must be given in the config."
        )

    if not chosen.revision:
        raise ConfigError(
            f"model.{variant}.revision is not set. The model revision must be pinned in the config."
        )

    threshold = chosen.threshold if chosen.threshold is not None else settings.detection.threshold
    log_event(
        "model.selected",
        variant=variant,
        model=chosen.name,
        revision=chosen.revision,
        device=device,
        threshold=threshold,
    )
    return SelectedModel(
        variant=variant,
        name=chosen.name,
        path=chosen.path,
        revision=chosen.revision,
        device=device,
        threshold=threshold,
    )


def detection_settings_for(settings: Settings, selected: SelectedModel) -> DetectionSettings:
    """The detection settings with the selected model's threshold in force."""
    return settings.detection.model_copy(update={"threshold": selected.threshold})
