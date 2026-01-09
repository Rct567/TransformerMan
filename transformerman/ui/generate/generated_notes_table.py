"""
TransformerMan by Rick Zuidhoek. Licensed under the GNU GPL-3.0.
See <https://www.gnu.org/licenses/gpl-3.0.html> for details.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from aqt.qt import (
    QTableWidget,
    QTableWidgetItem,
    QWidget,
    QHeaderView,
)

if TYPE_CHECKING:
    from collections.abc import Sequence


class GeneratedNotesTable(QTableWidget):
    """
    Editable table for displaying and modifying generated notes.
    """

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setAlternatingRowColors(True)
        header = self.horizontalHeader()
        if header:
            header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        v_header = self.verticalHeader()
        if v_header:
            v_header.setVisible(False)
        self.setMinimumHeight(200)

    def update_columns(self, field_names: Sequence[str]) -> None:
        """Update the columns of the table."""
        if self.rowCount() > 0:
            raise ValueError("Cannot update columns when table is not empty")
        self.setColumnCount(len(field_names))
        self.setHorizontalHeaderLabels(field_names)

    def set_notes(self, notes: list[dict[str, str]], field_names: Sequence[str]) -> None:
        """
        Set the notes to display in the table.

        Args:
            notes: List of dictionaries representing notes.
            field_names: List of field names to show as columns.
        """
        self.clear()
        self.update_columns(field_names)
        self.setRowCount(len(notes))

        for row, note in enumerate(notes):
            for col, field in enumerate(field_names):
                content = note.get(field, "")
                item = QTableWidgetItem(content)
                self.setItem(row, col, item)

    def append_notes(self, notes: list[dict[str, str]], field_names: Sequence[str]) -> None:
        """
        Append new notes to the existing table.

        Args:
            notes: List of new notes to append.
            field_names: List of field names (must match current columns).
        """
        if self.columnCount() == 0:
            self.set_notes(notes, field_names)
            return
        if self.columnCount() != len(field_names):
            raise ValueError("Number of columns must match number of field names")

        current_row_count = self.rowCount()
        self.setRowCount(current_row_count + len(notes))

        for i, note in enumerate(notes):
            row = current_row_count + i
            for col, field in enumerate(field_names):
                content = note.get(field, "")
                item = QTableWidgetItem(content)
                self.setItem(row, col, item)

    def get_all_notes(self) -> list[dict[str, str]]:
        """
        Return all notes currently in the table as a list of dictionaries.
        """
        notes = []
        field_names = []
        for i in range(self.columnCount()):
            item = self.horizontalHeaderItem(i)
            field_names.append(item.text() if item else f"Field {i}")

        for row in range(self.rowCount()):
            note_data = {}
            for col, field in enumerate(field_names):
                item = self.item(row, col)
                note_data[field] = item.text() if item else ""
            notes.append(note_data)

        return notes
