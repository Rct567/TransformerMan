"""
TransformerMan by Rick Zuidhoek. Licensed under the GNU GPL-3.0.
See <https://www.gnu.org/licenses/gpl-3.0.html> for details.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from aqt.qt import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QWidget,
    QScrollArea,
)

if TYPE_CHECKING:
    from anki.collection import Collection
    from anki.notes import NoteId


class ResultsDialog(QDialog):
    """Dialog to show transformation results and updated notes."""

    def __init__(
        self,
        parent: QWidget,
        col: Collection,
        note_ids: list[NoteId],
        selected_fields: set[str],
        note_type_name: str,
        results: dict[str, int],
    ) -> None:
        """
        Initialize the results dialog.

        Args:
            parent: Parent widget.
            col: Anki collection.
            note_ids: List of note IDs that were transformed.
            selected_fields: Set of field names that were selected for filling.
            note_type_name: Name of the note type.
            results: Dictionary with transformation results:
                - "updated": Number of fields updated
                - "failed": Number of notes that failed
                - "batches_processed": Number of batches processed
        """
        super().__init__(parent)
        self.col = col
        self.note_ids = note_ids
        self.selected_fields = selected_fields
        self.note_type_name = note_type_name
        self.results = results

        self._setup_ui()
        self._load_results()
        self._load_updated_notes()

    def _setup_ui(self) -> None:
        """Setup the UI components."""
        self.setWindowTitle("Transformation Results")
        self.setMinimumWidth(700)
        self.setMinimumHeight(500)

        layout = QVBoxLayout()

        # Results summary section
        layout.addWidget(QLabel("<h3>Transformation Results</h3>"))

        self.results_label = QLabel()
        layout.addWidget(self.results_label)

        # Separator
        layout.addWidget(QLabel("<hr>"))

        # Updated notes section
        layout.addWidget(QLabel("<h3>Updated Notes</h3>"))
        layout.addWidget(QLabel(f"Showing notes with updated fields (note type: {self.note_type_name}):"))

        # Scrollable table for notes
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setMinimumHeight(300)

        self.notes_table = QTableWidget()
        self.notes_table.setAlternatingRowColors(True)
        vertical_header = self.notes_table.verticalHeader()
        if vertical_header:
            vertical_header.setVisible(False)
        scroll_area.setWidget(self.notes_table)

        layout.addWidget(scroll_area)

        # Close button
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.close_button = QPushButton("Close")
        self.close_button.clicked.connect(self.accept)
        button_layout.addWidget(self.close_button)

        layout.addLayout(button_layout)

        self.setLayout(layout)

    def _load_results(self) -> None:
        """Load and display transformation results."""
        updated = self.results.get("updated", 0)
        failed = self.results.get("failed", 0)
        batches_processed = self.results.get("batches_processed", 0)

        html = f"""
        <div style="font-size: 16px;">
            <p><b>Batches processed:</b> {batches_processed}</p>
        """

        if updated > 0:
            html += f'<p style="color: #388e3c;"><b>Updated notes:</b> {updated}</p>'
        else:
            html += f'<p><b>Updated notes:</b>0</p>'

        if failed > 0:
            html += f'<p style="color: #d32f2f;"><b>Failed notes:</b> {failed}</p>'
        else:
            html += f'<p><b>Failed notes:</b> 0</p>'

        html += "</div>"

        self.results_label.setText(html)

    def _load_updated_notes(self) -> None:
        """Load and display updated notes with selected fields."""
        if not self.selected_fields:
            self.notes_table.clear()
            self.notes_table.setColumnCount(0)
            self.notes_table.setRowCount(0)
            self.notes_table.setHorizontalHeaderLabels([])
            return

        # Get fresh notes from collection
        notes = []
        for note_id in self.note_ids:
            try:
                note = self.col.get_note(note_id)
                notes.append(note)
            except Exception:
                continue

        if not notes:
            self.notes_table.clear()
            self.notes_table.setColumnCount(0)
            self.notes_table.setRowCount(0)
            self.notes_table.setHorizontalHeaderLabels([])
            return

        # Setup columns: Note ID + selected fields
        columns = ["Note ID"] + sorted(self.selected_fields)
        self.notes_table.setColumnCount(len(columns))
        self.notes_table.setHorizontalHeaderLabels(columns)

        self.notes_table.setRowCount(len(notes))

        for row, note in enumerate(notes):
            # Note ID
            item = QTableWidgetItem(str(note.id))
            item.setToolTip(f"Note ID: {note.id}")
            self.notes_table.setItem(row, 0, item)

            # Selected fields
            for col_idx, field_name in enumerate(sorted(self.selected_fields), start=1):
                if field_name in note:
                    content = note[field_name]
                    # Truncate long content for display
                    display_content = content
                    if len(content) > 100:
                        display_content = content[:97] + "..."

                    item = QTableWidgetItem(display_content)
                    item.setToolTip(content)  # Show full content on hover
                    self.notes_table.setItem(row, col_idx, item)
                else:
                    item = QTableWidgetItem("")
                    self.notes_table.setItem(row, col_idx, item)

        # Adjust column widths - Note ID fixed but resizable, other columns expand equally
        header = self.notes_table.horizontalHeader()
        if header:
            # Set Note ID column to a reasonable fixed width but still resizable
            self.notes_table.setColumnWidth(0, 120)
            header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)

            # Set all field columns to Stretch mode so they expand equally
            for col in range(1, self.notes_table.columnCount()):
                header.setSectionResizeMode(col, QHeaderView.ResizeMode.Stretch)
