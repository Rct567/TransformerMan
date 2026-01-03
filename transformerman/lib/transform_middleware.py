from __future__ import annotations

import hashlib
import sqlite3
import time
from abc import ABC, abstractmethod
from datetime import datetime
from typing import TYPE_CHECKING, TypeVar

from .lm_clients import LmResponse
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
    def before_transform(self, note_transformer: NoteTransformer) -> None:
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
    def before_transform(self, note_transformer: NoteTransformer) -> None:
        """Hook called before LM transformation."""
        if not self.log_enabled:
            return

        timestamp = datetime.now().isoformat()
        with self.log_file.open("w", encoding="utf-8") as f:
            f.write(f"=== REQUEST [{timestamp}] ===\n")
            f.write(f"{note_transformer.prompt}\n\n")

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


class CacheBatchMiddleware(Middleware):
    """Middleware for caching LM responses based on prompt, client ID, and model."""

    def __init__(self, addon_config: AddonConfig, user_files_dir: Path) -> None:
        """Initialize cache middleware."""

        self._addon_config = addon_config
        self._user_files_dir = user_files_dir

        self.cache_dir = self._user_files_dir / "cache"
        self.cache_file = self.cache_dir / "response_cache.sqlite"
        self._db_initialized = False
        self._num_cache_hits = 0

    @property
    def is_cache_enabled(self) -> bool:
        """Check if caching is enabled based on current config."""
        cache_setting = self._addon_config.get("cache_responses", False)
        return cache_setting is not False and cache_setting != 0

    @property
    def cache_limit(self) -> int:
        """Get the cache limit from current config."""
        cache_setting = self._addon_config.get("cache_responses", False)
        if isinstance(cache_setting, (int, float)):
            return int(cache_setting)
        return 100  # default if enabled but not specified

    @property
    def num_cache_hits(self) -> int:
        """Get the number of cache hits."""
        return self._num_cache_hits

    def _init_db(self) -> None:
        """Initialize the SQLite database and create table if needed."""
        with sqlite3.connect(self.cache_file) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cache (
                    id INTEGER PRIMARY KEY,
                    key_hash TEXT UNIQUE,
                    prompt TEXT,
                    client_id TEXT,
                    model TEXT,
                    response TEXT,
                    timestamp INTEGER
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_key_hash ON cache(key_hash)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON cache(timestamp)")

    def _get_cache_key(self, prompt: str, client_id: str, model: str) -> str:
        """Generate a cache key from prompt, client_id, and model."""
        key_data = f"{prompt}{client_id}{model}"
        return hashlib.sha256(key_data.encode("utf-8")).hexdigest()

    @override
    def before_transform(self, note_transformer: NoteTransformer) -> None:
        """Check cache before LM transformation."""
        if not self.is_cache_enabled:
            self._last_was_cache_hit = False
            return

        # Ensure DB is initialized
        if not self._db_initialized:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            self._init_db()
            self._db_initialized = True

        assert note_transformer.prompt and note_transformer.lm_client

        prompt = note_transformer.prompt
        client_id = note_transformer.lm_client.id
        model = note_transformer.lm_client.get_model()
        cache_key = self._get_cache_key(prompt, client_id, model)

        with sqlite3.connect(self.cache_file) as conn:
            cursor = conn.execute(
                "SELECT response FROM cache WHERE key_hash = ?",
                (cache_key,)
            )
            row = cursor.fetchone()

            if row:
                # Cache hit
                cached_response = row[0]
                note_transformer.response = LmResponse(cached_response)
                self._last_was_cache_hit = True
                self._num_cache_hits += 1
            else:
                # Cache miss
                self._last_was_cache_hit = False

    @override
    def after_transform(self, note_transformer: NoteTransformer) -> None:
        """Save response to cache after LM transformation."""
        if not self.is_cache_enabled:
            return

        # Check if this was a cache hit
        if self._last_was_cache_hit:
            return  # Don't save if it was from cache

        if note_transformer.response is None:
            return  # No response to cache

        # Get info from NoteTransformer
        prompt = note_transformer.prompt
        client_id = note_transformer.lm_client.id
        model = note_transformer.lm_client.get_model()
        cache_key = self._get_cache_key(prompt, client_id, model)

        with sqlite3.connect(self.cache_file) as conn:
            # Insert new cache entry
            conn.execute("""
                INSERT OR REPLACE INTO cache
                (key_hash, prompt, client_id, model, response, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                cache_key,
                prompt,
                client_id,
                model,
                note_transformer.response.content,
                int(time.time())
            ))

            # Enforce cache limit by deleting oldest entries
            if self.cache_limit > 0:
                conn.execute("""
                    DELETE FROM cache
                    WHERE id IN (
                        SELECT id FROM cache
                        ORDER BY timestamp DESC
                        LIMIT -1 OFFSET ?
                    )
                """, (self.cache_limit,))


T = TypeVar("T", bound=Middleware)


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

    def get(self, middleware_type: type[T]) -> T | None:
        """
        Get middleware by type.

        Args:
            middleware_type: The type/class of middleware to retrieve.

        Returns:
            Middleware instance if registered, None otherwise.
        """
        middleware = self._middleware.get(middleware_type)
        if isinstance(middleware, middleware_type):
            return middleware
        return None

    def before_transform(self, note_transformer: NoteTransformer) -> None:
        """
        Execute all middleware before LM transformation.

        Args:
            note_transformer: The note transformer used.
        """
        for middleware in self._middleware.values():
            middleware.before_transform(note_transformer)

    def after_transform(self, note_transformer: NoteTransformer) -> None:
        """
        Execute all middleware after LM transformation.

        Args:
            note_transformer: The note transformer used.
        """
        for middleware in self._middleware.values():
            middleware.after_transform(note_transformer)
