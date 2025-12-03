"""
Tests for addon config.
"""

from __future__ import annotations

import pytest

from transformerman.lib.addon_config import AddonConfig


@pytest.fixture
def mock_config():
    """Create a mock config for testing."""
    def loader():
        return {
            "api_key": "test-key",
            "model": "gpt-4",
            "batch_size": 5,
        }

    saved_config = {}

    def saver(config: dict[str, int | str]) -> None:
        saved_config.update(config)

    addon_config = AddonConfig(loader, saver)
    addon_config.load()
    return addon_config, saved_config


def test_get_api_key(mock_config: tuple[AddonConfig, dict[str, int | str]]) -> None:
    """Test getting API key."""
    addon_config, _ = mock_config

    assert str(addon_config.get("api_key", "")) == "test-key"


def test_set_api_key(mock_config: tuple[AddonConfig, dict[str, int | str]]) -> None:
    """Test setting API key."""
    addon_config, saved = mock_config

    addon_config.update_setting("api_key", "new-key")

    assert str(addon_config.get("api_key", "")) == "new-key"
    assert saved["api_key"] == "new-key"



def test_default_values():
    """Test default values when config is empty."""
    def loader():
        return {}

    def saver(config: dict[str, int | str]) -> None:
        pass

    addon_config = AddonConfig(loader, saver)
    addon_config.load()

    assert str(addon_config.get("api_key", "")) == ""
    assert str(addon_config.get("model", "claude-v1.3-100k")) == "claude-v1.3-100k"
    assert addon_config.get("batch_size", 10) == 10
