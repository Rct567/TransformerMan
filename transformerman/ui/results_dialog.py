"""
TransformerMan by Rick Zuidhoek. Licensed under the GNU GPL-3.0.
See <https://www.gnu.org/licenses/gpl-3.0.html> for details.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from aqt.qt import (
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
)

from .base_dialog import TransformerManBaseDialog

if TYPE_CHECKING:
    from anki.collection import Collection
    from anki.notes import NoteId


class ResultsDialog(TransformerManBaseDialog):
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

    def _setup_ui(self) -> None:
        """Setup the UI components."""
        self.setWindowTitle("Transformation Results")
        self.setMinimumWidth(500)
        self.setMinimumHeight(300)

        layout = QVBoxLayout()

        # Results summary section
        layout.addWidget(QLabel("<h3>Transformation Results</h3>"))

        self.results_label = QLabel()
        layout.addWidget(self.results_label)

        # Close button
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.close_button = QPushButton("Close")
        self.close_button.clicked.connect(self.accept)
        button_layout.addWidget(self.close_button)

        layout.addLayout(button_layout)
        layout.addStretch()

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
            html += '<p><b>Updated notes:</b>0</p>'

        if failed > 0:
            html += f'<p style="color: #d32f2f;"><b>Failed notes:</b> {failed}</p>'
        else:
            html += '<p><b>Failed notes:</b> 0</p>'

        html += "</div>"

        self.results_label.setText(html)
