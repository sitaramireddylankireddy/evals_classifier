from pathlib import Path

import pytest

# Every text value in the fixtures contains this word. Privacy tests assert
# that it never shows up in logs or error messages.
SENTINEL = "ZZSENTINEL"


@pytest.fixture
def sentinel() -> str:
    return SENTINEL


@pytest.fixture
def fixtures_dir() -> Path:
    return Path(__file__).parent / "fixtures"
