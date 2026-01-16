"""
Shared fixtures for all tests.

This module provides common test fixtures available to all test modules.
Follows project guideline: "Use pytest fixtures, but try to use the real thing where possible (it often is)"
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Generic, TypeVar
import pytest

from transformerman.lib.addon_config import AddonConfig

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path
    from transformerman.lib.utilities import JSON_TYPE


@pytest.fixture
def user_files_dir(tmp_path: Path) -> Path:
    """Temporary directory for user files."""
    return tmp_path / "user_files"


@pytest.fixture
def addon_config() -> AddonConfig:
    """
    Real AddonConfig for tests.

    Returns a real AddonConfig instance with in-memory storage for testing.
    """
    saved_config: dict[str, JSON_TYPE] = {
        "lm_client": "dummy",
        "dummy_model": "lorem_ipsum",
        "batch_size": 10,
        "log_last_lm_response_request": False,
        "max_prompt_size": 500000,
        "dummy_api_key": "test-api-key",
    }

    def loader() -> dict[str, JSON_TYPE]:
        return saved_config.copy()

    def saver(config: dict[str, JSON_TYPE]) -> None:
        saved_config.clear()
        saved_config.update(config)

    config = AddonConfig(loader, saver)
    config.load()
    return config


T = TypeVar("T")


class FakeQueryOp(Generic[T]):
    """Synchronous QueryOp for testing."""

    def __init__(
        self,
        *,
        parent: Any,
        op: Callable[[Any], T],
        success: Callable[[T], Any],
    ) -> None:
        self._op = op
        self._success = success
        self._parent = parent
        self._failure: Callable[[Exception], Any] | None = None

    def failure(self, failure: Callable[[Exception], Any] | None) -> FakeQueryOp[T]:
        self._failure = failure
        return self

    def without_collection(self) -> FakeQueryOp[T]:
        return self

    def with_progress(self, label: str | None = None) -> FakeQueryOp[T]:
        return self

    def with_backend_progress(self, progress_update: Any) -> FakeQueryOp[T]:
        return self

    def run_in_background(self) -> None:
        """Run synchronously instead of in background."""
        try:
            # Try to get collection from parent or mw
            col = getattr(self._parent, "col", None)
            if col is None:
                from aqt import mw  # noqa: PLC0415

                col = getattr(mw, "col", None)

            result = self._op(col)
            self._success(result)
        except Exception as e:
            if self._failure:
                self._failure(e)
            else:
                raise
