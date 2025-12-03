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
    QComboBox,
    QCheckBox,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QWidget,
)

if TYPE_CHECKING:
    from anki.collection import Collection
    from anki.notes import NoteId
    from ..lib.lm_client import LMClient
    from ..lib.settings_manager import SettingsManager


class TransformerManMainDialog(QDialog):
    """Main dialog for TransformerMan plugin."""

    def __init__(
        self,
        parent: QWidget,
        col: Collection,
        note_ids: list[NoteId],
        lm_client: LMClient,
        settings_manager: SettingsManager,
    ) -> None:
        """
        Initialize the main dialog.

        Args:
            parent: Parent widget.
            col: Anki collection.
            note_ids: List of selected note IDs.
            lm_client: LM client instance.
            settings_manager: Settings manager instance.
        """
        super().__init__(parent)
        self.col = col
        self.note_ids = note_ids
        self.lm_client = lm_client
        self.settings_manager = settings_manager

        from ..lib.selected_notes import SelectedNotes
        self.selected_notes = SelectedNotes(col, note_ids)

        # State
        self.note_type_counts: dict[str, int] = {}
        self.current_note_type: str = ""
        self.field_checkboxes: dict[str, QCheckBox] = {}
        self.field_instructions: dict[str, QLineEdit] = {}

        self._setup_ui()
        self._load_note_types()

    def _setup_ui(self) -> None:
        """Setup the UI components."""
        self.setWindowTitle("TransformerMan")
        self.setMinimumWidth(500)
        self.setMinimumHeight(400)

        layout = QVBoxLayout()

        # Note type selection
        note_type_layout = QHBoxLayout()
        note_type_layout.addWidget(QLabel("Note Type:"))
        self.note_type_combo = QComboBox()
        self.note_type_combo.currentTextChanged.connect(self._on_note_type_changed)
        note_type_layout.addWidget(self.note_type_combo)
        layout.addLayout(note_type_layout)

        # Notes count label
        self.notes_count_label = QLabel("0 notes selected")
        layout.addWidget(self.notes_count_label)

        # Fields section
        layout.addWidget(QLabel("Select fields to fill:"))

        # Scrollable area for fields
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setMinimumHeight(200)

        self.fields_widget = QWidget()
        self.fields_layout = QVBoxLayout()
        self.fields_widget.setLayout(self.fields_layout)
        scroll_area.setWidget(self.fields_widget)

        layout.addWidget(scroll_area)

        # Transform button
        self.transform_button = QPushButton("Transform")
        self.transform_button.clicked.connect(self._on_transform_clicked)
        self.transform_button.setEnabled(False)
        layout.addWidget(self.transform_button)

        self.setLayout(layout)

    def _load_note_types(self) -> None:
        """Load note types from selected notes."""
        self.note_type_counts = self.selected_notes.get_note_type_counts()

        if not self.note_type_counts:
            self.notes_count_label.setText("No valid notes selected")
            return

        # Populate combo box (already sorted by count)
        for note_type_name in self.note_type_counts.keys():
            self.note_type_combo.addItem(note_type_name)

        # Select the first (most common) note type
        if self.note_type_combo.count() > 0:
            self.note_type_combo.setCurrentIndex(0)

    def _on_note_type_changed(self, note_type_name: str) -> None:
        """Handle note type selection change."""
        if not note_type_name:
            return

        self.current_note_type = note_type_name

        # Update notes count
        filtered_ids = self.selected_notes.filter_by_note_type(note_type_name)
        self.notes_count_label.setText(f"{len(filtered_ids)} notes selected")

        # Clear existing field widgets
        for i in reversed(range(self.fields_layout.count())):
            item = self.fields_layout.itemAt(i)
            if item is not None:
                widget = item.widget()
                if widget:
                    widget.deleteLater()

        self.field_checkboxes.clear()
        self.field_instructions.clear()

        # Get field names for this note type
        field_names = self.selected_notes.get_field_names(note_type_name)

        # Create checkbox and instruction input for each field
        for idx, field_name in enumerate(field_names):
            field_layout = QHBoxLayout()

            # Checkbox
            checkbox = QCheckBox(field_name)
            # Select first two fields by default
            if idx < 2:
                checkbox.setChecked(True)
            checkbox.stateChanged.connect(self._on_field_selection_changed)
            self.field_checkboxes[field_name] = checkbox
            field_layout.addWidget(checkbox)

            # Instruction input
            instruction_input = QLineEdit()
            instruction_input.setPlaceholderText("Optional instructions for this field...")
            instruction_input.setEnabled(idx < 2)  # Enable for checked fields
            self.field_instructions[field_name] = instruction_input
            field_layout.addWidget(instruction_input)

            self.fields_layout.addLayout(field_layout)

        # Enable transform button if we have notes
        self.transform_button.setEnabled(len(filtered_ids) > 0)

    def _on_field_selection_changed(self) -> None:
        """Handle field checkbox state changes."""
        # Enable/disable instruction inputs based on checkbox state
        for field_name, checkbox in self.field_checkboxes.items():
            instruction_input = self.field_instructions[field_name]
            instruction_input.setEnabled(checkbox.isChecked())

    def _on_transform_clicked(self) -> None:
        """Handle transform button click."""
        # Get selected fields
        selected_fields = {
            field_name
            for field_name, checkbox in self.field_checkboxes.items()
            if checkbox.isChecked()
        }

        if not selected_fields:
            from aqt.utils import showInfo
            showInfo("Please select at least one field to fill.")
            return

        # Get field instructions
        field_instructions = {
            field_name: instruction_input.text().strip()
            for field_name, instruction_input in self.field_instructions.items()
            if instruction_input.text().strip() and field_name in selected_fields
        }

        # Get filtered note IDs
        filtered_note_ids = self.selected_notes.filter_by_note_type(self.current_note_type)

        if not filtered_note_ids:
            from aqt.utils import showInfo
            showInfo("No notes to transform.")
            return

        # Create prompt builder
        from ..lib.prompt_builder import PromptBuilder
        prompt_builder = PromptBuilder(field_instructions)

        # Start transformation
        from ..lib.transform_operations import transform_notes_with_progress

        batch_size = self.settings_manager.get_batch_size()

        transform_notes_with_progress(
            parent=self,
            col=self.col,
            selected_notes=self.selected_notes,
            note_ids=filtered_note_ids,
            lm_client=self.lm_client,
            prompt_builder=prompt_builder,
            selected_fields=selected_fields,
            note_type_name=self.current_note_type,
            batch_size=batch_size,
        )

        # Close dialog
        self.accept()
