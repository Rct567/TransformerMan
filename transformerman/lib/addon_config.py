"""
TransformerMan by Rick Zuidhoek. Licensed under the GNU GPL-3.0.
See <https://www.gnu.org/licenses/gpl-3.0.html> for details.
"""

from __future__ import annotations


from typing import Any, Callable, Optional, Union, TYPE_CHECKING

if TYPE_CHECKING:
    from .utilities import JSON_TYPE
    from aqt.main import AnkiQt

from .lm_clients import LM_CLIENTS, LMClient, get_lm_client_class, ApiKey, ModelName


DEFAULT_MAX_PROMPT_SIZE = 50_000
DEFAULT_MAX_NOTES_PER_BATCH = 500
DEFAULT_TIMEOUT = 240
DEFAULT_CONNECT_TIMEOUT = 10
DEFAULT_MAX_EXAMPLES = 10
DEFAULT_CACHE_RESPONSES = 500


class AddonConfigError(str):
    pass


class AddonConfig:
    _config: Optional[dict[str, JSON_TYPE]]
    _config_load: Callable[[], Optional[dict[str, Any]]]
    _config_save: Callable[[dict[str, Any]], None]

    def __init__(self, config_loader: Callable[[], Optional[dict[str, Any]]], config_saver: Callable[[dict[str, Any]], None]) -> None:
        self._config = None
        self._config_load = config_loader
        self._config_save = config_saver

    def load(self) -> None:
        if self._config is not None:
            raise ValueError("Config already loaded!")
        config = self._config_load()
        if config is None:
            config = {}
        self._config = config

    def reload(self) -> None:
        self._config = None
        self.load()

    def __getitem__(self, key: str) -> JSON_TYPE:
        if self._config is None:
            raise ValueError("Config not loaded!")
        return self._config[key]

    def get(self, key: str, default: JSON_TYPE) -> JSON_TYPE:
        if self._config is None:
            raise ValueError("Config not loaded!")
        return self._config.get(key, default)

    def __contains__(self, key: str) -> bool:
        if self._config is None:
            raise ValueError("Config not loaded!")
        return key in self._config

    def is_enabled(self, key: str, default: bool = False) -> bool:
        if self._config is None:
            raise ValueError("Config not loaded!")
        if key not in self._config:
            return default
        val = self._config[key]
        if isinstance(val, bool):
            return val
        if isinstance(val, str):
            return val.lower() in {"y", "yes", "true"}
        return default

    def update_setting(self, key: str, value: Union[bool, int, float, str, list[Any], dict[str, Any]]) -> None:
        if self._config is None:
            raise ValueError("Config not loaded!")
        self._config[key] = value
        self._config_save(self._config)

    def get_api_key(self, client_id: str) -> ApiKey:
        """Get the API key for a specific LM client."""
        if self._config is None:
            self.load()

        # After load(), _config should not be None
        assert self._config is not None

        # client-specific key (e.g., "openai_api_key")
        client_key = f"{client_id}_api_key"
        if client_key in self._config:
            return ApiKey(str(self._config[client_key]))

        return ApiKey("")

    def get_model(self, client_id: str) -> str:
        """Get the model for a specific LM client."""
        if self._config is None:
            self.load()

        # After load(), _config should not be None
        assert self._config is not None

        model_key = f"{client_id}_model"
        return str(self.get(model_key, ""))

    def set_model(self, client_id: str, model: str) -> None:
        """Set the model for a specific LM client."""
        if self._config is None:
            self.load()

        # After load(), _config should not be None
        assert self._config is not None

        # Store with client-specific prefix
        model_key = f"{client_id}_model"
        self.update_setting(model_key, model)

    def set_api_key(self, client_id: str, api_key: str) -> None:
        """Set the API key for a specific LM client."""
        if self._config is None:
            self.load()

        # After load(), _config should not be None
        assert self._config is not None

        # Store with client-specific prefix
        client_key = f"{client_id}_api_key"
        self.update_setting(client_key, api_key)

    def get_custom_client_settings(self, client_id: str) -> dict[str, str]:
        """Get custom settings for a specific LM client."""
        if self._config is None:
            self.load()

        # After load(), _config should not be None
        assert self._config is not None

        custom_settings = {}
        prefix = f"{client_id}_custom_"

        for key, value in self._config.items():
            if key.startswith(prefix) and isinstance(value, str):
                setting_name = key[len(prefix):]
                custom_settings[setting_name] = value

        return custom_settings

    def set_custom_client_setting(self, client_id: str, setting_name: str, setting_value: str) -> None:
        """Set a custom setting for a specific LM client."""
        if self._config is None:
            self.load()

        # After load(), _config should not be None
        assert self._config is not None

        # Store with client-specific prefix
        client_key = f"{client_id}_custom_{setting_name}"
        self.update_setting(client_key, setting_value)

    def set_custom_client_settings(self, client_id: str, settings: dict[str, str]) -> None:
        """Set multiple custom settings for a specific LM client."""
        if self._config is None:
            self.load()

        # After load(), _config should not be None
        assert self._config is not None

        for setting_name, setting_value in settings.items():
            self.set_custom_client_setting(client_id, setting_name, setting_value)

    def _get_int_setting(self, key: str, default: int, min_val: int = 1) -> int:
        """Get an integer setting with validation."""
        val = self.get(key, default)
        if not isinstance(val, (int, float)) or val < min_val:
            return default
        return int(val)

    def get_max_prompt_size(self) -> int:
        """Get the maximum size of the prompt in characters.

        This limit helps prevent sending excessively large requests,
        which could lead to API errors. It also helps preventing request that are too small,
        leading to higher overhead.
        """
        return self._get_int_setting("max_prompt_size", DEFAULT_MAX_PROMPT_SIZE)

    def get_max_notes_per_batch(self) -> int:
        """Get the maximum number of notes to process in a single batch.

        Processing notes in batches improves efficiency, but very large batches
        might exceed memory limits or API constraints.
        """
        return self._get_int_setting("max_notes_per_batch", DEFAULT_MAX_NOTES_PER_BATCH)

    def get_timeout(self) -> int:
        """Get the total timeout in seconds for API requests.

        This is the maximum time allowed for the entire request-response cycle.
        """
        return self._get_int_setting("timeout", DEFAULT_TIMEOUT)

    def get_connect_timeout(self) -> int:
        """Get the connection timeout in seconds for API requests.

        This is the maximum time allowed to establish a connection with the API server.
        """
        return self._get_int_setting("connect_timeout", DEFAULT_CONNECT_TIMEOUT)

    def get_max_examples(self) -> int:
        """Get the maximum number of few-shot examples to include in the prompt.

        Few-shot examples help the model understand the desired output format and style.
        """
        return self._get_int_setting("max_examples", DEFAULT_MAX_EXAMPLES, min_val=0)

    def get_num_cache_responses(self) -> int:
        """Get the number of API responses to cache.

        Caching responses helps avoid redundant API calls for identical prompts,
        saving time and reducing costs. Set to 0 to disable caching.
        """
        if self._config and "cache_responses" in self._config and self._config["cache_responses"] is False:
            self._config["cache_responses"] = 0

        return self._get_int_setting("cache_responses", DEFAULT_CACHE_RESPONSES, min_val=0)

    def get_client(self) -> tuple[LMClient, None] | tuple[None, AddonConfigError]:
        """Return the configured LM client, or None if the client is unknown."""
        if self._config is None:
            self.load()

        # Lm client name
        client_name = self.get("lm_client", None)

        if client_name is None:
            return None, AddonConfigError("No LM client configured")
        if not isinstance(client_name, str):
            return None, AddonConfigError("Configured LM client is not a string")
        elif not client_name:
            return None, AddonConfigError("No LM client configured")

        if client_name not in LM_CLIENTS:
            return None, AddonConfigError(f"Unknown LM client '{client_name}' configured")

        # get client
        client_class = get_lm_client_class(client_name)

        if not client_class:
            return None, AddonConfigError(f"Unknown LM client '{client_name}' configured")

        # Model of LM client (stored with client prefix like API key)
        model_str = self.get_model(client_name)

        # Api key
        api_key = self.get_api_key(client_name)

        if client_class.api_key_required():
            if not api_key:
                return None, AddonConfigError(f"API key is required for client '{client_name}'")

        # Create client with proper types
        model = ModelName(model_str)
        custom_settings = self.get_custom_client_settings(client_name)
        client = client_class(api_key, model, self.get_timeout(), self.get_connect_timeout(), custom_settings)
        return client, None

    def increase_counter(self, key: str, amount: int = 1) -> tuple[int, int]:
        """Increment a counter and return (old_count, new_count)."""
        if self._config is None:
            self.load()

        old_count = self.get(key, 0)
        if not isinstance(old_count, int):
            old_count = 0

        new_count = old_count + amount
        self.update_setting(key, new_count)

        return old_count, new_count

    def get_milestone_reached(self, old_count: int, new_count: int) -> Optional[int]:
        """Check if a milestone was reached between old and new counts."""

        milestones = [10, 100, 500, 1_000, 10_000, 50_000]
        for milestone in milestones:
            if old_count < milestone <= new_count:
                return milestone
        return None

    def should_ask_for_review(self) -> bool:
        """Check if we should ask the user for a review."""
        return self.is_enabled("ask_for_review", default=True)

    def disable_review_requests(self) -> None:
        """Disable future review requests."""
        self.update_setting("ask_for_review", False)

    @staticmethod
    def from_anki_main_window(mw: AnkiQt) -> AddonConfig:

        addon_manager = mw.addonManager
        config_loader: Callable[[], Optional[dict[str, Any]]] = lambda: addon_manager.getConfig(__name__)
        config_saver: Callable[[dict[str, Any]], None] = lambda config: addon_manager.writeConfig(__name__, config)

        addon_config = AddonConfig(config_loader, config_saver)
        return addon_config
