"""
Tests for addon config.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from transformerman.lib.addon_config import AddonConfig
from transformerman.lib.lm_clients import DummyLMClient, OpenAILMClient

if TYPE_CHECKING:
    from transformerman.lib.utilities import JSON_TYPE


@pytest.fixture
def addon_config_with_data() -> AddonConfig:
    """Create an AddonConfig with test data."""
    saved: dict[str, JSON_TYPE] = {}

    def loader() -> dict[str, JSON_TYPE]:
        return {
            "api_key": "test-key",
            "model": "gpt-4",
            "batch_size": 5,
        }

    def saver(config: dict[str, JSON_TYPE]) -> None:
        saved.clear()
        saved.update(config)

    config = AddonConfig(loader, saver)
    config.load()
    return config


@pytest.fixture
def empty_addon_config() -> AddonConfig:
    """Create an empty AddonConfig."""
    saved: dict[str, JSON_TYPE] = {}

    def loader() -> dict[str, JSON_TYPE]:
        return {}

    def saver(config: dict[str, JSON_TYPE]) -> None:
        saved.clear()
        saved.update(config)

    config = AddonConfig(loader, saver)
    config.load()
    return config


class TestAddonConfig:
    """Test class for AddonConfig."""

    def test_get_api_key(self, addon_config_with_data: AddonConfig) -> None:
        """Test getting API key."""
        assert str(addon_config_with_data.get("api_key", "")) == "test-key"

    def test_set_api_key(self) -> None:
        """Test setting API key."""
        saved_data: dict[str, JSON_TYPE] = {}

        def loader() -> dict[str, JSON_TYPE]:
            return {"api_key": "old-key"}

        def saver(config: dict[str, JSON_TYPE]) -> None:
            saved_data.clear()
            saved_data.update(config)

        addon_config = AddonConfig(loader, saver)
        addon_config.load()

        addon_config.update_setting("api_key", "new-key")
        assert str(addon_config.get("api_key", "")) == "new-key"

    def test_default_values(self, empty_addon_config: AddonConfig) -> None:
        """Test default values when config is empty."""
        assert str(empty_addon_config.get("api_key", "")) == ""
        assert str(empty_addon_config.get("model", "claude-v1.3-100k")) == "claude-v1.3-100k"
        assert empty_addon_config.get("batch_size", 10) == 10

    def test_get_client(self) -> None:
        """Test getting LM client."""

        def loader() -> dict[str, JSON_TYPE]:
            return {"lm_client": "openai"}

        def saver(config: dict[str, JSON_TYPE]) -> None:
            pass

        addon_config = AddonConfig(loader, saver)
        client = addon_config.getClient()
        assert isinstance(client, OpenAILMClient)

    def test_get_client_default(self) -> None:
        """Test getting default LM client."""

        def loader() -> dict[str, JSON_TYPE]:
            return {}

        def saver(config: dict[str, JSON_TYPE]) -> None:
            pass

        addon_config = AddonConfig(loader, saver)
        client = addon_config.getClient()
        assert isinstance(client, DummyLMClient)

    def test_is_enabled(self) -> None:
        """Test is_enabled method."""

        def loader() -> dict[str, JSON_TYPE]:
            return {
                "feature_a": True,
                "feature_b": False,
                "feature_c": "true",
                "feature_d": "yes",
                "feature_e": "no",
            }

        def saver(config: dict[str, JSON_TYPE]) -> None:
            pass

        addon_config = AddonConfig(loader, saver)
        addon_config.load()

        assert addon_config.is_enabled("feature_a") is True
        assert addon_config.is_enabled("feature_b") is False
        assert addon_config.is_enabled("feature_c") is True
        assert addon_config.is_enabled("feature_d") is True
        assert addon_config.is_enabled("feature_e") is False
        assert addon_config.is_enabled("feature_f", default=True) is True
        assert addon_config.is_enabled("feature_f", default=False) is False

    def test_contains(self, addon_config_with_data: AddonConfig) -> None:
        """Test __contains__ method."""
        assert "api_key" in addon_config_with_data
        assert "model" in addon_config_with_data
        assert "nonexistent" not in addon_config_with_data

    def test_getitem(self, addon_config_with_data: AddonConfig) -> None:
        """Test __getitem__ method."""
        assert addon_config_with_data["api_key"] == "test-key"
        assert addon_config_with_data["batch_size"] == 5

    def test_error_when_config_not_loaded(self) -> None:
        """Test that methods raise ValueError when config is not loaded."""

        def loader() -> dict[str, JSON_TYPE]:
            return {}

        def saver(config: dict[str, JSON_TYPE]) -> None:
            pass

        addon_config = AddonConfig(loader, saver)
        # Don't call load()

        with pytest.raises(ValueError, match="Config not loaded!"):
            _ = addon_config.get("api_key", "")

        with pytest.raises(ValueError, match="Config not loaded!"):
            _ = addon_config["api_key"]

        with pytest.raises(ValueError, match="Config not loaded!"):
            _ = "api_key" in addon_config

        with pytest.raises(ValueError, match="Config not loaded!"):
            addon_config.is_enabled("feature")

    def test_reload(self) -> None:
        """Test reload method."""
        current_data: dict[str, JSON_TYPE] = {"api_key": "initial"}

        def loader() -> dict[str, JSON_TYPE]:
            return current_data.copy()

        def saver(config: dict[str, JSON_TYPE]) -> None:
            nonlocal current_data
            current_data = config.copy()

        addon_config = AddonConfig(loader, saver)
        addon_config.load()

        assert addon_config.get("api_key", "") == "initial"

        # Update data externally
        current_data["api_key"] = "updated"

        # Reload should pick up the change
        addon_config.reload()
        assert addon_config.get("api_key", "") == "updated"

    def test_update_setting_persists_changes(self) -> None:
        """Test that update_setting persists changes through saver callback."""
        saved_items: list[tuple[str, JSON_TYPE]] = []

        def loader() -> dict[str, JSON_TYPE]:
            return {}

        def saver(config: dict[str, JSON_TYPE]) -> None:
            saved_items.clear()
            saved_items.extend(config.items())

        addon_config = AddonConfig(loader, saver)
        addon_config.load()

        # Test various types - update_setting doesn't accept None, so we don't test it
        test_cases = [
            ("string_key", "value"),
            ("int_key", 42),
            ("float_key", 3.14),
            ("bool_key", True),
            ("list_key", ["a", "b", "c"]),
            ("dict_key", {"nested": "value"}),
        ]

        for key, value in test_cases:
            addon_config.update_setting(key, value)  # type: ignore[arg-type]
            # Verify the value was passed to saver
            assert (key, value) in saved_items

    def test_double_load_raises_error(self, addon_config_with_data: AddonConfig) -> None:
        """Test that loading twice raises ValueError."""
        with pytest.raises(ValueError, match="Config already loaded!"):
            addon_config_with_data.load()
