"""
Tests for GeneratedNotesTable.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from aqt.qt import QWidget

from transformerman.ui.generate.generated_notes_table import GeneratedNotesTable
from transformerman.lib.xml_parser import NewNote

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


class TestGeneratedNotesTable:
    def test_discard_row(self, qtbot: QtBot) -> None:
        widget = QWidget()
        table = GeneratedNotesTable(widget)
        qtbot.addWidget(table)

        notes = [
            NewNote({"Front": "F1", "Back": "B1"}),
            NewNote({"Front": "F2", "Back": "B2"}),
            NewNote({"Front": "F3", "Back": "B3"}),
        ]

        table.set_notes(notes)
        assert table.rowCount() == 3

        # Test discarding a single row (index 1)
        table.discard_selected_rows(clicked_row=1)
        assert table.rowCount() == 2

        remaining_notes = table.get_all_notes()
        assert remaining_notes[0]["Front"] == "F1"
        assert remaining_notes[1]["Front"] == "F3"

    def test_discard_multiple_rows(self, qtbot: QtBot) -> None:
        widget = QWidget()
        table = GeneratedNotesTable(widget)
        qtbot.addWidget(table)

        notes = [
            NewNote({"Front": "F1", "Back": "B1"}),
            NewNote({"Front": "F2", "Back": "B2"}),
            NewNote({"Front": "F3", "Back": "B3"}),
        ]

        table.set_notes(notes)

        table.selectRow(0)

        # Select items in row 0 and 2
        for col in range(table.columnCount()):
            item0 = table.item(0, col)
            if item0:
                item0.setSelected(True)
            item2 = table.item(2, col)
            if item2:
                item2.setSelected(True)

        # Discard with clicked_row=0 (which is in selection)
        table.discard_selected_rows(clicked_row=0)

        assert table.rowCount() == 1
        remaining_notes = table.get_all_notes()
        assert remaining_notes[0]["Front"] == "F2"

    def test_discard_clicked_outside_selection(self, qtbot: QtBot) -> None:
        widget = QWidget()
        table = GeneratedNotesTable(widget)
        qtbot.addWidget(table)

        notes = [
            NewNote({"Front": "F1", "Back": "B1"}),
            NewNote({"Front": "F2", "Back": "B2"}),
            NewNote({"Front": "F3", "Back": "B3"}),
        ]

        table.set_notes(notes)

        # Select row 0
        table.selectRow(0)

        # Click on row 2 (which is NOT selected)
        # This should discard row 2 ONLY, ignoring the selection of row 0
        table.discard_selected_rows(clicked_row=2)

        assert table.rowCount() == 2
        remaining_notes = table.get_all_notes()
        assert remaining_notes[0]["Front"] == "F1"
        assert remaining_notes[1]["Front"] == "F2"

    def test_filter_invalid_notes(self, qtbot: QtBot) -> None:
        widget = QWidget()
        table = GeneratedNotesTable(widget)
        qtbot.addWidget(table)

        notes = [
            NewNote({"Front": "F1", "Back": "B1"}),
            NewNote({"Front": "", "Back": ""}),  # Invalid
            NewNote({"Front": "F3", "Back": ""}),  # Valid (has 1 field)
            NewNote({"Other": "Value"}),  # Invalid (no matching fields)
        ]

        table.set_notes(notes)
        # Should only have F1 and F3
        assert table.rowCount() == 2
        remaining_notes = table.get_all_notes()
        assert remaining_notes[0]["Front"] == "F1"
        assert remaining_notes[1]["Front"] == "F3"

    def test_append_invalid_notes(self, qtbot: QtBot) -> None:
        widget = QWidget()
        table = GeneratedNotesTable(widget)
        qtbot.addWidget(table)

        table.set_notes([NewNote({"Front": "F1", "Back": "B1"})])
        assert table.rowCount() == 1

        new_notes = [
            NewNote({"Front": "", "Back": ""}),  # Invalid
            NewNote({"Front": "F2", "Back": "B2"}),  # Valid
        ]

        table.append_notes(new_notes)
        assert table.rowCount() == 2
        remaining_notes = table.get_all_notes()
        assert remaining_notes[1]["Front"] == "F2"
