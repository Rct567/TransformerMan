"""
Tests for preview table.

Tests the PreviewTable widget which displays note previews with background loading
and highlighting capabilities.
"""

from __future__ import annotations


from typing import TYPE_CHECKING, cast, Any
from unittest.mock import Mock, patch

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot
    from anki.notes import NoteId
    from collections.abc import Sequence

from aqt.qt import QWidget, QColor

from transformerman.ui.preview_table import (
    PreviewTable,
    DARK_MODE_HIGHLIGHT_COLOR,
    LIGHT_MODE_HIGHLIGHT_COLOR,
)
from transformerman.lib.selected_notes import SelectedNotes
from tests.tools import with_test_collection, MockCollection, test_collection as test_collection_fixture

col = test_collection_fixture


class TestPreviewTable:
    """Test class for PreviewTable."""

    def test_table_creation(
        self,
        qtbot: QtBot,
        parent_widget: QWidget,
        is_dark_mode: bool,
    ) -> None:
        """Test that preview table can be created."""
        table = PreviewTable(parent_widget, is_dark_mode)
        qtbot.addWidget(table)

        assert table.parent() is parent_widget
        assert table.is_dark_mode == is_dark_mode

        # Table should have certain properties set
        assert table.alternatingRowColors()

        # Vertical header should be hidden
        vertical_header = table.verticalHeader()
        if vertical_header:
            assert not vertical_header.isVisible()

        # Should have minimum height
        assert table.minimumHeight() >= 150
        assert table.rowCount() == 0
        assert table.columnCount() == 0


    @with_test_collection("empty_collection")
    def test_set_note_fields_update_with_empty_data(
        self,
        qtbot: QtBot,
        parent_widget: QWidget,
        is_dark_mode: bool,
        col: MockCollection,
    ) -> None:
        """Test that table handles empty note IDs or fields."""
        table = PreviewTable(parent_widget, is_dark_mode)
        qtbot.addWidget(table)
        selected_notes = SelectedNotes(col, [])
        table.set_selected_notes(selected_notes)

        # Test with empty note IDs
        table.set_note_fields_update([], ["Front", "Back"])

        assert table.rowCount() == 0
        assert table.columnCount() == 0

        # Test with empty selected fields
        table.set_note_fields_update([cast("NoteId", 123)], [])

        assert table.rowCount() == 0
        assert table.columnCount() == 0

    @with_test_collection("empty_collection")
    @patch('transformerman.ui.preview_table.QueryOp')
    def test_table_headers_set(
        self,
        mock_query_op: Mock,
        qtbot: QtBot,
        parent_widget: QWidget,
        is_dark_mode: bool,
        col: MockCollection,
        test_note_ids: list[NoteId],
        test_selected_fields: Sequence[str],
    ) -> None:
        """Test that table headers are set correctly."""
        table = PreviewTable(parent_widget, is_dark_mode)
        qtbot.addWidget(table)
        selected_notes = SelectedNotes(col, [])
        table.set_selected_notes(selected_notes)

        # Mock QueryOp to avoid requiring main window
        mock_op_instance = Mock()
        mock_op_instance.success.return_value = mock_op_instance
        mock_op_instance.failure.return_value = mock_op_instance
        mock_op_instance.run_in_background.return_value = None
        mock_query_op.return_value = mock_op_instance

        # Convert set to list for consistent ordering
        selected_fields_list = list(test_selected_fields)

        table.set_note_fields_update(test_note_ids, selected_fields_list)

        # Should have correct number of columns
        assert table.columnCount() == len(selected_fields_list)
        assert table.rowCount() == len(test_note_ids)

        # Check header labels
        for i, field in enumerate(selected_fields_list):
            header_item = table.horizontalHeaderItem(i)
            assert header_item is not None
            assert header_item.text() == field



    @with_test_collection("empty_collection")
    @patch('transformerman.ui.preview_table.QueryOp')
    def test_highlighting_with_field_updates(
        self,
        mock_query_op: Mock,
        qtbot: QtBot,
        parent_widget: QWidget,
        is_dark_mode: bool,
        col: MockCollection,
        test_note_ids: list[NoteId],
        test_selected_fields: Sequence[str],
        test_field_updates: dict[NoteId, dict[str, str]],
    ) -> None:
        """Test that table highlights cells with field updates."""
        table = PreviewTable(parent_widget, is_dark_mode)
        qtbot.addWidget(table)
        selected_notes = SelectedNotes(col, [])
        table.set_selected_notes(selected_notes)

        selected_fields_list = list(test_selected_fields)

        # We'll capture the success callback to simulate note loading
        success_callback = None
        def mock_query_op_constructor(
            parent: QWidget,
            op: Any,  # Callable[[Collection], Any]
            success: Any,  # Callable[[Any], None]
        ) -> Mock:
            nonlocal success_callback
            success_callback = success
            # Return a mock that chains methods
            mock_op_instance = Mock()
            mock_op_instance.success.return_value = mock_op_instance
            mock_op_instance.failure.return_value = mock_op_instance
            mock_op_instance.run_in_background.return_value = None
            return mock_op_instance

        mock_query_op.side_effect = mock_query_op_constructor

        # Set up table with field updates
        table.set_note_fields_update(
            test_note_ids,
            selected_fields_list,
            test_field_updates
        )

        # Verify table is in highlighted mode when field updates are provided
        assert table.is_highlighted is True
        assert isinstance(table.highlight_color, QColor)

        # Verify the color is valid (not transparent/empty)
        assert table.highlight_color.isValid()

        # Verify the correct color is used based on dark mode
        actual_color = table.highlight_color.getRgb()[:3]  # Get RGB tuple
        if is_dark_mode:
            expected_color = DARK_MODE_HIGHLIGHT_COLOR
        else:
            expected_color = LIGHT_MODE_HIGHLIGHT_COLOR
        assert actual_color == expected_color

        # Table structure should be set up
        assert table.rowCount() == len(test_note_ids)
        assert table.columnCount() == len(selected_fields_list)

        # QueryOp should have been created
        mock_query_op.assert_called_once()

        # Simulate note loading by calling the success callback with mock data
        if success_callback:
            # Create mock note data that matches the field updates
            mock_notes_data = []
            for row, note_id in enumerate(test_note_ids):
                note_updates = test_field_updates.get(note_id, {})
                # Create a mock note
                mock_note = Mock()
                mock_note.id = note_id
                # Set up field values - each field returns "Original [field_name]"
                def make_getitem(field_note_id: int) -> Any:
                    return lambda key: f"Original {key} for note {field_note_id}"  # pyright: ignore
                mock_note.__getitem__ = Mock(side_effect=make_getitem(note_id))

                note_data = {
                    "note": mock_note,
                    "note_updates": note_updates,
                }
                mock_notes_data.append((row, note_data))

            # Call the success callback
            success_callback(mock_notes_data)

            # Now verify that cells with updates are highlighted
            for row in range(table.rowCount()):
                for col_idx in range(table.columnCount()):
                    item = table.item(row, col_idx)
                    if item:
                        field_name = selected_fields_list[col_idx]
                        note_id = test_note_ids[row]
                        note_updates = test_field_updates.get(note_id, {})

                        if field_name in note_updates:
                            # Should be highlighted
                            assert item.background().color() == table.highlight_color
                        else:
                            # Should not be highlighted
                            assert item.background().color() != table.highlight_color

        # Also test that without field updates, table is not in highlighted mode
        table2 = PreviewTable(parent_widget, is_dark_mode)
        qtbot.addWidget(table2)
        table2.set_selected_notes(selected_notes)

        # Reset mock for second test
        success_callback2 = None
        def mock_query_op_constructor2(
            parent: QWidget,
            op: Any,
            success: Any,
        ) -> Mock:
            nonlocal success_callback2
            success_callback2 = success
            mock_op_instance = Mock()
            mock_op_instance.success.return_value = mock_op_instance
            mock_op_instance.failure.return_value = mock_op_instance
            mock_op_instance.run_in_background.return_value = None
            return mock_op_instance

        mock_query_op.reset_mock()
        mock_query_op.side_effect = mock_query_op_constructor2

        table2.set_note_fields_update(
            test_note_ids,
            selected_fields_list,
            None  # No field updates
        )

        # Without field updates, table should not be in highlighted mode
        assert table2.is_highlighted is False
        # But highlight_color should still be set (always set in constructor)
        assert table2.highlight_color is not None
        assert isinstance(table2.highlight_color, QColor)

        # Table structure should still be set up
        assert table2.rowCount() == len(test_note_ids)
        assert table2.columnCount() == len(selected_fields_list)

    @with_test_collection("empty_collection")
    @patch('transformerman.ui.preview_table.QueryOp')
    def test_background_loading_setup(
        self,
        mock_query_op: Mock,
        qtbot: QtBot,
        parent_widget: QWidget,
        is_dark_mode: bool,
        col: MockCollection,
        test_note_ids: list[NoteId],
        test_selected_fields: Sequence[str],
    ) -> None:
        """Test that background loading is set up correctly."""
        table = PreviewTable(parent_widget, is_dark_mode)
        qtbot.addWidget(table)
        selected_notes = SelectedNotes(col, [])
        table.set_selected_notes(selected_notes)

        selected_fields_list = list(test_selected_fields)

        # Mock QueryOp to avoid requiring main window
        mock_op_instance = Mock()
        mock_op_instance.success.return_value = mock_op_instance
        mock_op_instance.failure.return_value = mock_op_instance
        mock_op_instance.run_in_background.return_value = None
        mock_query_op.return_value = mock_op_instance

        # We can't easily test the full background loading without
        # complex mocking, but we can verify the method doesn't crash
        table.set_note_fields_update(
            test_note_ids,
            selected_fields_list,
            None  # No field updates
        )

        # Should set up table structure
        assert table.rowCount() == len(test_note_ids)
        assert table.columnCount() == len(selected_fields_list)

        # QueryOp should have been created
        mock_query_op.assert_called_once()

    @with_test_collection("empty_collection")
    @patch('transformerman.ui.preview_table.QueryOp')
    def test_table_with_field_updates(
        self,
        mock_query_op: Mock,
        qtbot: QtBot,
        parent_widget: QWidget,
        is_dark_mode: bool,
        col: MockCollection,
        test_note_ids: list[NoteId],
        test_selected_fields: Sequence[str],
        test_field_updates: dict[NoteId, dict[str, str]],
    ) -> None:
        """Test that table handles field updates for highlighting."""
        table = PreviewTable(parent_widget, is_dark_mode)
        qtbot.addWidget(table)
        selected_notes = SelectedNotes(col, [])
        table.set_selected_notes(selected_notes)

        selected_fields_list = list(test_selected_fields)

        # Mock QueryOp to avoid requiring main window
        mock_op_instance = Mock()
        mock_op_instance.success.return_value = mock_op_instance
        mock_op_instance.failure.return_value = mock_op_instance
        mock_op_instance.run_in_background.return_value = None
        mock_query_op.return_value = mock_op_instance

        # Set up table with field updates
        table.set_note_fields_update(
            test_note_ids,
            selected_fields_list,
            test_field_updates
        )

        # Should be in highlighted mode when field updates are provided
        assert table.is_highlighted is True
        # Highlight color should always be set (in constructor)
        assert table.highlight_color is not None

        # Table structure should be set up
        assert table.rowCount() == len(test_note_ids)
        assert table.columnCount() == len(selected_fields_list)

        # QueryOp should have been created
        mock_query_op.assert_called_once()
