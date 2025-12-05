"""
TransformerMan by Rick Zuidhoek. Licensed under the GNU GPL-3.0.
See <https://www.gnu.org/licenses/gpl-3.0.html> for details.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from aqt.qt import (
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QComboBox,
    QCheckBox,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QWidget,
)
from aqt.utils import showInfo


from .base_dialog import TransformerManBaseDialog
from .preview_table import PreviewTable

from ..lib.transform_operations import transform_notes_with_progress, apply_field_updates
from ..lib.prompt_builder import PromptBuilder
from ..lib.selected_notes import SelectedNotes


if TYPE_CHECKING:
    from pathlib import Path
    from anki.collection import Collection
    from ..lib.lm_clients import LMClient
    from ..lib.addon_config import AddonConfig
    from anki.notes import NoteId


class TransformerManMainWindow(TransformerManBaseDialog):
    """Main window for TransformerMan plugin."""

    def __init__(
        self,
        parent: QWidget,
        is_dark_mode: bool,
        col: Collection,
        note_ids: list[NoteId],
        lm_client: LMClient,
        addon_config: AddonConfig,
        user_files_dir: Path,
    ) -> None:
        """
        Initialize the main window.

        Args:
            parent: Parent widget.
            is_dark_mode: Whether the application is in dark mode.
            col: Anki collection.
            note_ids: List of selected note IDs.
            lm_client: LM client instance.
            addon_config: Addon configuration instance.
            user_files_dir: Directory for user files.
        """
        super().__init__(parent)
        self.is_dark_mode = is_dark_mode
        self.col = col
        self.note_ids = note_ids
        self.lm_client = lm_client
        self.addon_config = addon_config
        self.user_files_dir = user_files_dir

        self.selected_notes = SelectedNotes(col, note_ids)

        # State
        self.note_type_counts: dict[str, int] = {}
        self.current_note_type: str = ""
        self.field_checkboxes: dict[str, QCheckBox] = {}
        self.field_instructions: dict[str, QLineEdit] = {}

        # Preview state
        self.preview_results: dict[NoteId, dict[str, str]] = {}  # note_id -> field_name -> new_value
        self.previewed_note_ids: list[NoteId] = []

        self._setup_ui()
        self._load_note_types()

    def _setup_ui(self) -> None:
        """Setup the UI components."""
        self.setWindowTitle("TransformerMan")
        self.setMinimumWidth(500)
        self.setMinimumHeight(400)

        # Create main layout for the dialog
        layout = QVBoxLayout(self)

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

        self.fields_widget = QWidget()
        fields_container_layout = QVBoxLayout()
        self.fields_widget.setLayout(fields_container_layout)

        self.fields_layout = QGridLayout()
        fields_container_layout.addLayout(self.fields_layout)
        fields_container_layout.addStretch()

        scroll_area.setWidget(self.fields_widget)

        layout.addWidget(scroll_area)

        # Preview Table
        layout.addWidget(QLabel("Selected notes:"))
        self.preview_table = PreviewTable(parent=self, is_dark_mode=self.is_dark_mode)
        self.preview_table.set_selected_notes(self.selected_notes)
        layout.addWidget(self.preview_table, 1)

        # Button layout
        button_layout = QHBoxLayout()

        # Preview button
        self.preview_button = QPushButton("Preview")
        self.preview_button.clicked.connect(self._on_preview_clicked)
        self.preview_button.setEnabled(False)
        button_layout.addWidget(self.preview_button)

        # Apply button
        self.apply_button = QPushButton("Apply")
        self.apply_button.clicked.connect(self._on_apply_clicked)
        self.apply_button.setEnabled(False)
        button_layout.addWidget(self.apply_button)

        button_layout.addStretch()
        layout.addLayout(button_layout)

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
        while self.fields_layout.count():
            item = self.fields_layout.takeAt(0)
            if item is not None:
                widget = item.widget()
                if widget:
                    widget.deleteLater()

        self.field_checkboxes.clear()
        self.field_instructions.clear()

        # Get field names for this note type
        field_names = self.selected_notes.get_field_names(note_type_name)

        # Create checkbox and instruction input for each field
        for row, field_name in enumerate(field_names):
            # Checkbox
            checkbox = QCheckBox(field_name)
            # Select first two fields by default
            if row < 2:
                checkbox.setChecked(True)
            checkbox.stateChanged.connect(self._on_field_selection_changed)
            self.field_checkboxes[field_name] = checkbox
            self.fields_layout.addWidget(checkbox, row, 0)

            # Instruction input
            instruction_input = QLineEdit()
            instruction_input.setPlaceholderText("Optional instructions for this field...")
            instruction_input.setEnabled(row < 2)  # Enable for checked fields
            self.field_instructions[field_name] = instruction_input
            self.fields_layout.addWidget(instruction_input, row, 1)

        # Set column stretch so that instruction column expands
        self.fields_layout.setColumnStretch(1, 1)

        # Enable preview button if we have notes
        self.preview_button.setEnabled(len(filtered_ids) > 0)

        self._update_preview_table()

    def _on_field_selection_changed(self) -> None:
        """Handle field checkbox state changes."""
        # Enable/disable instruction inputs based on checkbox state
        for field_name, checkbox in self.field_checkboxes.items():
            instruction_input = self.field_instructions[field_name]
            instruction_input.setEnabled(checkbox.isChecked())

        self._update_preview_table()

    def _update_preview_table(self) -> None:
        """Update the preview table with data from selected notes."""
        # Get selected fields
        selected_fields = [
            field_name
            for field_name, checkbox in self.field_checkboxes.items()
            if checkbox.isChecked()
        ]

        # Get filtered note IDs
        filtered_ids = self.selected_notes.filter_by_note_type(self.current_note_type)

        # Update the preview table
        self.preview_table.set_note_fields_update(filtered_ids, selected_fields)



    def _on_preview_clicked(self) -> None:
        """Handle preview button click."""
        # Get selected fields
        selected_fields = {
            field_name
            for field_name, checkbox in self.field_checkboxes.items()
            if checkbox.isChecked()
        }

        if not selected_fields:
            showInfo("Please select at least one field to fill.", parent=self)
            return

        if not self.selected_notes.has_note_with_empty_field(selected_fields):
            showInfo("No notes with empty fields found.", parent=self)
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
            showInfo("No notes to transform.", parent=self)
            return

        # Create prompt builder
        prompt_builder = PromptBuilder(field_instructions)

        # Start preview transformation
        batch_size = self.addon_config.get("batch_size", 10)
        if not isinstance(batch_size, int):
            batch_size = 10

        def on_preview_success(results: dict[str, int], field_updates: dict[NoteId, dict[str, str]]) -> None:
            """Handle successful preview."""
            # Store preview results
            self.preview_results = field_updates
            self.previewed_note_ids = list(field_updates.keys())

            # Enable apply button
            self.apply_button.setEnabled(len(field_updates) > 0)

            # Update preview table with green highlighting
            self._update_preview_table_with_results(results, field_updates)

            # Show preview summary
            updated = results.get("updated", 0)
            failed = results.get("failed", 0)
            showInfo(f"Preview complete:\n\n{updated} notes would be updated\n{failed} notes failed", parent=self)

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
            addon_config=self.addon_config,
            user_files_dir=self.user_files_dir,
            on_success=on_preview_success,
        )

    def _on_apply_clicked(self) -> None:
        """Handle apply button click."""
        if not self.preview_results:
            showInfo("No preview results to apply. Please run Preview first.", parent=self)
            return

        # Apply field updates
        results = apply_field_updates(self.col, self.preview_results)

        # Show results
        updated = results.get("updated", 0)
        failed = results.get("failed", 0)

        if updated > 0:
            showInfo(f"Successfully applied changes to {updated} notes.", parent=self)
            # Clear preview results and disable apply button
            self.preview_results.clear()
            self.previewed_note_ids.clear()
            self.apply_button.setEnabled(False)
            # Refresh preview table to show updated values
            self._update_preview_table()
        else:
            showInfo(f"No notes were updated. {failed} notes failed.", parent=self)

    def _update_preview_table_with_results(
        self,
        results: dict[str, int],
        field_updates: dict[NoteId, dict[str, str]],
    ) -> None:
        """Update the preview table with preview results and green highlighting."""
        # Get selected fields
        selected_fields = [
            field_name
            for field_name, checkbox in self.field_checkboxes.items()
            if checkbox.isChecked()
        ]

        # Get filtered note IDs
        filtered_ids = self.selected_notes.filter_by_note_type(self.current_note_type)

        # Update the preview table with field updates for highlighting
        self.preview_table.set_note_fields_update(filtered_ids, selected_fields, field_updates)
