from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import TYPE_CHECKING
from .utilities import override

if TYPE_CHECKING:
    from pathlib import Path
    from .addon_config import AddonConfig
    from .lm_clients import LmResponse


class Middleware(ABC):
    """Abstract base class for all middleware components."""

    @abstractmethod
    def __init__(self) -> None:
        """Initialize middleware."""

    @abstractmethod
    def before_transform(self, prompt: str) -> None:
        """
        Hook called before LM transformation.

        Args:
            prompt: The prompt to be sent to LM.
        """

    @abstractmethod
    def after_transform(self, response: LmResponse) -> None:
        """
        Hook called after LM transformation.

        Args:
            response: The response from LM.
        """


class LmLoggingMiddleware(Middleware):
    """Middleware for logging LM requests and responses."""

    def __init__(self, addon_config: AddonConfig, user_files_dir: Path) -> None:
        """
        Initialize LM logging middleware.

        Args:
            addon_config: Addon configuration.
            user_files_dir: Directory for user files.
        """

        self._addon_config = addon_config
        self._user_files_dir = user_files_dir

        self.log_requests_enabled = self._addon_config.is_enabled("log_lm_requests", False)
        self.log_responses_enabled = self._addon_config.is_enabled("log_lm_responses", False)

        self.logs_dir = self._user_files_dir / "logs"

        if self.log_requests_enabled or self.log_responses_enabled:
            self.logs_dir.mkdir(parents=True, exist_ok=True)

    def _log_request(self, prompt: str) -> None:
        if self.log_requests_enabled:
            requests_file = self.logs_dir / "lm_requests.log"
            timestamp = datetime.now().isoformat()
            with requests_file.open("a", encoding="utf-8") as f:
                f.write(f"[{timestamp}] {prompt}\n\n")

    def _log_response(self, response: LmResponse) -> None:
        if self.log_responses_enabled:
            responses_file = self.logs_dir / "lm_responses.log"
            timestamp = datetime.now().isoformat()
            with responses_file.open("a", encoding="utf-8") as f:
                f.write(f"[{timestamp}] {response.content}\n\n")

    @override
    def before_transform(self, prompt: str) -> None:
        """Hook called before LM transformation."""
        self._log_request(prompt)

    @override
    def after_transform(self, response: LmResponse) -> None:
        """Hook called after LM transformation."""
        self._log_response(response)


class TransformMiddleware:
    """Registry for transform operation middleware."""

    def __init__(self) -> None:
        """Initialize transform middleware registry."""
        self._middleware: dict[type, Middleware] = {}

    def register(self, middleware: Middleware) -> None:
        """
        Register middleware.

        Args:
            middleware: Middleware instance.
        """
        self._middleware[type(middleware)] = middleware

    def get(self, middleware_type: type[Middleware]) -> Middleware | None:
        """
        Get middleware by type.

        Args:
            middleware_type: The type/class of middleware to retrieve.

        Returns:
            Middleware instance if registered, None otherwise.
        """
        return self._middleware.get(middleware_type)

    def before_transform(self, prompt: str) -> None:
        """
        Execute all middleware before LM transformation.

        Args:
            prompt: The prompt to be sent to LM.
        """
        for middleware in self._middleware.values():
            middleware.before_transform(prompt)

    def after_transform(self, response: LmResponse) -> None:
        """
        Execute all middleware after LM transformation.

        Args:
            response: The response from LM.
        """
        for middleware in self._middleware.values():
            middleware.after_transform(response)
