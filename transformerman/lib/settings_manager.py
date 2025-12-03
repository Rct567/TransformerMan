"""
TransformerMan by Rick Zuidhoek. Licensed under the GNU GPL-3.0.
See <https://www.gnu.org/licenses/gpl-3.0.html> for details.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .addon_config import AddonConfig


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
        # For now, return a static list
        # In the future, this could be fetched from an API
        return [
            "claude-v1.3-100k",
            "gpt-4",
            "gpt-3.5-turbo",
            "grok-1",
        ]
