"""
Tests for transform operations.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock


from transformerman.lib.transform_operations import NoteTransformer
from transformerman.lib.transform_middleware import LogLastRequestResponseMiddleware, CacheBatchMiddleware
from transformerman.lib.lm_clients import DummyLMClient, ApiKey, ModelName, LmResponse

from tests.tools import test_collection as test_collection_fixture

col = test_collection_fixture


if TYPE_CHECKING:
    from pathlib import Path
    from transformerman.lib.addon_config import AddonConfig


class TestLmLoggingMiddleware:
    """Test class for LmLoggingMiddleware."""

    def test_logging_disabled_does_not_create_files(
        self,
        addon_config: AddonConfig,
        user_files_dir: Path,
    ) -> None:
        """Test that middleware does not log when disabled."""
        middleware = LogLastRequestResponseMiddleware(addon_config, user_files_dir)

        # Call middleware hooks
        mock_note_transformer = MagicMock(spec=NoteTransformer)
        mock_note_transformer.response = LmResponse("")
        middleware.before_transform(mock_note_transformer)
        middleware.after_transform(mock_note_transformer)

        # Verify no files were created (since logging is disabled)
        logs_dir = user_files_dir / "logs"
        assert not logs_dir.exists()

    def test_logging_enabled_creates_files(
        self,
        addon_config: AddonConfig,
        user_files_dir: Path,
    ) -> None:
        """Test that middleware logs when enabled."""
        # Enable logging by updating config
        addon_config.update_setting("log_last_lm_response_request", True)

        middleware = LogLastRequestResponseMiddleware(addon_config, user_files_dir)

        # Call middleware hooks
        test_prompt = "test prompt"
        test_lm_response = LmResponse("test response")
        mock_note_transformer = MagicMock(spec=NoteTransformer)
        mock_note_transformer.response = test_lm_response
        mock_note_transformer.prompt = test_prompt

        middleware.before_transform(mock_note_transformer)
        middleware.after_transform(mock_note_transformer)

        # Verify files were created and contain expected content
        logs_dir = user_files_dir / "logs"
        assert logs_dir.exists()

        # Check log file
        log_file = logs_dir / "last_lm_request_response.log"
        assert log_file.exists()
        with log_file.open("r", encoding="utf-8") as f:
            content = f.read()
            assert "=== REQUEST" in content
            assert test_prompt in content
            assert "=== RESPONSE" in content
            assert test_lm_response.content in content


class TestCacheBatchMiddleware:
    """Test class for CacheBatchMiddleware."""

    def test_caching_disabled_does_not_create_files(
        self,
        addon_config: AddonConfig,
        user_files_dir: Path,
    ) -> None:
        """Test that middleware does not cache when disabled."""
        middleware = CacheBatchMiddleware(addon_config, user_files_dir)

        # Call middleware hooks
        mock_note_transformer = MagicMock(spec=NoteTransformer)
        mock_lm_client = MagicMock()
        mock_lm_client.id = "dummy"
        mock_lm_client.get_model.return_value = "test_model"
        mock_note_transformer.lm_client = mock_lm_client
        mock_note_transformer.response = LmResponse("test response")

        middleware.before_transform(mock_note_transformer)
        middleware.after_transform(mock_note_transformer)

        # Verify no files were created (since caching is disabled)
        cache_dir = user_files_dir / "cache"
        assert not cache_dir.exists()

        # Verify no cache hits occurred
        assert middleware.num_cache_hits == 0

    def test_caching_enabled_caches_and_hits(
        self,
        addon_config: AddonConfig,
        user_files_dir: Path,
    ) -> None:
        """Test that middleware caches responses and serves cache hits."""
        # Enable caching by updating config
        addon_config.update_setting("cache_responses", 100)

        middleware = CacheBatchMiddleware(addon_config, user_files_dir)

        # Use real DummyLMClient
        dummy_client = DummyLMClient(ApiKey(""), ModelName("lorem_ipsum"))

        # Create minimal test objects with required attributes
        class MockNoteTransformer:  # noqa: B903
            def __init__(self, lm_client: DummyLMClient, prompt: str, response: LmResponse | None = None) -> None:
                self.lm_client = lm_client
                self.prompt = prompt
                self.response = response

        # First call - should cache the response
        note_transformer1 = MockNoteTransformer(dummy_client, "test prompt", None)
        middleware.before_transform(note_transformer1)  # type: ignore
        assert note_transformer1.response is None  # Should not be set (cache miss)

        # Simulate LM response
        note_transformer1.response = LmResponse("Lorem ipsum dolor sit amet, consectetur adipiscing elit.")
        middleware.after_transform(note_transformer1)  # type: ignore

        # Verify cache file was created
        cache_dir = user_files_dir / "cache"
        assert cache_dir.exists()
        cache_file = cache_dir / "response_cache.sqlite"
        assert cache_file.exists()

        # Second call - should hit cache
        note_transformer2 = MockNoteTransformer(dummy_client, "test prompt", None)
        middleware.before_transform(note_transformer2)  # type: ignore
        assert note_transformer2.response is not None  # Should be set (cache hit)
        assert note_transformer2.response.content == "Lorem ipsum dolor sit amet, consectetur adipiscing elit."
        middleware.after_transform(note_transformer2)  # type: ignore

        # Verify cache hit counter
        assert middleware.num_cache_hits == 1
