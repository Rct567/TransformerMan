"""
Tests for transform operations.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast, Callable, Any
from unittest.mock import Mock, MagicMock, patch
import pytest

from transformerman.lib.transform_operations import (
    NoteTransformer,
    create_lm_logger,
    apply_field_updates_with_operation,
)
from transformerman.lib.selected_notes import SelectedNotes
from transformerman.lib.lm_clients import DummyLMClient, ApiKey, ModelName, LmResponse
from transformerman.lib.prompt_builder import PromptBuilder
from tests.tools import test_collection as test_collection_fixture, with_test_collection, MockCollection

col = test_collection_fixture


if TYPE_CHECKING:
    from pathlib import Path
    from anki.notes import NoteId



@pytest.fixture
def mock_addon_config() -> Mock:
    """Create a mock AddonConfig."""
    config = Mock()
    config.is_enabled = Mock(return_value=False)
    return config


@pytest.fixture
def mock_user_files_dir(tmp_path: Path) -> Path:
    """Create a temporary directory for user files."""
    return tmp_path



class TestNoteTransformer:
    """Test class for NoteTransformer."""

    @with_test_collection("two_deck_collection")
    def test_init_validates_notes_with_empty_fields(
        self,
        col: MockCollection,
        mock_addon_config: Mock,
        mock_user_files_dir: Path,
    ) -> None:
        """Test that __init__ validates notes have empty fields."""
        # Get real note IDs from the collection (all have non-empty fields)
        note_ids = col.find_notes("")
        # Use a real SelectedNotes instance with those note IDs
        selected_notes = SelectedNotes(col, note_ids)

        # Create a real DummyLMClient
        dummy_client = DummyLMClient(ApiKey(""), ModelName("mock_content_generator"))

        # Create a real PromptBuilder
        prompt_builder = PromptBuilder()

        # The collection's notes have no empty fields in "Front" or "Back"
        # So validation should raise ValueError
        with pytest.raises(ValueError, match="No notes with empty fields found"):
            NoteTransformer(
                col=col,
                selected_notes=selected_notes,
                note_ids=note_ids,
                lm_client=dummy_client,
                prompt_builder=prompt_builder,
                selected_fields=["Front"],  # Field that exists and is non-empty
                note_type_name="Basic",
                max_prompt_size=500000,
                addon_config=mock_addon_config,
                user_files_dir=mock_user_files_dir,
            )

    @with_test_collection("two_deck_collection")
    def test_get_field_updates_returns_correct_updates(
        self,
        col: MockCollection,
        mock_addon_config: Mock,
        mock_user_files_dir: Path,
    ) -> None:
        """Test that get_field_updates returns correct field updates in preview mode."""
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
        dummy_client = DummyLMClient(ApiKey(""), ModelName("mock_content_generator"))

        # Create a real PromptBuilder
        prompt_builder = PromptBuilder()

        # Create NoteTransformer with max prompt size of 1000
        transformer = NoteTransformer(
            col=col,
            selected_notes=selected_notes,
            note_ids=note_ids,
            lm_client=dummy_client,
            prompt_builder=prompt_builder,
            selected_fields=["Front"],
            note_type_name="Basic",
            max_prompt_size=1000,
            addon_config=mock_addon_config,
            user_files_dir=mock_user_files_dir,
        )

        # Get field updates (preview mode)
        results, field_updates = transformer.get_field_updates()

        # Verify results
        assert results["num_notes_updated"] == 4  # All 4 notes should have updates
        assert results["num_notes_failed"] == 0
        assert results["num_batches_processed"] == 2  # Batch size produces 2 batches
        assert results["error"] is None

        # Verify field updates contain expected content
        assert len(field_updates) == 4
        for nid in note_ids:
            assert nid in field_updates
            assert "Front" in field_updates[nid]
            assert field_updates[nid]["Front"] == "Mock content for Front"

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
        col: MockCollection,
        mock_addon_config: Mock,
        mock_user_files_dir: Path,
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
        dummy_client = DummyLMClient(ApiKey(""), ModelName("mock_content_generator"))

        # Create a real PromptBuilder
        prompt_builder = PromptBuilder()

        # Create NoteTransformer with max prompt size
        transformer = NoteTransformer(
            col=col,
            selected_notes=selected_notes,
            note_ids=note_ids,
            lm_client=dummy_client,
            prompt_builder=prompt_builder,
            selected_fields=["Front"],
            note_type_name="Basic",
            max_prompt_size=500000,
            addon_config=mock_addon_config,
            user_files_dir=mock_user_files_dir,
        )

        # Track progress calls
        progress_calls = []
        def progress_callback(current: int, total: int) -> None:
            progress_calls.append((current, total))

        # Get field updates with progress callback
        transformer.get_field_updates(progress_callback=progress_callback)

        # Verify progress was reported (only 1 batch with 500k limit)
        assert len(progress_calls) == 2  # 1 batch + completion
        assert progress_calls[0] == (0, 1)  # First batch
        assert progress_calls[1] == (1, 1)  # Completion

    @with_test_collection("two_deck_collection")
    def test_get_field_updates_with_cancellation(
        self,
        col: MockCollection,
        mock_addon_config: Mock,
        mock_user_files_dir: Path,
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
        dummy_client = DummyLMClient(ApiKey(""), ModelName("mock_content_generator"))

        # Create a real PromptBuilder
        prompt_builder = PromptBuilder()

        # Create NoteTransformer with max prompt size
        transformer = NoteTransformer(
            col=col,
            selected_notes=selected_notes,
            note_ids=note_ids,
            lm_client=dummy_client,
            prompt_builder=prompt_builder,
            selected_fields=["Front"],
            note_type_name="Basic",
            max_prompt_size=500000,
            addon_config=mock_addon_config,
            user_files_dir=mock_user_files_dir,
        )

        # Cancel immediately (before processing)
        def should_cancel() -> bool:
            return True  # Cancel immediately

        # Get field updates with cancellation
        results, field_updates = transformer.get_field_updates(should_cancel=should_cancel)

        # Verify no batches were processed due to immediate cancellation
        assert results["num_batches_processed"] == 0
        # No notes should have updates due to cancellation
        assert len(field_updates) == 0

        # Verify that no notes have updates
        for nid in note_ids:
            assert nid not in field_updates

    @with_test_collection("two_deck_collection")
    def test_get_field_updates_handles_batch_errors(
        self,
        col: MockCollection,
        mock_addon_config: Mock,
        mock_user_files_dir: Path,
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
        prompt_builder = PromptBuilder()

        # Create a real DummyLMClient
        dummy_client = DummyLMClient(ApiKey(""), ModelName("mock_content_generator"))

        # Patch transform to raise an exception for the first batch and return a valid response for the second batch
        # Create a proper mock response for the second batch
        mock_response = MagicMock(spec=LmResponse)
        # The second batch contains note_ids[2] and note_ids[3]
        mock_response.get_notes_from_xml.return_value = {
            note_ids[2]: {"Front": "Content3"},
            note_ids[3]: {"Front": "Content4"},
        }
        mock_response.text_response = "<xml>response</xml>"
        mock_response.error = None  # Add error attribute

        # Make first batch fail, second batch succeed
        with patch.object(dummy_client, 'transform', side_effect=[Exception("Batch failed"), mock_response]):
            # Create NoteTransformer with max prompt size
            transformer = NoteTransformer(
                col=col,
                selected_notes=selected_notes,
                note_ids=note_ids,
                lm_client=dummy_client,
                prompt_builder=prompt_builder,
                selected_fields=["Front"],
                note_type_name="Basic",
                max_prompt_size=500000,
                addon_config=mock_addon_config,
                user_files_dir=mock_user_files_dir,
            )

            # Get field updates
            results, field_updates = transformer.get_field_updates()

        # Verify results show failures for all notes (all in one batch that failed)
        assert results["num_notes_failed"] == 4  # All 4 notes in the single batch
        assert results["num_notes_updated"] == 0  # No notes updated due to batch failure
        assert results["num_batches_processed"] == 1  # Only one batch attempted
        assert results["error"] is None  # No error in response

        # Verify that no notes have updates (batch failed)
        assert len(field_updates) == 0
        for nid in note_ids:
            assert nid not in field_updates

    @with_test_collection("two_deck_collection")
    def test_get_field_updates_only_returns_updates_for_empty_fields(
        self,
        col: MockCollection,
        mock_addon_config: Mock,
        mock_user_files_dir: Path,
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
        dummy_client = DummyLMClient(ApiKey(""), ModelName("mock_content_generator"))

        # Create a real PromptBuilder
        prompt_builder = PromptBuilder()

        # Create NoteTransformer with max prompt size
        transformer = NoteTransformer(
            col=col,
            selected_notes=selected_notes,
            note_ids=note_ids,
            lm_client=dummy_client,
            prompt_builder=prompt_builder,
            selected_fields=["Front"],
            note_type_name="Basic",
            max_prompt_size=500000,
            addon_config=mock_addon_config,
            user_files_dir=mock_user_files_dir,
        )

        # Get field updates
        results, field_updates = transformer.get_field_updates()

        # Verify only empty fields have updates
        assert results["num_notes_updated"] == 2  # Only first 2 notes (empty fields)
        assert results["num_notes_failed"] == 0
        # Only one batch (notes with empty fields) - notes with non-empty fields are filtered out
        assert results["num_batches_processed"] == 1

        # Verify that only empty fields have updates
        assert len(field_updates) == 2
        for i, nid in enumerate(note_ids):
            if i < 2:
                # Empty field should have update
                assert nid in field_updates
                assert field_updates[nid]["Front"] == "Mock content for Front"
            else:
                # Non-empty field should not have update
                assert nid not in field_updates


class TestApplyFieldUpdatesWithOperation:
    """Test class for apply_field_updates_with_operation function."""

    @with_test_collection("two_deck_collection")
    def test_apply_field_updates_with_operation_applies_updates(
        self,
        col: MockCollection,
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
        field_updates = {
            note_ids[0]: {"Front": "Updated content 1"},
            note_ids[1]: {"Front": "Updated content 2"},
            note_ids[2]: {"Front": "Updated content 3"},
            note_ids[3]: {"Front": "Updated content 4"},
        }

        # Mock logger
        logger = Mock()

        # Track success callback
        success_results = []
        def on_success(results: dict[str, int]) -> None:
            success_results.append(results)

        # Mock parent widget
        parent = Mock()

        # Mock CollectionOp to update notes synchronously
        with patch('transformerman.lib.transform_operations.CollectionOp') as MockCollectionOp:
            # Configure mock to call success callback immediately
            def mock_collection_op_call(parent: Mock, op_func: Callable) -> Mock:
                # Execute the operation function synchronously to update notes
                # The op_func takes a collection and returns changes
                changes = op_func(col)
                # Create a mock operation
                mock_op = Mock()
                # When success is called, call the callback with changes
                def success(callback: Callable[[Any], None]) -> Mock:
                    callback(changes)
                    return mock_op
                mock_op.success = success
                mock_op.failure = lambda callback: mock_op # type: ignore
                mock_op.run_in_background = Mock()
                return mock_op
            MockCollectionOp.side_effect = mock_collection_op_call

            # Mock mw and taskman to avoid AssertionError
            with patch('aqt.mw') as mock_mw:
                mock_taskman = Mock()
                mock_mw.taskman = mock_taskman

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
        col: MockCollection,
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
        field_updates = {
            note.id: {
                "Front": "Updated content",  # Valid field
                "NonexistentField": "Some content",  # Nonexistent field
            }
        }

        # Mock logger
        logger = Mock()

        # Track success callback
        success_results = []
        def on_success(results: dict[str, int]) -> None:
            success_results.append(results)

        # Mock parent widget
        parent = Mock()

        # Mock CollectionOp to update notes synchronously
        with patch('transformerman.lib.transform_operations.CollectionOp') as MockCollectionOp:
            # Configure mock to call success callback immediately
            def mock_collection_op_call(parent: Mock, op_func: Callable) -> Mock:
                # Execute the operation function synchronously to update notes
                # The op_func takes a collection and returns changes
                changes = op_func(col)
                # Create a mock operation
                mock_op = Mock()
                # When success is called, call the callback with changes
                def success(callback: Callable[[Any], None]) -> Mock:
                    callback(changes)
                    return mock_op
                mock_op.success = success
                mock_op.failure = lambda callback: mock_op # type: ignore
                mock_op.run_in_background = Mock()
                return mock_op
            MockCollectionOp.side_effect = mock_collection_op_call

            # Mock mw and taskman to avoid AssertionError
            with patch('aqt.mw') as mock_mw:
                mock_taskman = Mock()
                mock_mw.taskman = mock_taskman

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
        col: MockCollection,
    ) -> None:
        """Test that apply_field_updates_with_operation handles note not found."""
        # Create field updates for a non-existent note ID
        field_updates = {
            cast("NoteId", 999999): {"Front": "Updated content"},  # Non-existent note ID
        }

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
        col: MockCollection,
    ) -> None:
        """Test that apply_field_updates_with_operation handles empty field updates."""
        # Create field updates with no notes
        field_updates: dict[NoteId, dict[str, str]] = {}

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


class TestCreateLmLogger:
    """Test class for create_lm_logger function."""

    def test_create_lm_logger_disabled_logging(
        self,
        mock_addon_config: Mock,
        mock_user_files_dir: Path,
    ) -> None:
        """Test that create_lm_logger returns functions that don't log when disabled."""
        # Configure mock to return False for both settings
        def is_enabled(setting: str, default: bool) -> bool:
            return False

        mock_addon_config.is_enabled = is_enabled

        log_request, log_response = create_lm_logger(mock_addon_config, mock_user_files_dir)

        # Call logging functions
        log_request("test prompt")
        log_response(MagicMock(spec=LmResponse, text_response="test response"))

        # Verify no files were created (since logging is disabled)
        logs_dir = mock_user_files_dir / 'logs'
        assert not logs_dir.exists()

    def test_create_lm_logger_enabled_logging(
        self,
        mock_addon_config: Mock,
        mock_user_files_dir: Path,
    ) -> None:
        """Test that create_lm_logger returns functions that log when enabled."""
        # Configure mock to return True for both settings
        def is_enabled(setting: str, default: bool) -> bool:
            return True

        mock_addon_config.is_enabled = is_enabled

        log_request, log_response = create_lm_logger(mock_addon_config, mock_user_files_dir)

        # Call logging functions
        test_prompt = "test prompt"
        test_response = MagicMock(spec=LmResponse, text_response="test response")

        log_request(test_prompt)
        log_response(test_response)

        # Verify files were created and contain expected content
        logs_dir = mock_user_files_dir / 'logs'
        assert logs_dir.exists()

        # Check request log
        requests_file = logs_dir / 'lm_requests.log'
        assert requests_file.exists()
        with requests_file.open('r', encoding='utf-8') as f:
            content = f.read()
            assert test_prompt in content

        # Check response log
        responses_file = logs_dir / 'lm_responses.log'
        assert responses_file.exists()
        with responses_file.open('r', encoding='utf-8') as f:
            content = f.read()
            assert test_response.text_response in content
