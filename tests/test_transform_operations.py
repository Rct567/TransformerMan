"""
Tests for transform operations.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional, cast
from unittest.mock import Mock, MagicMock, patch
import pytest

from transformerman.lib.transform_operations import NoteTransformer
from transformerman.ui.transform_notes import apply_field_updates_with_operation
from transformerman.lib.transform_middleware import LogLastRequestResponseMiddleware, TransformMiddleware
from transformerman.lib.selected_notes import SelectedNotes
from transformerman.lib.lm_clients import DummyLMClient, ApiKey, ModelName, LmResponse
from transformerman.lib.prompt_builder import PromptBuilder
from transformerman.lib.field_updates import FieldUpdates
from transformerman.ui.field_widgets import FieldSelection
from tests.tools import test_collection as test_collection_fixture, with_test_collection, TestCollection, mock_collection_op

col = test_collection_fixture


if TYPE_CHECKING:
    from anki.notes import NoteId
    from pathlib import Path
    from transformerman.lib.addon_config import AddonConfig
    from transformerman.lib.http_utils import LmProgressData


@pytest.fixture
def mock_user_files_dir(tmp_path: Path) -> Path:
    """Create a temporary directory for user files."""
    return tmp_path


@pytest.fixture
def transform_middleware(addon_config: AddonConfig, mock_user_files_dir: Path) -> TransformMiddleware:
    """Create a TransformMiddleware with LmLoggingMiddleware for testing."""
    middleware = TransformMiddleware()
    lm_logging = LogLastRequestResponseMiddleware(addon_config, mock_user_files_dir)
    middleware.register(lm_logging)
    return middleware


class TestNoteTransformer:
    """Test class for NoteTransformer."""

    @with_test_collection("two_deck_collection")
    def test_init_validates_notes_with_empty_fields(
        self,
        col: TestCollection,
        addon_config: AddonConfig,
        transform_middleware: TransformMiddleware,
    ) -> None:
        """Test that __init__ validates notes have empty fields."""
        # Get real note IDs from the collection (all have non-empty fields)
        note_ids = col.find_notes("")
        # Use a real SelectedNotes instance with those note IDs
        selected_notes = SelectedNotes(col, note_ids)

        # Create a real DummyLMClient
        dummy_client = DummyLMClient(ApiKey(""), ModelName("lorem_ipsum"))

        # Create a real PromptBuilder
        prompt_builder = PromptBuilder(col)

        # The collection's notes have no empty fields in "Front" or "Back"
        # So validation should raise ValueError
        with pytest.raises(ValueError, match="No notes with empty writable fields found"):
            NoteTransformer(
                col=col,
                selected_notes=selected_notes,
                note_ids=note_ids,
                lm_client=dummy_client,
                prompt_builder=prompt_builder,
                field_selection=FieldSelection(
                    selected=["Front"],  # Field that exists and is non-empty
                    writable=["Front"],
                    overwritable=[],
                ),
                note_type_name="Basic",
                addon_config=addon_config,
                transform_middleware=transform_middleware,
            )

    @with_test_collection("two_deck_collection")
    def test_get_field_updates_returns_correct_updates(
        self,
        col: TestCollection,
        addon_config: AddonConfig,
        transform_middleware: TransformMiddleware,
    ) -> None:
        """Test that get_field_updates returns correct field updates in preview mode."""
        addon_config.update_setting("max_examples", 3)
        addon_config.update_setting("max_prompt_size", 1000)
        # Create 4 new notes with empty fields
        model = col.models.by_name("Basic")
        assert model is not None
        deck = col.decks.all()[0]
        deck_id = deck["id"]

        note_ids = []
        for _ in range(4):
            note = col.new_note(model)
            note["Front"] = ""  # Empty field
            note["Back"] = "some back"
            col.add_note(note, deck_id)
            note_ids.append(note.id)

        # Use real SelectedNotes instance
        selected_notes = SelectedNotes(col, note_ids)

        # Create a real DummyLMClient
        dummy_client = DummyLMClient(ApiKey(""), ModelName("lorem_ipsum"))

        # Create a real PromptBuilder
        prompt_builder = PromptBuilder(col)

        # Create NoteTransformer with max prompt size of 1000
        transformer = NoteTransformer(
            col=col,
            selected_notes=selected_notes,
            note_ids=note_ids,
            lm_client=dummy_client,
            prompt_builder=prompt_builder,
            field_selection=FieldSelection(
                selected=["Front"],
                writable=["Front"],
                overwritable=[],
            ),
            note_type_name="Basic",
            addon_config=addon_config,
            transform_middleware=transform_middleware,
        )

        # Get field updates (preview mode)
        results, field_updates = transformer.get_field_updates()

        # Verify results
        assert results.num_notes_updated == 4  # All 4 notes should have updates
        assert results.num_notes_failed == 0
        assert results.num_batches_processed == 3
        assert results.error is None

        # Verify field updates contain expected content
        assert len(field_updates) == 4
        for nid in note_ids:
            assert nid in field_updates
            assert "Front" in field_updates[nid]
            assert field_updates[nid]["Front"] == "Lorem ipsum dolor sit amet, consectetur adipiscing elit."

        # Verify notes were NOT updated in the collection (preview mode)
        for nid in note_ids:
            note = col.get_note(nid)
            # Should still be empty (preview mode doesn't apply updates)
            assert note["Front"] == ""
            # Back field unchanged
            assert note["Back"] == "some back"

    @with_test_collection("two_deck_collection")
    def test_get_field_updates_with_progress_callback(
        self,
        col: TestCollection,
        addon_config: AddonConfig,
        transform_middleware: TransformMiddleware,
    ) -> None:
        """Test that get_field_updates calls progress callback."""
        # Create 4 new notes with empty fields
        model = col.models.by_name("Basic")
        assert model is not None
        deck = col.decks.all()[0]
        deck_id = deck["id"]

        note_ids = []
        for _ in range(4):
            note = col.new_note(model)
            note["Front"] = ""  # Empty field
            note["Back"] = "some back"
            col.add_note(note, deck_id)
            note_ids.append(note.id)

        # Use real SelectedNotes instance
        selected_notes = SelectedNotes(col, note_ids)

        # Create a real DummyLMClient
        dummy_client = DummyLMClient(ApiKey(""), ModelName("lorem_ipsum"))

        # Create a real PromptBuilder
        prompt_builder = PromptBuilder(col)

        # Create NoteTransformer with max prompt size
        transformer = NoteTransformer(
            col=col,
            selected_notes=selected_notes,
            note_ids=note_ids,
            lm_client=dummy_client,
            prompt_builder=prompt_builder,
            field_selection=FieldSelection(
                selected=["Front"],
                writable=["Front"],
                overwritable=[],
            ),
            note_type_name="Basic",
            addon_config=addon_config,
            transform_middleware=transform_middleware,
        )

        # Track progress calls
        progress_calls = []

        def progress_callback(current: int, total: int, _: Optional[LmProgressData] = None) -> None:
            progress_calls.append((current, total))

        # Get field updates with progress callback
        transformer.get_field_updates(progress_callback=progress_callback)

        # Verify progress was reported (only 1 batch with 500k limit)
        # With streaming, we expect multiple calls: first batch, multiple streaming updates, and completion
        assert len(progress_calls) >= 2
        assert progress_calls[0] == (0, 1)  # First batch
        assert progress_calls[-1] == (1, 1)  # Completion

    @with_test_collection("two_deck_collection")
    def test_get_field_updates_with_cancellation(
        self,
        col: TestCollection,
        addon_config: AddonConfig,
        transform_middleware: TransformMiddleware,
    ) -> None:
        """Test that get_field_updates respects cancellation."""
        # Create 4 new notes with empty fields
        model = col.models.by_name("Basic")
        assert model is not None
        deck = col.decks.all()[0]
        deck_id = deck["id"]

        note_ids = []
        for _ in range(4):
            note = col.new_note(model)
            note["Front"] = ""  # Empty field
            note["Back"] = "some back"
            col.add_note(note, deck_id)
            note_ids.append(note.id)

        # Use real SelectedNotes instance
        selected_notes = SelectedNotes(col, note_ids)

        # Create a real DummyLMClient
        dummy_client = DummyLMClient(ApiKey(""), ModelName("lorem_ipsum"))

        # Create a real PromptBuilder
        prompt_builder = PromptBuilder(col)

        # Create NoteTransformer with max prompt size
        transformer = NoteTransformer(
            col=col,
            selected_notes=selected_notes,
            note_ids=note_ids,
            lm_client=dummy_client,
            prompt_builder=prompt_builder,
            field_selection=FieldSelection(
                selected=["Front"],
                writable=["Front"],
                overwritable=[],
            ),
            note_type_name="Basic",
            addon_config=addon_config,
            transform_middleware=transform_middleware,
        )

        # Cancel immediately (before processing)
        def should_cancel() -> bool:
            return True  # Cancel immediately

        # Get field updates with cancellation
        results, field_updates = transformer.get_field_updates(should_cancel=should_cancel)

        # Verify no batches were processed due to immediate cancellation
        assert results.num_batches_processed == 0
        # No notes should have updates due to cancellation
        assert len(field_updates) == 0

        # Verify that no notes have updates
        for nid in note_ids:
            assert nid not in field_updates

    @with_test_collection("two_deck_collection")
    def test_get_field_updates_handles_batch_errors(
        self,
        col: TestCollection,
        addon_config: AddonConfig,
        transform_middleware: TransformMiddleware,
    ) -> None:
        """Test that get_field_updates handles batch processing errors gracefully."""
        # Create 4 new notes with empty fields
        model = col.models.by_name("Basic")
        assert model is not None
        deck = col.decks.all()[0]
        deck_id = deck["id"]

        note_ids = []
        for _ in range(4):
            note = col.new_note(model)
            note["Front"] = ""  # Empty field
            note["Back"] = "some back"
            col.add_note(note, deck_id)
            note_ids.append(note.id)

        # Use real SelectedNotes instance
        selected_notes = SelectedNotes(col, note_ids)

        # Create a real PromptBuilder
        prompt_builder = PromptBuilder(col)

        # Create a real DummyLMClient
        dummy_client = DummyLMClient(ApiKey(""), ModelName("lorem_ipsum"))

        # Mock transform to return a response with missing field updates
        mock_response = MagicMock(spec=LmResponse)
        mock_response.get_notes_from_xml.return_value = {}  # Return empty dict to trigger missing updates error
        mock_response.text_response = "<xml>empty</xml>"
        mock_response.error = None
        mock_response.is_canceled = False

        # Create NoteTransformer with max prompt size
        transformer = NoteTransformer(
            col=col,
            selected_notes=selected_notes,
            note_ids=note_ids,
            lm_client=dummy_client,
            prompt_builder=prompt_builder,
            field_selection=FieldSelection(
                selected=["Front"],
                writable=["Front"],
                overwritable=[],
            ),
            note_type_name="Basic",
            addon_config=addon_config,
            transform_middleware=transform_middleware,
        )

        # Get field updates with mocked transform
        with patch.object(dummy_client, "transform", return_value=mock_response):
            results, field_updates = transformer.get_field_updates()

        # Verify results show failures for all notes (all in one batch that failed)
        assert results.num_batches_processed == 1  # Only one batch attempted
        assert results.error is not None
        assert "4 field updates appear to be missing" in results.error

        # Verify that no notes have updates (batch failed)
        assert len(field_updates) == 0
        for nid in note_ids:
            assert nid not in field_updates

    @with_test_collection("two_deck_collection")
    def test_get_field_updates_only_returns_updates_for_empty_fields(
        self,
        col: TestCollection,
        addon_config: AddonConfig,
        transform_middleware: TransformMiddleware,
    ) -> None:
        """Test that get_field_updates only returns updates for empty fields."""
        # Create 4 new notes with mixed empty/non-empty fields
        model = col.models.by_name("Basic")
        assert model is not None
        deck = col.decks.all()[0]
        deck_id = deck["id"]

        note_ids = []
        for i in range(4):
            note = col.new_note(model)
            if i < 2:
                note["Front"] = ""  # Empty field
            else:
                note["Front"] = "Already filled"  # Non-empty field
            note["Back"] = "some back"
            col.add_note(note, deck_id)
            note_ids.append(note.id)

        # Use real SelectedNotes instance
        selected_notes = SelectedNotes(col, note_ids)

        # Create a real DummyLMClient
        dummy_client = DummyLMClient(ApiKey(""), ModelName("lorem_ipsum"))

        # Create a real PromptBuilder
        prompt_builder = PromptBuilder(col)

        # Create NoteTransformer with max prompt size
        transformer = NoteTransformer(
            col=col,
            selected_notes=selected_notes,
            note_ids=note_ids,
            lm_client=dummy_client,
            prompt_builder=prompt_builder,
            field_selection=FieldSelection(
                selected=["Front"],
                writable=["Front"],
                overwritable=[],
            ),
            note_type_name="Basic",
            addon_config=addon_config,
            transform_middleware=transform_middleware,
        )

        # Get field updates
        results, field_updates = transformer.get_field_updates()

        # Verify only empty fields have updates
        assert results.num_notes_updated == 2  # Only first 2 notes (empty fields)
        assert results.num_notes_failed == 0
        # Only one batch (notes with empty fields) - notes with non-empty fields are filtered out
        assert results.num_batches_processed == 1

        # Verify that only empty fields have updates
        assert len(field_updates) == 2
        for i, nid in enumerate(note_ids):
            if i < 2:
                # Empty field should have update
                assert nid in field_updates
                assert field_updates[nid]["Front"] == "Lorem ipsum dolor sit amet, consectetur adipiscing elit."
            else:
                # Non-empty field should not have update
                assert nid not in field_updates


class TestApplyFieldUpdatesWithOperation:
    """Test class for apply_field_updates_with_operation function."""

    @with_test_collection("two_deck_collection")
    def test_apply_field_updates_with_operation_applies_updates(
        self,
        col: TestCollection,
    ) -> None:
        """Test that apply_field_updates_with_operation applies field updates."""
        # Create 4 new notes with empty fields
        model = col.models.by_name("Basic")
        assert model is not None
        deck = col.decks.all()[0]
        deck_id = deck["id"]

        note_ids = []
        for i in range(4):
            note = col.new_note(model)
            note["Front"] = ""  # Empty field
            note["Back"] = f"back {i}"
            col.add_note(note, deck_id)
            note_ids.append(note.id)

        # Create field updates to apply
        field_updates = FieldUpdates({
            note_ids[0]: {"Front": "Updated content 1"},
            note_ids[1]: {"Front": "Updated content 2"},
            note_ids[2]: {"Front": "Updated content 3"},
            note_ids[3]: {"Front": "Updated content 4"},
        })

        # Mock logger
        logger = Mock()

        # Track success callback
        success_results = []

        def on_success(results: dict[str, int]) -> None:
            success_results.append(results)

        # Mock parent widget
        parent = Mock()

        # Mock CollectionOp to update notes synchronously using the context manager
        with mock_collection_op(col) as MockCollectionOp:
            # Apply field updates
            apply_field_updates_with_operation(
                parent=parent,
                col=col,
                field_updates=field_updates,
                logger=logger,
                on_success=on_success,
            )

            # Verify CollectionOp was called
            assert MockCollectionOp.called, "CollectionOp was not called"
            # Verify it was called with the right arguments
            assert MockCollectionOp.call_args[0][0] is parent
            # The second argument should be a lambda that calls col.update_notes

        # Verify notes were updated in the collection
        for i, nid in enumerate(note_ids):
            note = col.get_note(nid)
            assert note["Front"] == f"Updated content {i+1}"
            assert note["Back"] == f"back {i}"

        # Verify success callback was called
        assert len(success_results) == 1
        assert success_results[0]["updated"] == 4
        assert success_results[0]["failed"] == 0

    @with_test_collection("two_deck_collection")
    def test_apply_field_updates_with_operation_handles_nonexistent_fields(
        self,
        col: TestCollection,
    ) -> None:
        """Test that apply_field_updates_with_operation handles nonexistent fields."""
        # Create a new note
        model = col.models.by_name("Basic")
        assert model is not None
        deck = col.decks.all()[0]
        deck_id = deck["id"]

        note = col.new_note(model)
        note["Front"] = ""  # Empty field
        note["Back"] = "back"
        col.add_note(note, deck_id)

        # Create field updates with nonexistent field
        field_updates = FieldUpdates({
            note.id: {
                "Front": "Updated content",  # Valid field
                "NonexistentField": "Some content",  # Nonexistent field
            }
        })

        # Mock logger
        logger = Mock()

        # Track success callback
        success_results = []

        def on_success(results: dict[str, int]) -> None:
            success_results.append(results)

        # Mock parent widget
        parent = Mock()

        # Mock CollectionOp to update notes synchronously using the context manager
        with mock_collection_op(col) as _:
            # Apply field updates
            apply_field_updates_with_operation(
                parent=parent,
                col=col,
                field_updates=field_updates,
                logger=logger,
                on_success=on_success,
            )

        # Verify only valid field was updated
        updated_note = col.get_note(note.id)
        assert updated_note["Front"] == "Updated content"
        assert updated_note["Back"] == "back"  # Unchanged

        # Verify success callback was called
        assert len(success_results) == 1
        assert success_results[0]["updated"] == 1
        assert success_results[0]["failed"] == 0

    @with_test_collection("two_deck_collection")
    def test_apply_field_updates_with_operation_handles_note_not_found(
        self,
        col: TestCollection,
    ) -> None:
        """Test that apply_field_updates_with_operation handles note not found."""
        # Create field updates for a non-existent note ID
        field_updates = FieldUpdates({
            cast("NoteId", 999999): {"Front": "Updated content"},  # Non-existent note ID
        })

        # Mock logger
        logger = Mock()

        # Track success callback
        success_results = []

        def on_success(results: dict[str, int]) -> None:
            success_results.append(results)

        # Mock parent widget
        parent = Mock()

        # Apply field updates
        apply_field_updates_with_operation(
            parent=parent,
            col=col,
            field_updates=field_updates,
            logger=logger,
            on_success=on_success,
        )

        # Verify success callback was called with failure
        assert len(success_results) == 1
        assert success_results[0]["updated"] == 0
        assert success_results[0]["failed"] == 1

        # Verify error was logged
        logger.error.assert_called_once()

    @with_test_collection("two_deck_collection")
    def test_apply_field_updates_with_operation_no_updates(
        self,
        col: TestCollection,
    ) -> None:
        """Test that apply_field_updates_with_operation handles empty field updates."""
        # Create field updates with no notes
        field_updates = FieldUpdates()

        # Mock logger
        logger = Mock()

        # Track success callback
        success_results = []

        def on_success(results: dict[str, int]) -> None:
            success_results.append(results)

        # Mock parent widget
        parent = Mock()

        # Apply field updates
        apply_field_updates_with_operation(
            parent=parent,
            col=col,
            field_updates=field_updates,
            logger=logger,
            on_success=on_success,
        )

        # Verify success callback was called immediately
        assert len(success_results) == 1
        assert success_results[0]["updated"] == 0
        assert success_results[0]["failed"] == 0
