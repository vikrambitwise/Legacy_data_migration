import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TEST_DATA = ROOT / "tests" / "_tmp"
TEST_DATA.mkdir(exist_ok=True)

os.environ["SOURCE_DB_URL"] = f"sqlite:///{(TEST_DATA / 'legacy_source.db').as_posix()}"
os.environ["TARGET_WAREHOUSE"] = "sqlite"
os.environ["TARGET_DB_URL"] = f"sqlite:///{(TEST_DATA / 'target_warehouse.db').as_posix()}"
os.environ["LLM_PROVIDER"] = "none"
os.environ["CONFIDENCE_THRESHOLD"] = "0.80"
os.environ["LOG_LEVEL"] = "WARNING"

from core.config import get_settings  # noqa: E402

get_settings.cache_clear()


@pytest.fixture()
def settings():
    get_settings.cache_clear()
    return get_settings()
