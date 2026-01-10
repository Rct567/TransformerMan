"""
TransformerMan by Rick Zuidhoek. Licensed under the GNU GPL-3.0.
See <https://www.gnu.org/licenses/gpl-3.0.html> for details.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from aqt.qt import (
    QTableWidget,
    QTableWidgetItem,
    QColor,
    QWidget,
    QHeaderView,
    Qt,
    QMenu,
    QAction,
    QPoint,
)

if TYPE_CHECKING:
    from ...lib.xml_parser import NewNote
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
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

    def _show_context_menu(self, position: QPoint) -> None:
        """Show context menu for table rows."""
        item = self.itemAt(position)
        if not item:
            return

        menu = QMenu(self)
        discard_action = QAction("Discard", self)
        discard_action.triggered.connect(lambda: self.discard_selected_rows(item.row()))
        menu.addAction(discard_action)
        menu.exec(self.mapToGlobal(position))

    def discard_selected_rows(self, clicked_row: int | None = None) -> None:
        """Discard selected rows, or the clicked row if not in selection."""
        rows = set()
        for selected_item in self.selectedItems():
            rows.add(selected_item.row())

        # If a specific row was clicked and is not in selection, just use that row
        if clicked_row is not None and clicked_row not in rows:
            rows = {clicked_row}

        # Remove in reverse order to maintain indices
        for r in sorted(rows, reverse=True):
            self.removeRow(r)

    def update_columns(self, field_names: Sequence[str]) -> None:
        """Update the columns of the table."""
        if self.rowCount() > 0:
            raise ValueError("Cannot update columns when table is not empty")
        self.setColumnCount(len(field_names))
        self.setHorizontalHeaderLabels(field_names)

    def set_notes(self, notes: Sequence[NewNote]) -> None:
        """
        Set the notes to display in the table.
        Extracts field names from the first note to determine columns.

        Args:
            notes: List of NewNote objects.
        """
        if not notes:
            self.setRowCount(0)
            return

        field_names = list(notes[0].keys())
        self.clear()
        self.update_columns(field_names)
        self.setRowCount(len(notes))

        for row, note in enumerate(notes):
            for col, field in enumerate(field_names):
                content = note.get(field, "")
                item = QTableWidgetItem(content)
                self.setItem(row, col, item)

    def append_notes(self, notes: Sequence[NewNote]) -> None:
        """
        Append new notes to the existing table.

        Args:
            notes: List of new notes to append.
        """
        if self.columnCount() == 0:
            self.set_notes(notes)
            return

        # Get current field names from horizontal header
        field_names = []
        for i in range(self.columnCount()):
            header_item = self.horizontalHeaderItem(i)
            field_names.append(header_item.text() if header_item else f"Field {i}")

        current_row_count = self.rowCount()
        self.setRowCount(current_row_count + len(notes))

        for i, note in enumerate(notes):
            if len(note.keys()) != len(field_names):
                raise ValueError("Number of columns must match number of field names")
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

    def highlight_duplicates(self, duplicates: dict[int, list[str]], start_row: int = 0) -> None:
        """
        Highlight duplicate cells in the table.

        Args:
            duplicates: Mapping of relative row index to list of duplicate field names.
            start_row: The absolute row index where the batch starts.
        """
        # Light orange/red color for duplicates
        duplicate_color = QColor(255, 200, 200)
        if self.parent() and getattr(self.parent(), "is_dark_mode", False):
            duplicate_color = QColor(100, 50, 50)

        for rel_row, fields in duplicates.items():
            row = start_row + rel_row
            if row >= self.rowCount():
                continue

            for field in fields:
                # Find column for this field
                for col in range(self.columnCount()):
                    header_item = self.horizontalHeaderItem(col)
                    if header_item and header_item.text() == field:
                        item = self.item(row, col)
                        if item:
                            item.setBackground(duplicate_color)
                            item.setToolTip(f"Duplicate content in field '{field}'")
                        break
