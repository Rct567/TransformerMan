from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import TYPE_CHECKING
from .utilities import override

if TYPE_CHECKING:
    from pathlib import Path
    from .addon_config import AddonConfig
    from .transform_operations import NoteTransformer


class Middleware(ABC):
    """Abstract base class for all middleware components."""

    @abstractmethod
    def __init__(self) -> None:
        """Initialize middleware."""

    @abstractmethod
    def before_transform(self, prompt: str, note_transformer: NoteTransformer) -> None:
        """Hook called before LM transformation."""

    @abstractmethod
    def after_transform(self, note_transformer: NoteTransformer) -> None:
        """Hook called after LM transformation."""


class LogLastRequestResponseMiddleware(Middleware):
    """Middleware for logging last LM request and response"""

    def __init__(self, addon_config: AddonConfig, user_files_dir: Path) -> None:
        """Initialize LM logging middleware."""

        self._addon_config = addon_config
        self._user_files_dir = user_files_dir

        self.log_enabled = self._addon_config.is_enabled("log_last_lm_response_request", False)
        self.logs_dir = self._user_files_dir / "logs"
        self.log_file = self.logs_dir / "last_lm_request_response.log"

        if self.log_enabled:
            self.logs_dir.mkdir(parents=True, exist_ok=True)

    @override
    def before_transform(self, prompt: str, note_transformer: NoteTransformer) -> None:
        """Hook called before LM transformation."""
        if not self.log_enabled:
            return

        timestamp = datetime.now().isoformat()
        with self.log_file.open("w", encoding="utf-8") as f:
            f.write(f"=== REQUEST [{timestamp}] ===\n")
            f.write(f"{prompt}\n\n")

    @override
    def after_transform(self, note_transformer: NoteTransformer) -> None:
        """Hook called after LM transformation."""
        if not self.log_enabled:
            return

        timestamp = datetime.now().isoformat()
        with self.log_file.open("a", encoding="utf-8") as f:
            f.write(f"=== RESPONSE [{timestamp}] ===\n")
            if note_transformer.response is None:
                f.write("No response...\n\n")
            else:
                f.write(f"{note_transformer.response.content}\n\n")


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

    def before_transform(self, prompt: str, note_transformer: NoteTransformer) -> None:
        """
        Execute all middleware before LM transformation.

        Args:
            prompt: The prompt to be sent to LM.
        """
        for middleware in self._middleware.values():
            middleware.before_transform(prompt, note_transformer)

    def after_transform(self, note_transformer: NoteTransformer) -> None:
        """
        Execute all middleware after LM transformation.

        Args:
            response: The response from LM.
        """
        for middleware in self._middleware.values():
            middleware.after_transform(note_transformer)
