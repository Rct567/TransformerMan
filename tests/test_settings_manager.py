"""
Tests for settings manager.
"""

from __future__ import annotations

import pytest

from transformerman.lib.addon_config import AddonConfig
from transformerman.lib.settings_manager import SettingsManager


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

    config = AddonConfig(loader, saver)
    config.load()
    return config, saved_config


def test_get_api_key(mock_config: tuple[AddonConfig, dict[str, int | str]]) -> None:
    """Test getting API key."""
    config, _ = mock_config
    manager = SettingsManager(config)

    assert manager.get_api_key() == "test-key"


def test_set_api_key(mock_config: tuple[AddonConfig, dict[str, int | str]]) -> None:
    """Test setting API key."""
    config, saved = mock_config
    manager = SettingsManager(config)

    manager.set_api_key("new-key")

    assert manager.get_api_key() == "new-key"
    assert saved["api_key"] == "new-key"


def test_get_model(mock_config: tuple[AddonConfig, dict[str, int | str]]) -> None:
    """Test getting model."""
    config, _ = mock_config
    manager = SettingsManager(config)

    assert manager.get_model() == "gpt-4"


def test_set_model(mock_config: tuple[AddonConfig, dict[str, int | str]]) -> None:
    """Test setting model."""
    config, saved = mock_config
    manager = SettingsManager(config)

    manager.set_model("claude-v1.3-100k")

    assert manager.get_model() == "claude-v1.3-100k"
    assert saved["model"] == "claude-v1.3-100k"


def test_get_batch_size(mock_config: tuple[AddonConfig, dict[str, int | str]]) -> None:
    """Test getting batch size."""
    config, _ = mock_config
    manager = SettingsManager(config)

    assert manager.get_batch_size() == 5


def test_set_batch_size(mock_config: tuple[AddonConfig, dict[str, int | str]]) -> None:
    """Test setting batch size."""
    config, saved = mock_config
    manager = SettingsManager(config)

    manager.set_batch_size(20)

    assert manager.get_batch_size() == 20
    assert saved["batch_size"] == 20


def test_set_batch_size_minimum(mock_config: tuple[AddonConfig, dict[str, int | str]]) -> None:
    """Test that batch size cannot be less than 1."""
    config, saved = mock_config
    manager = SettingsManager(config)

    manager.set_batch_size(0)

    assert manager.get_batch_size() == 1
    assert saved["batch_size"] == 1


def test_get_available_models(mock_config: tuple[AddonConfig, dict[str, int | str]]) -> None:
    """Test getting available models."""
    config, _ = mock_config
    manager = SettingsManager(config)

    models = manager.get_available_models()

    assert isinstance(models, list)
    assert len(models) > 0
    assert "gpt-4" in models


def test_default_values():
    """Test default values when config is empty."""
    def loader():
        return {}

    def saver(config: dict[str, int | str]) -> None:
        pass

    config = AddonConfig(loader, saver)
    config.load()
    manager = SettingsManager(config)

    assert manager.get_api_key() == ""
    assert manager.get_model() == "claude-v1.3-100k"
    assert manager.get_batch_size() == 10
