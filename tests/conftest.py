"""
Shared fixtures for all tests.

This module provides common test fixtures available to all test modules.
Follows project guideline: "Use pytest fixtures, but try to use the real thing where possible (it often is)"
"""

from __future__ import annotations
from typing import TYPE_CHECKING

import pytest
from tests.tools import MockMW
from transformerman.lib.addon_config import AddonConfig

if TYPE_CHECKING:
    from pathlib import Path
    from transformerman.lib.utilities import JSON_TYPE


# patch the aqt.mw global to use our mock
import aqt
aqt.mw = MockMW()  # type: ignore[assignment]


@pytest.fixture
def user_files_dir(tmp_path: Path) -> Path:
    """Temporary directory for user files."""
    return tmp_path / "user_files"


@pytest.fixture
def addon_config() -> AddonConfig:
    """
    Real AddonConfig for tests.

    Returns a real AddonConfig instance with in-memory storage for testing.
    """
    saved_config: dict[str, JSON_TYPE] = {
        "lm_client": "dummy",
        "dummy_model": "lorem_ipsum",
        "batch_size": 10,
        "log_last_lm_response_request": False,
        "max_prompt_size": 500000,
        "dummy_api_key": "test-api-key",
    }

    def loader() -> dict[str, JSON_TYPE]:
        return saved_config.copy()

    def saver(config: dict[str, JSON_TYPE]) -> None:
        saved_config.clear()
        saved_config.update(config)

    config = AddonConfig(loader, saver)
    config.load()
    return config
