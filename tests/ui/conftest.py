"""
Shared fixtures for UI tests.

This module provides common test fixtures for testing TransformerMan UI components.
Follows project guideline: "Use pytest fixtures, but try to use the real thing where possible (it often is)"
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast
from unittest.mock import Mock, patch

import pytest

from aqt.qt import QWidget, QMessageBox

from transformerman.lib.lm_clients import DummyLMClient, ApiKey, ModelName
from transformerman.lib.selected_notes import SelectedNotes

if TYPE_CHECKING:
    from pathlib import Path
    from pytestqt.qtbot import QtBot
    from anki.notes import NoteId


# Patch restoreGeom and saveGeom at the module level where they're used
# Also patch QMessageBox to avoid showing dialogs during tests
# Patch QueryOp to avoid requiring main window
@pytest.fixture(autouse=True)
def mock_anki_utils():
    """Mock Anki utility functions that require main window."""
    with patch('transformerman.ui.base_dialog.restoreGeom') as mock_restore, \
         patch('transformerman.ui.base_dialog.saveGeom') as mock_save, \
         patch('transformerman.ui.settings_dialog.QMessageBox.question') as mock_qmessagebox, \
         patch('transformerman.ui.preview_table.QueryOp') as mock_query_op:
        # Configure mocks to do nothing (successful no-op)
        mock_restore.return_value = None
        mock_save.return_value = None
        # Default QMessageBox.question to return Save to avoid blocking
        mock_qmessagebox.return_value = QMessageBox.StandardButton.Save

        # Mock QueryOp to avoid requiring main window
        mock_query_op_instance = Mock()
        mock_query_op_instance.failure.return_value = mock_query_op_instance
        mock_query_op_instance.run_in_background.return_value = None
        mock_query_op.return_value = mock_query_op_instance

        yield


@pytest.fixture
def qtbot(qtbot: QtBot) -> QtBot:
    """QtBot fixture for testing Qt widgets."""
    return qtbot


@pytest.fixture
def parent_widget(qtbot: QtBot) -> QWidget:
    """Create a parent widget for dialogs."""
    widget = QWidget()
    qtbot.addWidget(widget)
    return widget


@pytest.fixture
def mock_collection() -> Mock:
    """Mock Anki collection."""
    collection = Mock(spec_set=["get_note", "models", "find_notes"])

    # Mock models to return proper dict-like objects
    mock_model = {"name": "Basic", "id": 123, "flds": [{"name": "Front"}, {"name": "Back"}]}
    collection.models = Mock()
    collection.models.all.return_value = [mock_model]

    # Mock models.get to return the mock model when called with ID 123
    def models_get_side_effect(model_id: int) -> dict[str, Any] | None:
        if model_id == 123:
            return mock_model
        return None

    collection.models.get = Mock(side_effect=models_get_side_effect)

    # Mock find_notes to return empty list
    collection.find_notes.return_value = []

    # Mock get_note to return a mock note with proper attributes
    def get_note_side_effect(note_id: NoteId) -> Mock:
        note = Mock()
        note.id = note_id
        note.mid = 123  # Model ID
        note.note_type = Mock(return_value={"name": "Basic", "id": 123})
        note.fields = ["Front", "Back"]
        note.items.return_value = [("Front", f"Question {note_id}"), ("Back", f"Answer {note_id}")]
        # Define __getitem__ as a proper function with type hints
        def getitem_func(self: Mock, key: str) -> str:
            return {"Front": f"Question {note_id}", "Back": f"Answer {note_id}"}.get(key, "")
        note.__getitem__ = getitem_func
        return note

    collection.get_note.side_effect = get_note_side_effect

    return collection


@pytest.fixture
def test_note_ids() -> list[NoteId]:
    """Test note IDs for testing."""
    return [cast('NoteId', 123), cast('NoteId', 456), cast('NoteId', 789)]


@pytest.fixture
def selected_notes(mock_collection: Mock, test_note_ids: list[NoteId]) -> SelectedNotes:
    """
    Real SelectedNotes instance with mocked collection.

    Uses real SelectedNotes class with a mocked collection to avoid database dependencies.
    """
    # Mock get_note to return a mock note
    def get_note_side_effect(note_id: NoteId) -> Mock:
        note = Mock()
        note.id = note_id
        note.note_type.return_value = {"name": "Basic", "id": 123}
        note.fields = ["Front", "Back"]
        note.items.return_value = [("Front", f"Question {note_id}"), ("Back", f"Answer {note_id}")]
        # Define __getitem__ as a proper function with type hints
        def getitem_func(self: Mock, key: str) -> str:
            return {"Front": f"Question {note_id}", "Back": f"Answer {note_id}"}.get(key, "")
        note.__getitem__ = getitem_func
        return note

    mock_collection.get_note.side_effect = get_note_side_effect

    return SelectedNotes(mock_collection, test_note_ids)


@pytest.fixture
def addon_config() -> Mock:
    """
    Mock AddonConfig for UI tests.

    Returns a Mock that behaves like AddonConfig for UI testing.
    """
    config = Mock(spec_set=["get", "get_api_key", "set_api_key", "update_setting", "reload"])

    # Default configuration values
    def get_side_effect(key: str, default: Any = None) -> Any:
        config_dict = {
            "lm_client": "dummy",
            "model": "mock_content_generator",
            "batch_size": 10,
            "log_lm_requests": False,
            "log_lm_responses": False,
        }
        return config_dict.get(key, default)
    config.get.side_effect = get_side_effect

    config.get_api_key.return_value = "test-api-key"
    config.set_api_key.return_value = None
    config.update_setting.return_value = None
    config.reload.return_value = None

    return config


@pytest.fixture
def dummy_lm_client() -> DummyLMClient:
    """Real DummyLMClient instance for testing."""
    return DummyLMClient(ApiKey(""), ModelName("mock_content_generator"))


@pytest.fixture
def is_dark_mode() -> bool:
    """Fixture for dark mode setting."""
    return False


@pytest.fixture
def user_files_dir(tmp_path: Path) -> Path:
    """Temporary directory for user files."""
    return tmp_path / "user_files"


@pytest.fixture
def test_field_updates() -> dict[NoteId, dict[str, str]]:
    """Test field updates for preview highlighting."""
    return {
        cast('NoteId', 123): {"Front": "Updated Front 1", "Back": "Updated Back 1"},
        cast('NoteId', 456): {"Front": "Updated Front 2", "Back": "Updated Back 2"},
    }


@pytest.fixture
def test_transform_results() -> dict[str, int]:
    """Test transformation results for results dialog."""
    return {
        "updated": 5,
        "failed": 1,
        "batches_processed": 2,
    }


@pytest.fixture
def test_selected_fields() -> set[str]:
    """Test selected fields set."""
    return {"Front", "Back"}


@pytest.fixture
def test_note_type_name() -> str:
    """Test note type name."""
    return "Basic"
