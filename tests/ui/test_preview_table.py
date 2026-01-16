"""Tests for preview table.

Tests the PreviewTable widget which displays note previews with background loading
and highlighting capabilities."""
from __future__ import annotations

from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot
    from anki.notes import NoteId

from aqt.qt import QWidget, QColor

from transformerman.ui.transform.preview_table import (
    PreviewTable,
    DARK_MODE_HIGHLIGHT_COLOR,
    LIGHT_MODE_HIGHLIGHT_COLOR,
)
from transformerman.lib.field_updates import FieldUpdates
from transformerman.lib.selected_notes import SelectedNotes
from tests.tools import with_test_collection, TestCollection, test_collection as test_collection_fixture

col = test_collection_fixture


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

    @with_test_collection("two_deck_collection")
    def test_table_headers_set(
        self,
        qtbot: QtBot,
        parent_widget: QWidget,
        is_dark_mode: bool,
        col: TestCollection,
    ) -> None:
        """Test that table headers are set correctly."""
        selected_fields = ["Front", "Back"]
        selected_notes = SelectedNotes(col, col.find_notes(""))
        table = PreviewTable(parent_widget, is_dark_mode, selected_notes.get_notes)
        qtbot.addWidget(table)

        table.show_notes(selected_notes, selected_fields)

        assert table.columnCount() == len(selected_fields)
        assert table.rowCount() == 16

        for i, field in enumerate(selected_fields):
            header_item = table.horizontalHeaderItem(i)
            assert header_item is not None
            assert header_item.text() == field

    @with_test_collection("two_deck_collection")
    def test_highlighting_mode(
        self,
        qtbot: QtBot,
        parent_widget: QWidget,
        is_dark_mode: bool,
        col: TestCollection,
    ) -> None:
        """Test that table enters highlighted mode when field updates are provided."""
        selected_fields = ["Front", "Back"]
        note_ids = col.find_notes("")
        field_updates = FieldUpdates({
            note_ids[0]: {"Front": "Updated Front 1", "Back": "Updated Back 1"},
            note_ids[1]: {"Front": "Updated Front 2", "Back": "Updated Back 2"},
        })
        selected_notes = SelectedNotes(col, note_ids)
        table = PreviewTable(parent_widget, is_dark_mode, selected_notes.get_notes)
        qtbot.addWidget(table)

        table.show_notes(selected_notes, selected_fields, field_updates)

        assert table.is_highlighted is True
        assert isinstance(table.highlight_color, QColor)
        assert table.highlight_color.isValid()

        actual_color = table.highlight_color.getRgb()[:3]
        expected_color = DARK_MODE_HIGHLIGHT_COLOR if is_dark_mode else LIGHT_MODE_HIGHLIGHT_COLOR
        assert actual_color == expected_color

        assert table.rowCount() == 16
        assert table.columnCount() == len(selected_fields)

        for row in range(table.rowCount()):
            for col_idx in range(table.columnCount()):
                item = table.item(row, col_idx)
                assert item
                field_name = selected_fields[col_idx]
                note_id = note_ids[row]
                note_updates = field_updates.get(note_id, {})

                if field_name in note_updates:
                    assert item.background().color() == table.highlight_color
                else:
                    assert item.background().color() != table.highlight_color

    @with_test_collection("two_deck_collection")
    def test_no_highlighting_without_field_updates(
        self,
        qtbot: QtBot,
        parent_widget: QWidget,
        is_dark_mode: bool,
        col: TestCollection,
    ) -> None:
        """Test that table is not in highlighted mode without field updates."""
        selected_fields = ["Front", "Back"]
        selected_notes = SelectedNotes(col, col.find_notes(""))
        table = PreviewTable(parent_widget, is_dark_mode, selected_notes.get_notes)
        qtbot.addWidget(table)

        table.show_notes(selected_notes, selected_fields, None)

        assert table.is_highlighted is False
        assert table.highlight_color is not None
        assert isinstance(table.highlight_color, QColor)

        assert table.rowCount() == 16
        assert table.columnCount() == len(selected_fields)

    @with_test_collection("two_deck_collection")
    def test_background_loading_setup(
        self,
        qtbot: QtBot,
        parent_widget: QWidget,
        is_dark_mode: bool,
        col: TestCollection,
    ) -> None:
        """Test that background loading is set up correctly."""
        selected_fields = ["Front", "Back"]
        selected_notes = SelectedNotes(col, col.find_notes(""))
        table = PreviewTable(parent_widget, is_dark_mode, selected_notes.get_notes)
        qtbot.addWidget(table)

        table.show_notes(selected_notes, selected_fields, None)

        assert table.rowCount() == 16
        assert table.columnCount() == len(selected_fields)
