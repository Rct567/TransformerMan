"""
TransformerMan by Rick Zuidhoek. Licensed under the GNU GPL-3.0.
See <https://www.gnu.org/licenses/gpl-3.0.html> for details.
"""

from __future__ import annotations


from typing import Any, Callable, Optional, Union, TYPE_CHECKING

if TYPE_CHECKING:
    from .utilities import JSON_TYPE
    from aqt.main import AnkiQt

from .lm_clients import LM_CLIENTS, LMClient, get_lm_client_class


class AddonConfig:

    __config: Optional[dict[str, JSON_TYPE]]
    __config_load: Callable[[], Optional[dict[str, Any]]]
    __config_save: Callable[[dict[str, Any]], None]

    def __init__(self, config_loader: Callable[[], Optional[dict[str, Any]]], config_saver: Callable[[dict[str, Any]], None]):
        self.__config = None
        self.__config_load = config_loader
        self.__config_save = config_saver

    def load(self) -> None:
        if self.__config is not None:
            raise ValueError("Config already loaded!")
        config = self.__config_load()
        if config is None:
            config = {}
        self.__config = config

    def reload(self) -> None:
        self.__config = None
        self.load()

    def __getitem__(self, key: str) -> JSON_TYPE:
        if self.__config is None:
            raise ValueError("Config not loaded!")
        return self.__config[key]

    def get(self, key: str, default: JSON_TYPE) -> JSON_TYPE:
        if self.__config is None:
            raise ValueError("Config not loaded!")
        return self.__config.get(key, default)

    def __contains__(self, key: str) -> bool:
        if self.__config is None:
            raise ValueError("Config not loaded!")
        return key in self.__config

    def is_enabled(self, key: str, default: bool = False) -> bool:
        if self.__config is None:
            raise ValueError("Config not loaded!")
        if key not in self.__config:
            return default
        val = self.__config[key]
        if isinstance(val, bool):
            return val
        if isinstance(val, str):
            return val.lower() in {"y", "yes", "true"}
        return default

    def update_setting(self, key: str, value: Union[bool, int, float, str, list[Any], dict[str, Any]]) -> None:
        if self.__config is None:
            raise ValueError("Config not loaded!")
        self.__config[key] = value
        self.__config_save(self.__config)

    def get_api_key(self, client_id: str) -> str:
        """Get the API key for a specific LM client."""
        if self.__config is None:
            self.load()

        # After load(), __config should not be None
        assert self.__config is not None

        # Try client-specific key first (e.g., "openai_api_key")
        client_key = f"{client_id}_api_key"
        if client_key in self.__config:
            return str(self.__config[client_key])

        # Fall back to generic "api_key" for backward compatibility
        return str(self.get("api_key", ""))

    def set_api_key(self, client_id: str, api_key: str) -> None:
        """Set the API key for a specific LM client."""
        if self.__config is None:
            self.load()

        # After load(), __config should not be None
        assert self.__config is not None

        # Store with client-specific prefix
        client_key = f"{client_id}_api_key"
        self.update_setting(client_key, api_key)

    def getClient(self) -> tuple[Optional[str], Optional[LMClient]]:
        """Return the configured LM client, or None if the client is unknown."""
        if self.__config is None:
            self.load()

        # Lm client name
        client_name = self.get("lm_client", None)

        if not isinstance(client_name, str):
            return "Configured LM client is not a string", None
        elif not client_name:
            return "No LM client configured", None

        if client_name not in LM_CLIENTS:
            return f"Unknown LM client '{client_name}' configured", None

        # Model of LM client
        model = self.get("model", None)

        if not isinstance(model, str):
            return "Configured model is not a string", None
        elif not model:
            return "No model configured", None

        client_class = get_lm_client_class(client_name)

        if not client_class:
            return f"Unknown LM client '{client_name}' configured", None

        if model not in client_class.get_available_models():
            return f"Configured model '{model}' is not available for client '{client_name}'", None

        # Api key
        api_key = ""

        if client_class.api_key_required():

            api_key = self.get_api_key(client_name)

            if not api_key:
                return f"API key is required for client '{client_name}'", None

        # Create client
        client = client_class(client_name, api_key)
        return None, client

    @staticmethod
    def from_anki_main_window(mw: AnkiQt) -> AddonConfig:

        addon_manager = mw.addonManager
        config_loader: Callable[[], Optional[dict[str, Any]]] = lambda: addon_manager.getConfig(__name__)
        config_saver: Callable[[dict[str, Any]], None] = lambda config: addon_manager.writeConfig(__name__, config)

        addon_config = AddonConfig(config_loader, config_saver)
        return addon_config
