"""
Tests for addon config.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from transformerman.lib.addon_config import AddonConfig
from transformerman.lib.lm_clients import OpenAILMClient, ApiKey

if TYPE_CHECKING:
    from transformerman.lib.utilities import JSON_TYPE


@pytest.fixture
def addon_config_with_data() -> AddonConfig:
    """Create an AddonConfig with test data."""
    saved: dict[str, JSON_TYPE] = {}

    def loader() -> dict[str, JSON_TYPE]:
        return {
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

    def test_set_api_key(self) -> None:
        """Test setting API key."""
        saved_data: dict[str, JSON_TYPE] = {}

        def loader() -> dict[str, JSON_TYPE]:
            return {"openai_api_key": "old-key"}

        def saver(config: dict[str, JSON_TYPE]) -> None:
            saved_data.clear()
            saved_data.update(config)

        addon_config = AddonConfig(loader, saver)
        addon_config.load()

        assert addon_config.get_api_key("openai") == ApiKey("old-key")
        addon_config.update_setting("openai_api_key", "new-key")

        assert addon_config.get("openai_api_key", None) == "new-key"
        assert addon_config.get_api_key("openai") == ApiKey("new-key")

    def test_default_values(self, empty_addon_config: AddonConfig) -> None:
        """Test default values when config is empty."""
        assert str(empty_addon_config.get("model", "claude-v1.3-100k")) == "claude-v1.3-100k"
        assert empty_addon_config.get("batch_size", 10) == 10
        assert empty_addon_config.is_enabled("log_last_lm_response_request", False) is False

    def test_get_client(self) -> None:
        """Test getting LM client."""

        def loader() -> dict[str, JSON_TYPE]:
            return {"lm_client": "openai", "openai_model": "gpt-5", "openai_api_key": "test-key"}

        def saver(config: dict[str, JSON_TYPE]) -> None:
            pass

        addon_config = AddonConfig(loader, saver)
        client, error = addon_config.get_client()
        assert error is None
        assert isinstance(client, OpenAILMClient)

    def test_get_client_not_configured(self) -> None:
        """Test getting default LM client."""

        def loader() -> dict[str, JSON_TYPE]:
            return {}

        def saver(config: dict[str, JSON_TYPE]) -> None:
            pass

        addon_config = AddonConfig(loader, saver)
        client, error = addon_config.get_client()
        assert client is None
        assert error is not None

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
        assert "model" in addon_config_with_data
        assert "nonexistent" not in addon_config_with_data

    def test_getitem(self, addon_config_with_data: AddonConfig) -> None:
        """Test __getitem__ method."""
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
            addon_config.is_enabled("feature")

    def test_reload(self) -> None:
        """Test reload method."""
        current_data: dict[str, JSON_TYPE] = {"gemini_api_key": "initial"}

        def loader() -> dict[str, JSON_TYPE]:
            return current_data.copy()

        def saver(config: dict[str, JSON_TYPE]) -> None:
            nonlocal current_data
            current_data = config.copy()

        addon_config = AddonConfig(loader, saver)
        addon_config.load()

        assert addon_config.get("gemini_api_key", "") == "initial"

        # Update data externally
        current_data["gemini_api_key"] = "updated"

        # Reload should pick up the change
        addon_config.reload()
        assert addon_config.get("gemini_api_key", "") == "updated"

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

    def test_milestone_system(self, empty_addon_config: AddonConfig) -> None:
        """Comprehensive test for the milestone system."""
        # Initial state
        assert empty_addon_config.should_ask_for_review() is True
        assert empty_addon_config.get("notes_generated_count", 0) == 0

        # 1. Increment counter, no milestone
        old_count, new_count = empty_addon_config.increase_counter("notes_generated_count", 50)
        milestone = empty_addon_config.get_milestone_reached(old_count, new_count)
        assert milestone is None
        assert old_count == 0
        assert new_count == 50

        # 2. Reach first milestone (100)
        old_count, new_count = empty_addon_config.increase_counter("notes_generated_count", 50)
        milestone = empty_addon_config.get_milestone_reached(old_count, new_count)
        assert milestone == 100
        assert old_count == 50
        assert new_count == 100

        # 3. Increment more, no new milestone
        old_count, new_count = empty_addon_config.increase_counter("notes_generated_count", 100)
        milestone = empty_addon_config.get_milestone_reached(old_count, new_count)
        assert milestone is None
        assert old_count == 100
        assert new_count == 200

        # 4. Reach second milestone (1,000)
        old_count, new_count = empty_addon_config.increase_counter("notes_generated_count", 800)
        milestone = empty_addon_config.get_milestone_reached(old_count, new_count)
        assert milestone == 1_000
        assert old_count == 200
        assert new_count == 1000

        # 5. Test review request logic
        assert empty_addon_config.should_ask_for_review() is True
        empty_addon_config.disable_review_requests()
        assert empty_addon_config.should_ask_for_review() is False

        # 6. Reach third milestone (10,000) - review request should still be disabled
        old_count, new_count = empty_addon_config.increase_counter("notes_generated_count", 9000)
        milestone = empty_addon_config.get_milestone_reached(old_count, new_count)
        assert milestone == 10_000
        assert empty_addon_config.should_ask_for_review() is False
