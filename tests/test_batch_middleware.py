"""
Tests for transform operations.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from transformerman.lib.transform_operations import NoteTransformer
from transformerman.lib.transform_middleware import LogLastRequestResponseMiddleware, CacheBatchMiddleware, TransformMiddleware
from transformerman.lib.lm_clients import DummyLMClient, ApiKey, ModelName
from transformerman.lib.selected_notes import NoteModel, SelectedNotes, SelectedNotesFromType
from transformerman.lib.prompt_builder import PromptBuilder
from transformerman.ui.field_widgets import FieldSelection

from tests.tools import test_collection as test_collection_fixture, with_test_collection, TestCollection

col = test_collection_fixture


if TYPE_CHECKING:
    from pathlib import Path
    from anki.notes import NoteId
    from collections.abc import Sequence
    from transformerman.lib.addon_config import AddonConfig


def create_test_notes_with_empty_front(col: TestCollection, count: int = 2, back_content_prefix: str = "existing content") -> list[NoteId]:
    """Get existing test notes and modify them to have empty Front fields for transformation testing."""
    # Find existing notes
    existing_note_ids = col.find_notes("")
    assert len(existing_note_ids) >= count, f"Need at least {count} existing notes, found {len(existing_note_ids)}"

    note_ids = []
    for i in range(count):
        note_id = existing_note_ids[i]
        note = col.get_note(note_id)
        note["Front"] = ""  # Empty field to transform
        note["Back"] = f"{back_content_prefix} {i}" if count > 1 else back_content_prefix
        col.update_note(note)
        note_ids.append(note.id)

    return note_ids


def create_standard_transform_dependencies(
    col: TestCollection, note_ids: Sequence[NoteId]
) -> tuple[SelectedNotesFromType, DummyLMClient, PromptBuilder, FieldSelection]:
    """Create standard dependencies needed for NoteTransformer."""
    selected_notes = SelectedNotes(col, note_ids)
    dummy_client = DummyLMClient(ApiKey(""), ModelName("lorem_ipsum"))
    prompt_builder = PromptBuilder(col)
    field_selection = FieldSelection(
        selected=["Front", "Back"],
        writable=["Front"],
        overwritable=[],
    )
    note_type = NoteModel.by_name(col, "Basic")
    assert note_type
    return selected_notes.filter_by_note_type(note_type), dummy_client, prompt_builder, field_selection


class TestLmLoggingMiddleware:
    """Test class for LmLoggingMiddleware."""

    @with_test_collection("two_deck_collection")
    def test_logging_disabled_does_not_create_files(
        self,
        col: TestCollection,
        addon_config: AddonConfig,
        user_files_dir: Path,
    ) -> None:
        """Test that middleware does not log when disabled."""
        # Create test notes and dependencies
        note_ids = create_test_notes_with_empty_front(col)
        selected_notes, dummy_client, prompt_builder, field_selection = create_standard_transform_dependencies(col, note_ids)

        # Create middleware and register it
        middleware = LogLastRequestResponseMiddleware(addon_config, user_files_dir)
        transform_middleware = TransformMiddleware()
        transform_middleware.register(middleware)

        # Create and run NoteTransformer
        transformer = NoteTransformer(
            col=col,
            selected_notes=selected_notes,
            lm_client=dummy_client,
            prompt_builder=prompt_builder,
            field_selection=field_selection,
            addon_config=addon_config,
            transform_middleware=transform_middleware,
        )
        results, _field_updates = transformer.get_field_updates()

        # Verify transform succeeded
        assert results.num_notes_updated == 2
        assert transformer.prompt is not None
        assert transformer.response is not None

        # Verify no files were created (since logging is disabled)
        logs_dir = user_files_dir / "logs"
        assert not logs_dir.exists()

    @with_test_collection("two_deck_collection")
    def test_logging_enabled_creates_files(
        self,
        col: TestCollection,
        addon_config: AddonConfig,
        user_files_dir: Path,
    ) -> None:
        """Test that middleware logs when enabled."""
        # Enable logging by updating config
        addon_config.update_setting("log_last_lm_response_request", True)

        # Create test notes and dependencies
        note_ids = create_test_notes_with_empty_front(col)
        selected_notes, dummy_client, prompt_builder, field_selection = create_standard_transform_dependencies(col, note_ids)

        # Create middleware and register it
        middleware = LogLastRequestResponseMiddleware(addon_config, user_files_dir)
        transform_middleware = TransformMiddleware()
        transform_middleware.register(middleware)

        # Create and run NoteTransformer
        transformer = NoteTransformer(
            col=col,
            selected_notes=selected_notes,
            lm_client=dummy_client,
            prompt_builder=prompt_builder,
            field_selection=field_selection,
            addon_config=addon_config,
            transform_middleware=transform_middleware,
        )
        results, _field_updates = transformer.get_field_updates()

        # Verify transform succeeded
        assert results.num_notes_updated == 2
        assert transformer.prompt is not None
        assert transformer.response is not None

        # Verify files were created and contain expected content
        logs_dir = user_files_dir / "logs"
        assert logs_dir.exists()

        # Check log file
        log_file = logs_dir / "last_lm_request_response.log"
        assert log_file.exists()
        with log_file.open("r", encoding="utf-8") as f:
            content = f.read()
            assert "=== REQUEST" in content
            assert transformer.prompt in content
            assert "=== RESPONSE" in content
            assert transformer.response.content in content


class TestCacheBatchMiddleware:
    """Test class for CacheBatchMiddleware."""

    @with_test_collection("two_deck_collection")
    def test_caching_disabled_does_not_create_files(
        self,
        col: TestCollection,
        addon_config: AddonConfig,
        user_files_dir: Path,
    ) -> None:
        """Test that middleware does not cache when disabled."""
        # Create test notes and dependencies
        note_ids = create_test_notes_with_empty_front(col)
        selected_notes, dummy_client, prompt_builder, field_selection = create_standard_transform_dependencies(col, note_ids)

        # Create middleware and register it (caching disabled by default)
        middleware = CacheBatchMiddleware(addon_config, user_files_dir)
        transform_middleware = TransformMiddleware()
        transform_middleware.register(middleware)

        # Create and run NoteTransformer
        transformer = NoteTransformer(
            col=col,
            selected_notes=selected_notes,
            lm_client=dummy_client,
            prompt_builder=prompt_builder,
            field_selection=field_selection,
            addon_config=addon_config,
            transform_middleware=transform_middleware,
        )
        results, _field_updates = transformer.get_field_updates()

        # Verify transform succeeded
        assert results.num_notes_updated == 2
        assert transformer.prompt is not None
        assert transformer.response is not None

        # Verify no files were created (since caching is disabled)
        cache_dir = user_files_dir / "cache"
        assert not cache_dir.exists()

        # Verify no cache hits occurred
        assert middleware.num_cache_hits == 0

    @with_test_collection("two_deck_collection")
    def test_caching_enabled_caches_and_hits(
        self,
        col: TestCollection,
        addon_config: AddonConfig,
        user_files_dir: Path,
    ) -> None:
        """Test that middleware caches responses and serves cache hits."""
        # Enable caching by updating config
        addon_config.update_setting("cache_responses", 100)

        # Create test notes and dependencies
        note_ids = create_test_notes_with_empty_front(col)
        selected_notes, dummy_client, prompt_builder, field_selection = create_standard_transform_dependencies(col, note_ids)

        # Create middleware and register it
        middleware = CacheBatchMiddleware(addon_config, user_files_dir)
        transform_middleware = TransformMiddleware()
        transform_middleware.register(middleware)

        # Create NoteTransformer
        transformer = NoteTransformer(
            col=col,
            selected_notes=selected_notes,
            lm_client=dummy_client,
            prompt_builder=prompt_builder,
            field_selection=field_selection,
            addon_config=addon_config,
            transform_middleware=transform_middleware,
        )

        # First call - run transform to populate cache
        results1, _ = transformer.get_field_updates()

        # Verify first transform succeeded
        assert results1.num_notes_updated == 2
        assert transformer.prompt is not None
        assert transformer.response is not None

        # Verify cache file was created
        cache_dir = user_files_dir / "cache"
        assert cache_dir.exists()
        cache_file = cache_dir / "response_cache.sqlite"
        assert cache_file.exists()

        # Reset notes to empty for second call (to test cache hit)
        for note_id in note_ids:
            note = col.get_note(note_id)
            note["Front"] = ""  # Reset to empty
        col.update_notes([col.get_note(nid) for nid in note_ids])

        # Second call - run transform again on same instance (should hit cache)
        results2, _ = transformer.get_field_updates()

        # Verify second transform succeeded via cache
        assert results2.num_notes_updated == 2
        # Same prompt should have been generated
        assert transformer.prompt is not None
        assert transformer.response is not None

        # Verify cache hit occurred
        assert middleware.num_cache_hits == 1
