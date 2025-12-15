"""
Shared fixtures for all tests.

This module provides common test fixtures available to all test modules.
Follows project guideline: "Use pytest fixtures, but try to use the real thing where possible (it often is)"
"""

from __future__ import annotations

from typing import TYPE_CHECKING
import pytest

from transformerman.lib.addon_config import AddonConfig

if TYPE_CHECKING:
    from transformerman.lib.utilities import JSON_TYPE


@pytest.fixture
def addon_config() -> AddonConfig:
    """
    Real AddonConfig for tests.

    Returns a real AddonConfig instance with in-memory storage for testing.
    """
    saved_config: dict[str, JSON_TYPE] = {
        "lm_client": "dummy",
        "dummy_model": "mock_content_generator",
        "batch_size": 10,
        "log_lm_requests": False,
        "log_lm_responses": False,
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
