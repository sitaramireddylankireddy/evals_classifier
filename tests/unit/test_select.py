import pytest

from evalsvc.config import (
    BaseModelSettings,
    ConfigError,
    DetectionSettings,
    LargeModelSettings,
    ModelSettings,
    Settings,
)
from evalsvc.detector.select import detection_settings_for, select_model


def make_settings(select="auto", device="auto", large_threshold=None, base_threshold=None, **paths):
    return Settings(
        model=ModelSettings(
            select=select,
            device=device,
            large=LargeModelSettings(
                path=paths.get("large_path", "C:/models/large"),
                revision="large-rev",
                threshold=large_threshold,
            ),
            base=BaseModelSettings(
                path=paths.get("base_path", "C:/models/base"),
                revision="base-rev",
                threshold=base_threshold,
            ),
        ),
        detection=DetectionSettings(threshold=0.5),
    )


def test_gpu_selects_the_large_model():
    selected = select_model(make_settings(), has_gpu=True)

    assert selected.variant == "large"
    assert selected.device == "cuda"
    assert selected.name == "lettucedect-large-modernbert-en-v1"
    assert selected.path == "C:/models/large"
    assert selected.revision == "large-rev"


def test_no_gpu_selects_the_base_model():
    selected = select_model(make_settings(), has_gpu=False)

    assert selected.variant == "base"
    assert selected.device == "cpu"
    assert selected.name == "lettucedect-base-modernbert-en-v1"
    assert selected.path == "C:/models/base"
    assert selected.revision == "base-rev"


@pytest.mark.parametrize(
    ("select", "has_gpu", "variant", "device"),
    [
        ("large", False, "large", "cpu"),
        ("base", True, "base", "cuda"),
        ("large", True, "large", "cuda"),
        ("base", False, "base", "cpu"),
    ],
)
def test_model_can_be_forced(select, has_gpu, variant, device):
    selected = select_model(make_settings(select=select), has_gpu=has_gpu)

    assert (selected.variant, selected.device) == (variant, device)


def test_device_forced_to_cpu_selects_the_base_model_even_with_a_gpu():
    selected = select_model(make_settings(device="cpu"), has_gpu=True)

    assert (selected.variant, selected.device) == ("base", "cpu")


def test_device_forced_to_cuda_without_a_gpu_is_an_error():
    with pytest.raises(ConfigError, match="no GPU"):
        select_model(make_settings(device="cuda"), has_gpu=False)


def test_missing_path_for_the_selected_model_is_an_error_not_a_fallback():
    with pytest.raises(ConfigError, match="model.large.path"):
        select_model(make_settings(large_path=""), has_gpu=True)
    with pytest.raises(ConfigError, match="model.base.path"):
        select_model(make_settings(base_path=""), has_gpu=False)


def test_missing_revision_for_the_selected_model_is_an_error():
    settings = Settings(
        model=ModelSettings(base=BaseModelSettings(path="C:/models/base", revision=""))
    )

    with pytest.raises(ConfigError, match="model.base.revision"):
        select_model(settings, has_gpu=False)


def test_missing_path_for_the_other_model_does_not_matter():
    selected = select_model(make_settings(large_path=""), has_gpu=False)

    assert selected.variant == "base"


def test_threshold_comes_from_detection_settings_by_default():
    assert select_model(make_settings(), has_gpu=True).threshold == 0.5
    assert select_model(make_settings(), has_gpu=False).threshold == 0.5


def test_each_model_can_have_its_own_threshold():
    settings = make_settings(large_threshold=0.7, base_threshold=0.4)

    assert select_model(settings, has_gpu=True).threshold == 0.7
    assert select_model(settings, has_gpu=False).threshold == 0.4


def test_detection_settings_take_the_selected_models_threshold():
    settings = make_settings(large_threshold=0.7)
    selected = select_model(settings, has_gpu=True)

    detection = detection_settings_for(settings, selected)

    assert detection.threshold == 0.7
    assert detection.window_evidence_tokens == settings.detection.window_evidence_tokens


def test_selection_is_logged_without_the_path(caplog):
    import logging

    caplog.set_level(logging.DEBUG)

    select_model(make_settings(), has_gpu=True)

    assert "model.selected" in caplog.text
    assert "C:/models/large" not in caplog.text
