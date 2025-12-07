"""
Tests for preview table.

Tests the PreviewTable widget which displays note previews with background loading
and highlighting capabilities.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast
from unittest.mock import Mock, patch

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot
    from anki.notes import NoteId

from aqt.qt import QWidget, QTableWidgetItem

from transformerman.ui.preview_table import PreviewTable


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

    def test_set_selected_notes(
        self,
        qtbot: QtBot,
        parent_widget: QWidget,
        is_dark_mode: bool,
        selected_notes: Mock,
    ) -> None:
        """Test that selected notes can be set."""
        table = PreviewTable(parent_widget, is_dark_mode)
        qtbot.addWidget(table)

        table.set_selected_notes(selected_notes)

        assert table.selected_notes is selected_notes

    def test_set_note_fields_update_with_empty_data(
        self,
        qtbot: QtBot,
        parent_widget: QWidget,
        is_dark_mode: bool,
        selected_notes: Mock,
    ) -> None:
        """Test that table handles empty note IDs or fields."""
        table = PreviewTable(parent_widget, is_dark_mode)
        qtbot.addWidget(table)
        table.set_selected_notes(selected_notes)

        # Test with empty note IDs
        table.set_note_fields_update([], ["Front", "Back"])

        assert table.rowCount() == 0
        assert table.columnCount() == 0

        # Test with empty selected fields
        table.set_note_fields_update([cast("NoteId", 123)], [])

        assert table.rowCount() == 0
        assert table.columnCount() == 0

    @patch('transformerman.ui.preview_table.QueryOp')
    def test_table_headers_set(
        self,
        mock_query_op: Mock,
        qtbot: QtBot,
        parent_widget: QWidget,
        is_dark_mode: bool,
        selected_notes: Mock,
        test_note_ids: list[NoteId],
        test_selected_fields: set[str],
    ) -> None:
        """Test that table headers are set correctly."""
        table = PreviewTable(parent_widget, is_dark_mode)
        qtbot.addWidget(table)
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

        # Check header labels
        for i, field in enumerate(selected_fields_list):
            header_item = table.horizontalHeaderItem(i)
            assert header_item is not None
            assert header_item.text() == field

    def test_create_table_item_truncation(
        self,
        qtbot: QtBot,
        parent_widget: QWidget,
        is_dark_mode: bool,
    ) -> None:
        """Test that table items truncate long content."""
        table = PreviewTable(parent_widget, is_dark_mode)
        qtbot.addWidget(table)

        # Short content should not be truncated
        short_content = "Short"
        item = table._create_table_item(short_content, False)  # type: ignore

        assert isinstance(item, QTableWidgetItem)
        assert item.text() == short_content
        assert item.toolTip() == short_content

        # Long content should be truncated
        long_content = "A" * 100  # Longer than MAX_CONTENT_LENGTH (50)
        item = table._create_table_item(long_content, False)  # type: ignore

        assert len(item.text()) <= 50  # MAX_CONTENT_LENGTH
        assert "..." in item.text()  # Should have ellipsis
        assert item.toolTip() == long_content  # Full content in tooltip

    def test_create_table_item_highlighting(
        self,
        qtbot: QtBot,
        parent_widget: QWidget,
        is_dark_mode: bool,
    ) -> None:
        """Test that table items can be highlighted."""
        table = PreviewTable(parent_widget, is_dark_mode)
        qtbot.addWidget(table)

        # Create highlight color based on dark mode
        if is_dark_mode:
            table.highlight_color = table.highlight_color  # This will be set by the class

        # Test without highlighting
        item = table._create_table_item("Content", False)  # type: ignore
        assert item.background().color().getRgb() != (200, 255, 200)  # Not light green
        assert item.background().color().getRgb() != (50, 150, 50)  # Not dark green

        # Note: We can't easily test highlighting without setting up the full
        # field_updates scenario, but the method should handle it

    @patch('transformerman.ui.preview_table.QueryOp')
    def test_background_loading_setup(
        self,
        mock_query_op: Mock,
        qtbot: QtBot,
        parent_widget: QWidget,
        is_dark_mode: bool,
        selected_notes: Mock,
        test_note_ids: list[NoteId],
        test_selected_fields: set[str],
    ) -> None:
        """Test that background loading is set up correctly."""
        table = PreviewTable(parent_widget, is_dark_mode)
        qtbot.addWidget(table)
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

    @patch('transformerman.ui.preview_table.QueryOp')
    def test_table_with_field_updates(
        self,
        mock_query_op: Mock,
        qtbot: QtBot,
        parent_widget: QWidget,
        is_dark_mode: bool,
        selected_notes: Mock,
        test_note_ids: list[NoteId],
        test_selected_fields: set[str],
        test_field_updates: dict[NoteId, dict[str, str]],
    ) -> None:
        """Test that table handles field updates for highlighting."""
        table = PreviewTable(parent_widget, is_dark_mode)
        qtbot.addWidget(table)
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

        # Should set highlight color based on dark mode
        assert table.highlight_color is not None

        # Table structure should be set up
        assert table.rowCount() == len(test_note_ids)
        assert table.columnCount() == len(selected_fields_list)

        # QueryOp should have been created
        mock_query_op.assert_called_once()

    def test_table_alternating_colors(
        self,
        qtbot: QtBot,
        parent_widget: QWidget,
        is_dark_mode: bool,
    ) -> None:
        """Test that table has alternating row colors enabled."""
        table = PreviewTable(parent_widget, is_dark_mode)
        qtbot.addWidget(table)

        assert table.alternatingRowColors()

    def test_table_minimum_size(
        self,
        qtbot: QtBot,
        parent_widget: QWidget,
        is_dark_mode: bool,
    ) -> None:
        """Test that table has appropriate minimum size."""
        table = PreviewTable(parent_widget, is_dark_mode)
        qtbot.addWidget(table)

        # Should have reasonable minimum height for displaying data
        assert table.minimumHeight() > 0
