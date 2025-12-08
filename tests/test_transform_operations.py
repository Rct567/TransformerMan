"""
Tests for transform operations.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import Mock, MagicMock
import pytest

from transformerman.lib.transform_operations import NoteTransformer, create_lm_logger
from transformerman.lib.selected_notes import SelectedNotes
from transformerman.lib.lm_clients import DummyLMClient, ApiKey, ModelName
from transformerman.lib.prompt_builder import PromptBuilder
from tests.tools import test_collection as test_collection_fixture, with_test_collection, MockCollection

col = test_collection_fixture


if TYPE_CHECKING:
    from pathlib import Path



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
                selected_fields={"Front"},  # Field that exists and is non-empty
                note_type_name="Basic",
                batch_size=2,
                addon_config=mock_addon_config,
                user_files_dir=mock_user_files_dir,
            )

    @with_test_collection("two_deck_collection")
    def test_transform_processes_all_batches(
        self,
        col: MockCollection,
        mock_addon_config: Mock,
        mock_user_files_dir: Path,
    ) -> None:
        """Test that transform processes all batches."""
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

        # Create NoteTransformer with batch size 2
        transformer = NoteTransformer(
            col=col,
            selected_notes=selected_notes,
            note_ids=note_ids,
            lm_client=dummy_client,
            prompt_builder=prompt_builder,
            selected_fields={"Front"},
            note_type_name="Basic",
            batch_size=2,
            addon_config=mock_addon_config,
            user_files_dir=mock_user_files_dir,
        )

        # Run transformation (immediate application)
        results = transformer.transform()

        # Verify results
        assert results["updated"] == 4  # All 4 notes should be updated
        assert results["failed"] == 0
        assert results["batches_processed"] == 2  # 2 batches of size 2

        # Verify notes were updated in the collection with dummy content
        for nid in note_ids:
            note = col.get_note(nid)
            # DummyLMClient fills empty fields with "Mock content for Front"
            assert note["Front"] == "Mock content for Front"
            # Back field should remain unchanged (non-empty)
            assert note["Back"] == "some back"

    @with_test_collection("two_deck_collection")
    def test_transform_with_progress_callback(
        self,
        col: MockCollection,
        mock_addon_config: Mock,
        mock_user_files_dir: Path,
    ) -> None:
        """Test that transform calls progress callback."""
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

        # Create NoteTransformer with batch size 2
        transformer = NoteTransformer(
            col=col,
            selected_notes=selected_notes,
            note_ids=note_ids,
            lm_client=dummy_client,
            prompt_builder=prompt_builder,
            selected_fields={"Front"},
            note_type_name="Basic",
            batch_size=2,
            addon_config=mock_addon_config,
            user_files_dir=mock_user_files_dir,
        )

        # Track progress calls
        progress_calls = []
        def progress_callback(current: int, total: int) -> None:
            progress_calls.append((current, total))

        # Run transformation with progress callback
        transformer.transform(progress_callback=progress_callback)

        # Verify progress was reported
        assert len(progress_calls) == 3  # 2 batches + completion
        assert progress_calls[0] == (0, 2)  # First batch
        assert progress_calls[1] == (1, 2)  # Second batch
        assert progress_calls[2] == (2, 2)  # Completion

        # Verify notes were updated in the collection with dummy content
        for nid in note_ids:
            note = col.get_note(nid)
            # DummyLMClient fills empty fields with "Mock content for Front"
            assert note["Front"] == "Mock content for Front"
            # Back field should remain unchanged (non-empty)
            assert note["Back"] == "some back"

    @with_test_collection("two_deck_collection")
    def test_transform_with_cancellation(
        self,
        col: MockCollection,
        mock_addon_config: Mock,
        mock_user_files_dir: Path,
    ) -> None:
        """Test that transform respects cancellation."""
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

        # Create NoteTransformer with batch size 2
        transformer = NoteTransformer(
            col=col,
            selected_notes=selected_notes,
            note_ids=note_ids,
            lm_client=dummy_client,
            prompt_builder=prompt_builder,
            selected_fields={"Front"},
            note_type_name="Basic",
            batch_size=2,
            addon_config=mock_addon_config,
            user_files_dir=mock_user_files_dir,
        )

        # Cancel after first batch
        cancel_after = [0]
        def should_cancel() -> bool:
            cancel_after[0] += 1
            return cancel_after[0] > 1  # Cancel after first check

        # Run transformation with cancellation
        results = transformer.transform(should_cancel=should_cancel)

        # Verify only first batch was processed
        assert results["batches_processed"] == 1
        # Only first batch notes should be updated (2 notes)
        # Since DummyLMClient fills empty fields, we can check that only first two notes have been updated
        # Actually the transformer will have updated the first two notes (since batch size 2)
        # The second batch should not have been processed due to cancellation.
        # We can verify that notes 3 and 4 still have empty fields? Wait, they were never processed.
        # However, the DummyLMClient would have been called only for the first batch.
        # Let's verify that the first two notes have been updated, and the last two notes remain empty.
        for i, nid in enumerate(note_ids):
            note = col.get_note(nid)
            if i < 2:
                # First batch: updated
                assert note["Front"] == "Mock content for Front"
            else:
                # Second batch: not updated (still empty)
                assert note["Front"] == ""
            # Back field unchanged
            assert note["Back"] == "some back"

    @with_test_collection("two_deck_collection")
    def test_transform_handles_note_update_errors(
        self,
        col: MockCollection,
        mock_addon_config: Mock,
        mock_user_files_dir: Path,
    ) -> None:
        """Test that transform handles note update errors gracefully."""
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

        # Create NoteTransformer with batch size 2
        transformer = NoteTransformer(
            col=col,
            selected_notes=selected_notes,
            note_ids=note_ids,
            lm_client=dummy_client,
            prompt_builder=prompt_builder,
            selected_fields={"Front"},
            note_type_name="Basic",
            batch_size=2,
            addon_config=mock_addon_config,
            user_files_dir=mock_user_files_dir,
        )

        # Patch col.update_note to raise an exception for the second note (index 1)
        from unittest.mock import patch
        from typing import Any
        original_update_note = col.update_note
        call_count = 0
        def mock_update_note(note: Any) -> Any:
            nonlocal call_count
            call_count += 1
            if call_count == 2:  # second note update
                raise Exception("Update failed")
            return original_update_note(note)

        with patch.object(col, 'update_note', side_effect=mock_update_note):
            # Run transformation
            results = transformer.transform()

        # Verify results show one failure
        assert results["failed"] == 1
        assert results["updated"] == 3  # Other 3 notes updated successfully

        # Verify that the first, third, and fourth notes were updated
        for i, nid in enumerate(note_ids):
            note = col.get_note(nid)
            if i == 1:  # second note (failed)
                # Should still be empty because update failed
                assert note["Front"] == ""
            else:
                # Should be updated with dummy content
                assert note["Front"] == "Mock content for Front"
            # Back field unchanged
            assert note["Back"] == "some back"

    @with_test_collection("two_deck_collection")
    def test_transform_handles_batch_errors(
        self,
        col: MockCollection,
        mock_addon_config: Mock,
        mock_user_files_dir: Path,
    ) -> None:
        """Test that transform handles batch processing errors gracefully."""
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
        from unittest.mock import patch
        from transformerman.lib.lm_clients import LmResponse

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
            # Create NoteTransformer with batch size 2
            transformer = NoteTransformer(
                col=col,
                selected_notes=selected_notes,
                note_ids=note_ids,
                lm_client=dummy_client,
                prompt_builder=prompt_builder,
                selected_fields={"Front"},
                note_type_name="Basic",
                batch_size=2,
                addon_config=mock_addon_config,
                user_files_dir=mock_user_files_dir,
            )

            # Run transformation
            results = transformer.transform()

        # Verify results show failures for first batch only
        assert results["failed"] == 2  # 2 notes in first batch
        assert results["updated"] == 2  # 2 notes in second batch updated
        assert results["batches_processed"] == 2  # Both batches attempted

        # Verify that notes from first batch remain empty, second batch updated
        for i, nid in enumerate(note_ids):
            note = col.get_note(nid)
            if i < 2:
                # First batch: empty (failed)
                assert note["Front"] == ""
            else:
                # Second batch: updated with mock content
                assert note["Front"] == f"Content{i+1}"
            # Back field unchanged
            assert note["Back"] == "some back"

    @with_test_collection("two_deck_collection")
    def test_transform_only_updates_empty_fields(
        self,
        col: MockCollection,
        mock_addon_config: Mock,
        mock_user_files_dir: Path,
    ) -> None:
        """Test that transform only updates empty fields."""
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

        # Create NoteTransformer with batch size 2
        transformer = NoteTransformer(
            col=col,
            selected_notes=selected_notes,
            note_ids=note_ids,
            lm_client=dummy_client,
            prompt_builder=prompt_builder,
            selected_fields={"Front"},
            note_type_name="Basic",
            batch_size=2,
            addon_config=mock_addon_config,
            user_files_dir=mock_user_files_dir,
        )

        # Run transformation
        results = transformer.transform()

        # Verify only empty fields were updated
        assert results["updated"] == 2  # Only first 2 notes (empty fields)
        assert results["failed"] == 0
        assert results["batches_processed"] == 1  # Only one batch (notes with empty fields)

        # Verify that empty fields were updated, non-empty fields unchanged
        for i, nid in enumerate(note_ids):
            note = col.get_note(nid)
            if i < 2:
                # Empty field should be filled with dummy content
                assert note["Front"] == "Mock content for Front"
            else:
                # Non-empty field should remain unchanged (not processed)
                assert note["Front"] == "Already filled"
            # Back field unchanged
            assert note["Back"] == "some back"


class TestCreateLmLogger:
    """Test class for create_lm_logger function."""

    def test_logging_disabled(
        self,
        mock_addon_config: Mock,
        mock_user_files_dir: Path,
    ) -> None:
        """Test that logging functions do nothing when logging is disabled."""
        mock_addon_config.is_enabled.return_value = False

        log_request, log_response = create_lm_logger(mock_addon_config, mock_user_files_dir)

        # Call logging functions
        log_request("Test prompt")
        log_response(Mock(text_response="Test response"))

        # Verify no log files were created (directory may exist but should be empty)
        logs_dir = mock_user_files_dir / 'logs'
        if logs_dir.exists():
            # Directory might exist from mkdir, but should have no log files
            requests_file = logs_dir / 'lm_requests.log'
            responses_file = logs_dir / 'lm_responses.log'
            assert not requests_file.exists()
            assert not responses_file.exists()

    def test_logging_enabled(
        self,
        mock_addon_config: Mock,
        mock_user_files_dir: Path,
    ) -> None:
        """Test that logging functions write to files when logging is enabled."""
        mock_addon_config.is_enabled.return_value = True

        log_request, log_response = create_lm_logger(mock_addon_config, mock_user_files_dir)

        # Call logging functions
        log_request("Test prompt")

        mock_response = Mock()
        mock_response.text_response = "Test response"
        log_response(mock_response)

        # Verify files were created and contain expected content
        logs_dir = mock_user_files_dir / 'logs'
        assert logs_dir.exists()

        requests_file = logs_dir / 'lm_requests.log'
        assert requests_file.exists()

        responses_file = logs_dir / 'lm_responses.log'
        assert responses_file.exists()

        # Check file contents
        with requests_file.open('r', encoding='utf-8') as f:
            content = f.read()
            assert "Test prompt" in content

        with responses_file.open('r', encoding='utf-8') as f:
            content = f.read()
            assert "Test response" in content
