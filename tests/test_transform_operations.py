"""
Tests for transform operations.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast
from unittest.mock import Mock, MagicMock
import pytest

from transformerman.lib.transform_operations import NoteTransformer, create_lm_logger
from tests.tools import test_collection as test_collection_fixture

col = test_collection_fixture


if TYPE_CHECKING:
    from pathlib import Path
    from anki.notes import NoteId


@pytest.fixture
def mock_selected_notes() -> Mock:
    """Create a mock SelectedNotes instance."""
    selected_notes = Mock()

    # Mock note with empty fields
    mock_note = Mock()
    mock_note.has_note_with_empty_field = Mock(return_value=True)
    mock_note.filter_by_empty_field = Mock(return_value=mock_note)  # returns itself
    mock_note.note_ids = [1, 2, 3, 4]
    # Mock batched to return list of SelectedNotes mocks
    batch1 = Mock()
    batch1.note_ids = [1, 2]
    batch2 = Mock()
    batch2.note_ids = [3, 4]
    mock_note.batched = Mock(return_value=[batch1, batch2])

    selected_notes.get_selected_notes = Mock(return_value=mock_note)
    return selected_notes


@pytest.fixture
def mock_lm_client() -> Mock:
    """Create a mock LM client."""
    client = Mock()

    # Mock response
    mock_response = Mock()
    mock_response.get_notes_from_xml = Mock(return_value={
        1: {"Field1": "Content1"},
        2: {"Field1": "Content2"},
        3: {"Field1": "Content3"},
        4: {"Field1": "Content4"},
    })
    mock_response.text_response = "<xml>response</xml>"
    mock_response.error = None

    client.transform = Mock(return_value=mock_response)
    return client


@pytest.fixture
def mock_prompt_builder() -> Mock:
    """Create a mock PromptBuilder."""
    builder = Mock()
    builder.build_prompt = Mock(return_value="Test prompt")
    return builder


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


@pytest.fixture
def note_transformer(
    mock_selected_notes: Mock,
    mock_lm_client: Mock,
    mock_prompt_builder: Mock,
    mock_addon_config: Mock,
    mock_user_files_dir: Path,
) -> NoteTransformer:
    """Create a NoteTransformer instance for testing."""
    # We'll create a real collection for this fixture
    # But tests that use this fixture will need to mock collection methods
    # This is a temporary solution - ideally tests should use @with_test_collection
    mock_collection = Mock()
    mock_collection.get_note = Mock()
    mock_collection.update_note = Mock()

    return NoteTransformer(
        col=mock_collection,
        selected_notes=mock_selected_notes,
        note_ids=[cast("NoteId", 1), cast("NoteId", 2), cast("NoteId", 3), cast("NoteId", 4)],
        lm_client=mock_lm_client,
        prompt_builder=mock_prompt_builder,
        selected_fields={"Field1"},
        note_type_name="Basic",
        batch_size=2,
        addon_config=mock_addon_config,
        user_files_dir=mock_user_files_dir,
    )


class TestNoteTransformer:
    """Test class for NoteTransformer."""

    def test_init_validates_notes_with_empty_fields(
        self,
        mock_selected_notes: Mock,
        mock_lm_client: Mock,
        mock_prompt_builder: Mock,
        mock_addon_config: Mock,
        mock_user_files_dir: Path,
    ) -> None:
        """Test that __init__ validates notes have empty fields."""
        # Mock notes without empty fields
        mock_selected_notes_without_empty = Mock()
        mock_selected_notes_without_empty.has_note_with_empty_field = Mock(return_value=False)
        # Add required attributes (won't be used because validation fails)
        mock_selected_notes_without_empty.filter_by_empty_field = Mock()
        mock_selected_notes_without_empty.batched = Mock()
        mock_selected_notes.get_selected_notes = Mock(return_value=mock_selected_notes_without_empty)

        # Create a mock collection
        mock_collection = Mock()
        mock_collection.get_note = Mock()
        mock_collection.update_note = Mock()

        with pytest.raises(ValueError, match="No notes with empty fields found"):
            NoteTransformer(
                col=mock_collection,
                selected_notes=mock_selected_notes,
                note_ids=[cast("NoteId", 1), cast("NoteId", 2), cast("NoteId", 3), cast("NoteId", 4)],
                lm_client=mock_lm_client,
                prompt_builder=mock_prompt_builder,
                selected_fields={"Field1"},
                note_type_name="Basic",
                batch_size=2,
                addon_config=mock_addon_config,
                user_files_dir=mock_user_files_dir,
            )

    def test_transform_processes_all_batches(
        self,
        note_transformer: NoteTransformer,
        mock_lm_client: Mock,
        mock_prompt_builder: Mock,
    ) -> None:
        """Test that transform processes all batches."""
        # Mock notes
        mock_notes = []
        for _ in [1, 2, 3, 4]:
            note = Mock()
            note.__getitem__ = Mock(return_value="")  # Empty field
            note.__setitem__ = Mock()
            mock_notes.append(note)

        note_transformer.col.get_note.side_effect = mock_notes # type: ignore

        # Run transformation (immediate application)
        results = note_transformer.transform()

        # Verify results
        assert results["updated"] == 4  # All 4 notes should be updated
        assert results["failed"] == 0
        assert results["batches_processed"] == 2  # 2 batches of size 2

        # Verify LM client was called for each batch
        assert mock_lm_client.transform.call_count == 2
        mock_prompt_builder.build_prompt.assert_called()

        # Verify notes were updated
        assert note_transformer.col.update_note.call_count == 4 # type: ignore

    def test_transform_with_progress_callback(
        self,
        note_transformer: NoteTransformer,
    ) -> None:
        """Test that transform calls progress callback."""
        # Mock notes
        mock_notes = []
        for _ in [1, 2, 3, 4]:
            note = Mock()
            note.__getitem__ = Mock(return_value="")  # Empty field
            note.__setitem__ = Mock()
            mock_notes.append(note)

        note_transformer.col.get_note.side_effect = mock_notes # type: ignore

        # Track progress calls
        progress_calls = []
        def progress_callback(current: int, total: int) -> None:
            progress_calls.append((current, total))

        # Run transformation
        note_transformer.transform(progress_callback=progress_callback)

        # Verify progress was reported
        assert len(progress_calls) == 3  # 2 batches + completion
        assert progress_calls[0] == (0, 2)  # First batch
        assert progress_calls[1] == (1, 2)  # Second batch
        assert progress_calls[2] == (2, 2)  # Completion

    def test_transform_with_cancellation(
        self,
        note_transformer: NoteTransformer,
    ) -> None:
        """Test that transform respects cancellation."""
        # Mock notes for first batch only
        mock_notes = []
        for _ in [1, 2]:
            note = Mock()
            note.__getitem__ = Mock(return_value="")  # Empty field
            note.__setitem__ = Mock()
            mock_notes.append(note)

        note_transformer.col.get_note.side_effect = mock_notes # type: ignore

        # Cancel after first batch
        cancel_after = [0]
        def should_cancel() -> bool:
            cancel_after[0] += 1
            return cancel_after[0] > 1  # Cancel after first check

        # Run transformation
        results = note_transformer.transform(should_cancel=should_cancel)

        # Verify only first batch was processed
        assert results["batches_processed"] == 1
        assert note_transformer.col.update_note.call_count == 2  # type: ignore # Only first batch notes

    def test_transform_handles_note_update_errors(
        self,
        note_transformer: NoteTransformer,
    ) -> None:
        """Test that transform handles note update errors gracefully."""
        # Mock notes with one failing
        mock_notes = []
        for i, _ in enumerate([1, 2, 3, 4]):
            note = Mock()
            note.__getitem__ = Mock(return_value="")  # Empty field
            note.__setitem__ = Mock()

            # Make second note fail
            if i == 1:
                note_transformer.col.update_note.side_effect = [Exception("Update failed"), None, None, None] # type: ignore

            mock_notes.append(note)

        note_transformer.col.get_note.side_effect = mock_notes # type: ignore

        # Run transformation
        results = note_transformer.transform()

        # Verify results show one failure
        assert results["failed"] == 1
        assert results["updated"] == 3  # Other 3 notes updated successfully

    def test_transform_handles_batch_errors(
        self,
        note_transformer: NoteTransformer,
        mock_lm_client: Mock,
    ) -> None:
        """Test that transform handles batch processing errors gracefully."""
        # Mock notes for both batches
        mock_notes = []
        for _ in [1, 2, 3, 4]:
            note = Mock()
            note.__getitem__ = Mock(return_value="")  # Empty field
            note.__setitem__ = Mock()
            mock_notes.append(note)

        note_transformer.col.get_note.side_effect = mock_notes # type: ignore

        # Create a proper mock response for the second batch
        mock_response = MagicMock()
        mock_response.get_notes_from_xml.return_value = {
            3: {"Field1": "Content3"},
            4: {"Field1": "Content4"},
        }
        mock_response.text_response = "<xml>response</xml>"
        mock_response.error = None  # Add error attribute

        # Make first batch fail, second batch succeed
        mock_lm_client.transform.side_effect = [Exception("Batch failed"), mock_response]

        # Run transformation
        results = note_transformer.transform()

        # Verify results show failures for first batch only
        assert results["failed"] == 2  # 2 notes in first batch
        assert results["updated"] == 2  # 2 notes in second batch updated
        assert results["batches_processed"] == 2  # Both batches attempted

    def test_transform_only_updates_empty_fields(
        self,
        note_transformer: NoteTransformer,
    ) -> None:
        """Test that transform only updates empty fields."""
        # Mock notes with some non-empty fields
        mock_notes = []
        for i, _ in enumerate([1, 2, 3, 4]):
            note = Mock()
            # First two notes have empty fields, last two have non-empty
            if i < 2:
                note.__getitem__ = Mock(return_value="")  # Empty field
            else:
                note.__getitem__ = Mock(return_value="Already filled")  # Non-empty field
            note.__setitem__ = Mock()
            mock_notes.append(note)

        note_transformer.col.get_note.side_effect = mock_notes # type: ignore

        # Run transformation
        results = note_transformer.transform()

        # Verify only empty fields were updated
        assert results["updated"] == 2  # Only first 2 notes
        assert results["failed"] == 0

        # Verify __setitem__ was only called for empty fields
        for i, note in enumerate(mock_notes):
            if i < 2:
                note.__setitem__.assert_called_with("Field1", f"Content{i+1}")
            else:
                note.__setitem__.assert_not_called()


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
