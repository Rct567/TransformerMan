"""Tests for preview table.

Tests the PreviewTable widget which displays note previews with background loading
and highlighting capabilities.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast, Any
from unittest.mock import Mock, patch

import pytest

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot
    from anki.notes import NoteId

from aqt.qt import QWidget, QColor

from transformerman.ui.preview_table import (
    PreviewTable,
    DARK_MODE_HIGHLIGHT_COLOR,
    LIGHT_MODE_HIGHLIGHT_COLOR,
)
from transformerman.lib.field_updates import FieldUpdates
from transformerman.lib.selected_notes import SelectedNotes
from tests.tools import with_test_collection, TestCollection, test_collection as test_collection_fixture

col = test_collection_fixture


@pytest.fixture
def test_note_ids() -> list[NoteId]:
    return [cast("NoteId", 123), cast("NoteId", 456), cast("NoteId", 789)]


@pytest.fixture
def test_selected_fields() -> list[str]:
    return ["Front", "Back"]


@pytest.fixture
def test_field_updates() -> FieldUpdates:
    return FieldUpdates({
        cast("NoteId", 123): {"Front": "Updated Front 1", "Back": "Updated Back 1"},
        cast("NoteId", 456): {"Front": "Updated Front 2", "Back": "Updated Back 2"},
    })


def create_mock_note(note_id: int, field_updates: dict[str, str]) -> Mock:
    """Create a mock note with field access."""
    mock_note = Mock()
    mock_note.id = note_id

    def make_getitem(field_note_id: int) -> Any:
        return lambda key: f"Original {key} for note {field_note_id}"  # pyright: ignore

    mock_note.__getitem__ = Mock(side_effect=make_getitem(note_id))
    return mock_note


class TestPreviewTable:
    """Test class for PreviewTable."""

    @with_test_collection("empty_collection")
    def test_table_creation(
        self,
        qtbot: QtBot,
        parent_widget: QWidget,
        is_dark_mode: bool,
        col: TestCollection,
    ) -> None:
        """Test that preview table can be created."""
        selected_notes = SelectedNotes(col, [])
        table = PreviewTable(parent_widget, is_dark_mode, selected_notes.get_notes)
        qtbot.addWidget(table)

        assert table.parent() is parent_widget
        assert table.alternatingRowColors()

        vertical_header = table.verticalHeader()
        if vertical_header:
            assert not vertical_header.isVisible()

        assert table.minimumHeight() >= 150
        assert table.rowCount() == 0
        assert table.columnCount() == 0

    @with_test_collection("empty_collection")
    def test_set_note_fields_update_with_empty_data(
        self,
        qtbot: QtBot,
        parent_widget: QWidget,
        is_dark_mode: bool,
        col: TestCollection,
    ) -> None:
        """Test that table handles empty note IDs or fields."""
        selected_notes = SelectedNotes(col, [])
        table = PreviewTable(parent_widget, is_dark_mode, selected_notes.get_notes)
        qtbot.addWidget(table)

        # Test with empty note IDs
        table.show_notes(selected_notes, ["Front", "Back"])

        assert table.rowCount() == 0
        assert table.columnCount() == 0

        # Test with empty selected fields
        table.show_notes(SelectedNotes(col, [cast("NoteId", 123)]), [])

        assert table.rowCount() == 0
        assert table.columnCount() == 0

    @with_test_collection("empty_collection")
    @patch("transformerman.ui.preview_table.QueryOp")
    def test_table_headers_set(
        self,
        mock_query_op: Mock,
        qtbot: QtBot,
        parent_widget: QWidget,
        is_dark_mode: bool,
        col: TestCollection,
        test_note_ids: list[NoteId],
        test_selected_fields: list[str],
    ) -> None:
        """Test that table headers are set correctly."""
        selected_notes = SelectedNotes(col, [])
        table = PreviewTable(parent_widget, is_dark_mode, selected_notes.get_notes)
        qtbot.addWidget(table)

        mock_op_instance = Mock()
        mock_op_instance.success.return_value = mock_op_instance
        mock_op_instance.failure.return_value = mock_op_instance
        mock_op_instance.run_in_background.return_value = None
        mock_query_op.return_value = mock_op_instance

        table.show_notes(SelectedNotes(col, test_note_ids), test_selected_fields)

        assert table.columnCount() == len(test_selected_fields)
        assert table.rowCount() == len(test_note_ids)

        for i, field in enumerate(test_selected_fields):
            header_item = table.horizontalHeaderItem(i)
            assert header_item is not None
            assert header_item.text() == field

    @with_test_collection("empty_collection")
    @patch("transformerman.ui.preview_table.QueryOp")
    def test_highlighting_mode(
        self,
        mock_query_op: Mock,
        qtbot: QtBot,
        parent_widget: QWidget,
        is_dark_mode: bool,
        col: TestCollection,
        test_note_ids: list[NoteId],
        test_selected_fields: list[str],
        test_field_updates: FieldUpdates,
    ) -> None:
        """Test that table enters highlighted mode when field updates are provided."""
        selected_notes = SelectedNotes(col, [])
        table = PreviewTable(parent_widget, is_dark_mode, selected_notes.get_notes)
        qtbot.addWidget(table)

        success_callback = None

        def capture_success(
            parent: QWidget,
            op: Any,
            success: Any,
        ) -> Mock:
            nonlocal success_callback
            success_callback = success
            mock_op_instance = Mock()
            mock_op_instance.success.return_value = mock_op_instance
            mock_op_instance.failure.return_value = mock_op_instance
            mock_op_instance.run_in_background.return_value = None
            return mock_op_instance

        mock_query_op.side_effect = capture_success

        table.show_notes(SelectedNotes(col, test_note_ids), test_selected_fields, test_field_updates)

        assert table.is_highlighted is True
        assert isinstance(table.highlight_color, QColor)
        assert table.highlight_color.isValid()

        actual_color = table.highlight_color.getRgb()[:3]
        expected_color = DARK_MODE_HIGHLIGHT_COLOR if is_dark_mode else LIGHT_MODE_HIGHLIGHT_COLOR
        assert actual_color == expected_color

        assert table.rowCount() == len(test_note_ids)
        assert table.columnCount() == len(test_selected_fields)
        mock_query_op.assert_called_once()

        # Verify highlighting when data is loaded
        assert success_callback

        mock_notes_data = [
            {
                "note": create_mock_note(note_id, test_field_updates.get(note_id, {})),
                "note_updates": test_field_updates.get(note_id, {}),
            }
            for note_id in test_note_ids
        ]
        success_callback(mock_notes_data)

        for row in range(table.rowCount()):
            for col_idx in range(table.columnCount()):
                item = table.item(row, col_idx)
                assert item
                field_name = test_selected_fields[col_idx]
                note_id = test_note_ids[row]
                note_updates = test_field_updates.get(note_id, {})

                if field_name in note_updates:
                    assert item.background().color() == table.highlight_color
                else:
                    assert item.background().color() != table.highlight_color

    @with_test_collection("empty_collection")
    @patch("transformerman.ui.preview_table.QueryOp")
    def test_no_highlighting_without_field_updates(
        self,
        mock_query_op: Mock,
        qtbot: QtBot,
        parent_widget: QWidget,
        is_dark_mode: bool,
        col: TestCollection,
        test_note_ids: list[NoteId],
        test_selected_fields: list[str],
    ) -> None:
        """Test that table is not in highlighted mode without field updates."""
        selected_notes = SelectedNotes(col, [])
        table = PreviewTable(parent_widget, is_dark_mode, selected_notes.get_notes)
        qtbot.addWidget(table)

        mock_op_instance = Mock()
        mock_op_instance.success.return_value = mock_op_instance
        mock_op_instance.failure.return_value = mock_op_instance
        mock_op_instance.run_in_background.return_value = None
        mock_query_op.return_value = mock_op_instance

        table.show_notes(
            SelectedNotes(col, test_note_ids),
            test_selected_fields,
            None,  # No field updates
        )

        assert table.is_highlighted is False
        assert table.highlight_color is not None
        assert isinstance(table.highlight_color, QColor)

        assert table.rowCount() == len(test_note_ids)
        assert table.columnCount() == len(test_selected_fields)

    @with_test_collection("empty_collection")
    @patch("transformerman.ui.preview_table.QueryOp")
    def test_background_loading_setup(
        self,
        mock_query_op: Mock,
        qtbot: QtBot,
        parent_widget: QWidget,
        is_dark_mode: bool,
        col: TestCollection,
        test_note_ids: list[NoteId],
        test_selected_fields: list[str],
    ) -> None:
        """Test that background loading is set up correctly."""
        selected_notes = SelectedNotes(col, [])
        table = PreviewTable(parent_widget, is_dark_mode, selected_notes.get_notes)
        qtbot.addWidget(table)

        mock_op_instance = Mock()
        mock_op_instance.success.return_value = mock_op_instance
        mock_op_instance.failure.return_value = mock_op_instance
        mock_op_instance.run_in_background.return_value = None
        mock_query_op.return_value = mock_op_instance

        table.show_notes(SelectedNotes(col, test_note_ids), test_selected_fields, None)

        assert table.rowCount() == len(test_note_ids)
        assert table.columnCount() == len(test_selected_fields)
        mock_query_op.assert_called_once()
