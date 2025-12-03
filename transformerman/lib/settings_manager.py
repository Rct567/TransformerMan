"""
TransformerMan by Rick Zuidhoek. Licensed under the GNU GPL-3.0.
See <https://www.gnu.org/licenses/gpl-3.0.html> for details.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .addon_config import AddonConfig
from .lm_clients import LM_CLIENTS, create_lm_client


class SettingsManager:
    """Manages plugin settings."""

    def __init__(self, config: AddonConfig) -> None:
        """
        Initialize settings manager.

        Args:
            config: The addon configuration object.
        """
        self.config = config

    def get_api_key(self) -> str:
        """
        Get the API key for the LM service.

        Returns:
            API key string.
        """
        return str(self.config.get("api_key", ""))

    def set_api_key(self, api_key: str) -> None:
        """
        Set the API key for the LM service.

        Args:
            api_key: The API key to set.
        """
        self.config.update_setting("api_key", api_key)

    def get_lm_client_name(self) -> str:
        return str(self.config.get("lm_client", "dummy"))

    def set_lm_client_name(self, client_name: str) -> None:
        self.config.update_setting("lm_client", client_name)

    def get_model(self) -> str:
        """
        Get the selected LM model.

        Returns:
            Model name string.
        """
        return str(self.config.get("model", "claude-v1.3-100k"))

    def set_model(self, model: str) -> None:
        """
        Set the LM model.

        Args:
            model: The model name to set.
        """
        self.config.update_setting("model", model)

    def get_batch_size(self) -> int:
        """
        Get the batch size for processing notes.

        Returns:
            Batch size as integer.
        """
        batch_size = self.config.get("batch_size", 10)
        if isinstance(batch_size, int):
            return batch_size
        return 10

    def set_batch_size(self, batch_size: int) -> None:
        """
        Set the batch size for processing notes.

        Args:
            batch_size: The batch size to set.
        """
        if batch_size < 1:
            batch_size = 1
        self.config.update_setting("batch_size", batch_size)

    def get_available_models(self) -> list[str]:
        """
        Get list of available LM models.

        Returns:
            List of model names.
        """
        client = create_lm_client(self.get_lm_client_name())
        return client.get_available_models()

    def get_available_clients(self) -> list[str]:
        return list(LM_CLIENTS.keys())

    def get_available_models_for_client(self, client_name: str) -> list[str]:
        client = create_lm_client(client_name)
        return client.get_available_models()
