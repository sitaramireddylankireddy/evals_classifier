"""Process-wide settings that must be in place before any model library is imported."""

import os

_OFFLINE_ENV = {
    "HF_HUB_OFFLINE": "1",
    "TRANSFORMERS_OFFLINE": "1",
    "HF_DATASETS_OFFLINE": "1",
    "HF_HUB_DISABLE_TELEMETRY": "1",
}


def set_offline_env() -> None:
    """Stop the model libraries from making any network call."""
    os.environ.update(_OFFLINE_ENV)
