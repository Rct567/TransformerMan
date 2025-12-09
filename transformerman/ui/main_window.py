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
from aqt.utils import showInfo, showWarning, askUserDialog

from .base_dialog import TransformerManBaseDialog
from .preview_table import PreviewTable

from ..lib.transform_operations import TransformNotesWithProgress
from ..lib.prompt_builder import PromptBuilder
from ..lib.selected_notes import SelectedNotes

import logging

if TYPE_CHECKING:
    from pathlib import Path
    from anki.collection import Collection
    from ..lib.lm_clients import LMClient
    from ..lib.addon_config import AddonConfig
    from anki.notes import NoteId
    from ..lib.transform_operations import TransformResults


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
        super().__init__(parent, is_dark_mode)
        self.is_dark_mode = is_dark_mode
        self.col = col
        self.note_ids = note_ids
        self.lm_client = lm_client
        self.addon_config = addon_config
        self.logger = logging.getLogger(__name__)
        self.user_files_dir = user_files_dir

        self.selected_notes = SelectedNotes(col, note_ids)

        # Initialize transformer
        self.transformer = TransformNotesWithProgress(
            parent=self,
            col=col,
            selected_notes=self.selected_notes,
            lm_client=lm_client,
            addon_config=addon_config,
            user_files_dir=user_files_dir,
        )

        # State
        self.note_type_counts: dict[str, int] = {}
        self.current_note_type: str = ""
        self.field_checkboxes: dict[str, QCheckBox] = {}
        self.field_instructions: dict[str, QLineEdit] = {}

        # Preview state
        self.preview_results: dict[NoteId, dict[str, str]] = {}  # note_id -> field_name -> new_value

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
        note_type_text = QLabel("Select note type:")
        note_type_text.setMinimumWidth(145)
        note_type_layout.addWidget(note_type_text)
        # Add spacing between label and combo box
        note_type_layout.addSpacing(10)
        self.note_type_combo = QComboBox()
        self.note_type_combo.currentTextChanged.connect(self._on_note_type_changed)
        # Add combo box with stretch factor so it expands horizontally
        note_type_layout.addWidget(self.note_type_combo, 1)
        layout.addLayout(note_type_layout)

        # Notes count label
        self.notes_count_label = QLabel("<b>0 notes selected, 0 notes with empty fields (0 API calls)</b>")
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
        self.preview_table = PreviewTable(self, self.is_dark_mode)
        self.preview_table.set_selected_notes(self.selected_notes)
        layout.addWidget(self.preview_table, 1)

        # Button layout
        button_layout = QHBoxLayout()

        # Preview button
        self.preview_button = QPushButton("Preview")
        self.preview_button.setToolTip("Preview transformation")
        self.preview_button.clicked.connect(self._on_preview_clicked)
        button_layout.addWidget(self.preview_button)

        # Apply button
        self.apply_button = QPushButton("Apply")
        self.apply_button.setToolTip("Apply transformation")
        self.apply_button.clicked.connect(self._on_apply_clicked)
        button_layout.addWidget(self.apply_button)

        # Set initial button states
        self.update_buttons_state()

        button_layout.addStretch()
        layout.addLayout(button_layout)

    def _get_selected_fields(self) -> list[str]:
        """
        Get the currently selected field names.

        Returns:
            List of selected field names.
        """
        return [
            field_name
            for field_name, checkbox in self.field_checkboxes.items()
            if checkbox.isChecked()
        ]

    def _update_notes_count_label(self) -> None:
        """Update the notes count label with bold text and empty field count."""
        if not self.current_note_type:
            # No note type selected yet
            self.notes_count_label.setText("<b>0 notes selected, 0 notes with empty fields (0 API calls)</b>")
            return

        # Get filtered note IDs for current note type
        filtered_note_ids = self.selected_notes.filter_by_note_type(self.current_note_type)
        total_count = len(filtered_note_ids)

        # Get selected fields
        selected_fields = self._get_selected_fields()
        # Calculate notes with empty fields among selected fields
        if selected_fields:
            num_notes_empty_field = len(self.selected_notes.filter_by_empty_field(selected_fields))
        else:
            num_notes_empty_field = 0  # No fields selected

        # Calculate API calls needed using transformer method
        api_calls_needed = self.transformer.get_num_api_calls_needed(
            self.current_note_type, selected_fields, filtered_note_ids
        )
        api_text = "API call" if api_calls_needed == 1 else "API calls"

        # Format with proper pluralization
        note_text = "note" if total_count == 1 else "notes"
        empty_text = "note" if num_notes_empty_field == 1 else "notes"
        field_text = "field" if num_notes_empty_field == 1 else "fields"

        # Update label with bold HTML
        label_text = (
            f"<b>{total_count} {note_text} selected, "
            f"{num_notes_empty_field} {empty_text} with empty {field_text} ({api_calls_needed} {api_text})</b>"
        )
        self.notes_count_label.setText(label_text)

    def _load_note_types(self) -> None:
        """Load note types from selected notes."""
        self.note_type_counts = self.selected_notes.get_note_type_counts()

        if not self.note_type_counts:
            self.notes_count_label.setText("<b>No valid notes selected</b>")
            return

        # Block signals during population to avoid triggering _on_note_type_changed prematurely
        self.note_type_combo.blockSignals(True)

        # Populate combo box (already sorted by count)
        for note_type_name in self.note_type_counts.keys():
            self.note_type_combo.addItem(note_type_name)

        # Select the first (most common) note type
        if self.note_type_combo.count() > 0:
            self.note_type_combo.setCurrentIndex(0)

        # Re-enable signals and manually trigger the change handler
        self.note_type_combo.blockSignals(False)

        # Manually trigger note type changed for the first item
        if self.note_type_combo.count() > 0:
            self._on_note_type_changed(self.note_type_combo.currentText())

    def _on_note_type_changed(self, note_type_name: str) -> None:
        """Handle note type selection change."""
        if not note_type_name:
            return
        self.current_note_type = note_type_name

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

        # Clear preview results since they're no longer valid for the new note type
        self.preview_results.clear()

        # Update notes count label with new counts
        self._update_notes_count_label()

        self._update_preview_table()

        # Update button states
        self.update_buttons_state()

    def _on_field_selection_changed(self) -> None:
        """Handle field checkbox state changes."""
        # Enable/disable instruction inputs based on checkbox state
        for field_name, checkbox in self.field_checkboxes.items():
            instruction_input = self.field_instructions[field_name]
            instruction_input.setEnabled(checkbox.isChecked())

        # Clear preview results since they're no longer valid with new field selection
        self.preview_results.clear()

        # Update notes count label since empty field count may have changed
        self._update_notes_count_label()
        self._update_preview_table()

        # Update button states
        self.update_buttons_state()

    def _update_preview_table(self) -> None:
        """Update the preview table with data from selected notes."""
        # Get selected fields
        selected_fields = self._get_selected_fields()
        # Get filtered note IDs
        filtered_note_ids = self.selected_notes.filter_by_note_type(self.current_note_type)
        # Update the preview table
        self.preview_table.set_note_fields_update(filtered_note_ids, selected_fields)

    def update_buttons_state(self) -> None:
        """Update the enabled/disabled state of all buttons based on current state."""
        # Preview button conditions
        preview_enabled = False
        if self.current_note_type:
            filtered_note_ids = self.selected_notes.filter_by_note_type(self.current_note_type)
            selected_fields = self._get_selected_fields()
            # Enable preview if we have notes AND at least one field selected
            # AND no preview results exist (would generate same results)
            # AND there are notes with empty fields to fill
            preview_enabled = (
                len(filtered_note_ids) > 0
                and len(selected_fields) > 0
                and len(self.preview_results) == 0
                and self.selected_notes.has_note_with_empty_field(selected_fields)
            )

        # Apply button conditions
        apply_enabled = len(self.preview_results) > 0

        # Update buttons
        self.preview_button.setEnabled(preview_enabled)
        self.apply_button.setEnabled(apply_enabled)

    def _on_preview_clicked(self) -> None:
        """Handle preview button click."""
        # Get selected fields
        selected_fields = self._get_selected_fields()

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

        # Calculate API calls needed using transformer method
        api_calls_needed = self.transformer.get_num_api_calls_needed(
            self.current_note_type, selected_fields, filtered_note_ids
        )

        # Show warning if API calls > 10
        if api_calls_needed > 10:
            # Need to get empty count for warning message
            num_notes_empty_field = len(self.selected_notes.filter_by_empty_field(selected_fields))
            max_prompt_size = self.addon_config.get_max_prompt_size()

            warning_message = (
                f"This preview will require {api_calls_needed} API calls.\n\n"
                f"Notes with empty fields: {num_notes_empty_field}\n"
                f"Max prompt size: {max_prompt_size:,} characters\n\n"
                "Do you want to continue?"
            )

            if askUserDialog(warning_message, buttons=["Continue", "Cancel"], parent=self).run() != "Continue":
                return

        # Create prompt builder
        prompt_builder = PromptBuilder(field_instructions)

        def on_preview_success(results: TransformResults, field_updates: dict[NoteId, dict[str, str]]) -> None:
            """Handle successful preview."""

            # Check for error in results
            if results['error']:
                # Show error with warning
                showWarning(f"Error during preview:\n\n{results['error']}\n\nNo notes would be updated.", parent=self)
                # Clear any partial results
                self.preview_results.clear()
                self.update_buttons_state()
                return

            # Store preview results
            self.preview_results = field_updates

            # Update button states
            self.update_buttons_state()

            # Update preview table with green highlighting
            self._update_preview_table_with_results(results, field_updates)

            # Show summary of results used for preview
            num_updated = results['num_notes_updated']
            num_notes_failed = results['num_notes_failed']
            num_batches_processed = results['num_batches_processed']

            result_info_text = f"Preview complete:\n\n{num_updated} notes would be updated."

            if num_notes_failed > 0:
                result_info_text += f"\n{num_notes_failed} notes failed."
            if num_batches_processed > 1:
                result_info_text += f"\n{num_batches_processed} batches processed."

            showInfo(result_info_text, parent=self)

        self.transformer.transform(
            note_ids=filtered_note_ids,
            prompt_builder=prompt_builder,
            selected_fields=selected_fields,
            note_type_name=self.current_note_type,
            on_success=on_preview_success,
        )

    def _on_apply_clicked(self) -> None:
        """Handle apply button click."""
        if not self.preview_results:
            showInfo("No preview results to apply. Please run Preview first.", parent=self)
            return

        # Apply field updates using operation (which will trigger Browser refresh)
        def on_success(results: dict[str, int]) -> None:
            """Handle successful application of field updates."""
            updated = results.get("updated", 0)
            failed = results.get("failed", 0)

            if updated > 0:
                showInfo(f"Successfully applied changes to {updated} notes.", parent=self)
                # Clear preview results
                self.preview_results.clear()
                # Refresh preview table to show updated values
                self.selected_notes.clear_cache()
                self._update_preview_table()
                # Update notes count label since empty field count has changed
                self._update_notes_count_label()
                # Update button states
                self.update_buttons_state()
            else:
                showInfo(f"No notes were updated. {failed} notes failed.", parent=self)

        def on_failure(exception: Exception) -> None:
            """Handle failure of field updates operation."""
            self.logger.error(f"Error applying field updates: {exception!r}")
            showInfo(f"Error applying changes: {exception!s}", parent=self)

        self.transformer.apply_field_updates(
            field_updates=self.preview_results,
            on_success=on_success,
            on_failure=on_failure,
        )

    def _update_preview_table_with_results(
        self,
        results: TransformResults,
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
        filtered_note_ids = self.selected_notes.filter_by_note_type(self.current_note_type)

        # Update the preview table with field updates for highlighting
        self.preview_table.set_note_fields_update(filtered_note_ids, selected_fields, field_updates)
