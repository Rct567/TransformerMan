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
    Qt,
    QMouseEvent,
    QObject,
    QEvent
)
from aqt.utils import showInfo, showWarning, askUserDialog

from .base_dialog import TransformerManBaseDialog
from .preview_table import PreviewTable

from ..lib.transform_operations import TransformNotesWithProgress
from ..lib.selected_notes import SelectedNotes
from ..lib.utilities import override
from ..lib.field_updates import FieldUpdates

import logging

if TYPE_CHECKING:
    from pathlib import Path
    from anki.collection import Collection
    from ..lib.lm_clients import LMClient
    from ..lib.addon_config import AddonConfig
    from anki.notes import NoteId
    from anki.cards import CardId
    from ..lib.transform_operations import TransformResults


class FieldWidget(QWidget):
    """Widget containing all UI elements for a single field."""

    def __init__(
        self,
        field_name: str,
        main_window: TransformerManMainWindow,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.field_name = field_name
        self.main_window = main_window
        self.is_overwritable = False

        # Create widgets
        self.context_checkbox = QCheckBox()
        self.context_checkbox.setToolTip("Allow read (include field content in the prompt)")
        self.context_checkbox.stateChanged.connect(self._on_context_changed)

        self.writable_checkbox = QCheckBox()
        self.writable_checkbox.setToolTip("Allow write (allow this field to be filled). Click with CTRL to make overwritable (red).")
        self.writable_checkbox.stateChanged.connect(self._on_writable_changed)

        # Install event filter to capture CTRL+click
        self.writable_checkbox.installEventFilter(self)

        self.field_label = QLabel(field_name)

        self.instruction_input = QLineEdit()
        self.instruction_input.setPlaceholderText("Optional instructions for this field...")
        self.instruction_input.textChanged.connect(self._on_instruction_changed)

        # Initial state
        self.instruction_input.setEnabled(False)

    @override
    def eventFilter(self, a0: QObject | None, a1: QEvent | None) -> bool:
        """Filter events for the writable checkbox to detect CTRL+click."""
        if a0 == self.writable_checkbox and a1 is not None and a1.type() == a1.Type.MouseButtonPress:
            if not isinstance(a1, QMouseEvent):
                return super().eventFilter(a0, a1)
            if a1.modifiers() & Qt.KeyboardModifier.ControlModifier:
                # CTRL+click: toggle overwritable state
                if self.writable_checkbox.isChecked():
                    # Currently checked: toggle between writable and overwritable
                    if self.is_overwritable:
                        # Currently overwritable (red) -> uncheck
                        self.set_overwritable(False)
                        self.writable_checkbox.setChecked(False)
                    else:
                        # Currently writable (normal) -> make overwritable (red)
                        self.set_overwritable(True)
                else:
                    # Currently unchecked -> check as overwritable (red) directly
                    self.set_overwritable(True)
                    self.writable_checkbox.setChecked(True)
                # Return True to indicate we've handled the event
                return True
        # Let the parent class handle other events
        return super().eventFilter(a0, a1)

    def _on_context_changed(self) -> None:
        """Handle context checkbox state change."""
        if not self.context_checkbox.isChecked():
            # If context unchecked, uncheck writable
            self.writable_checkbox.setChecked(False)
        self.instruction_input.setEnabled(self.context_checkbox.isChecked())
        self.main_window._on_field_selection_changed()  # type: ignore[reportPrivateUsage]

    def _on_writable_changed(self) -> None:
        """Handle writable checkbox state change."""
        if self.writable_checkbox.isChecked():
            # If writable checked, check context
            self.context_checkbox.setChecked(True)
        else:
            # If writable unchecked, clear overwritable state
            self.set_overwritable(False)
        self.main_window._on_field_selection_changed()  # type: ignore[reportPrivateUsage]

    def _on_instruction_changed(self) -> None:
        """Handle instruction input text change."""
        self.main_window._on_instruction_changed()  # type: ignore[reportPrivateUsage]

    def set_overwritable(self, overwritable: bool) -> None:
        """Set overwritable state and update visual appearance."""
        self.is_overwritable = overwritable
        if overwritable:
            self.field_label.setStyleSheet("color: red; font-weight: bold;")
            self.writable_checkbox.setToolTip("Overwritable (field will be filled even if already has content).")
        else:
            self.field_label.setStyleSheet("")
            self.writable_checkbox.setToolTip("Allow write (allow this field to be filled). Click with CTRL to make overwritable (red).")

    def is_context_selected(self) -> bool:
        """Return True if context checkbox is checked."""
        return self.context_checkbox.isChecked()

    def is_writable(self) -> bool:
        """Return True if writable checkbox is checked and not overwritable."""
        return self.writable_checkbox.isChecked() and not self.is_overwritable

    def is_overwritable_selected(self) -> bool:
        """Return True if field is in overwritable state."""
        return self.writable_checkbox.isChecked() and self.is_overwritable

    def get_instruction(self) -> str:
        """Get instruction text."""
        return self.instruction_input.text().strip()

    def set_instruction_enabled(self, enabled: bool) -> None:
        """Enable or disable instruction input."""
        self.instruction_input.setEnabled(enabled)

    def set_context_checked(self, checked: bool) -> None:
        """Set context checkbox state."""
        self.context_checkbox.setChecked(checked)




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
        card_ids: list[CardId] | None = None,
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
            card_ids: List of selected card IDs (optional). If provided, used for deck detection.
        """
        super().__init__(parent, is_dark_mode)
        self.is_dark_mode = is_dark_mode
        self.col = col
        self.lm_client = lm_client
        self.addon_config = addon_config
        self.logger = logging.getLogger(__name__)
        self.user_files_dir = user_files_dir

        self.selected_notes = SelectedNotes(col, note_ids, card_ids=card_ids)

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
        self.field_widgets: dict[str, FieldWidget] = {}

        # Preview state
        self.preview_results = FieldUpdates()  # note_id -> field_name -> new_value

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
        layout.addWidget(QLabel("Select fields:"))

        # Scrollable area for fields
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)

        self.fields_widget = QWidget()
        fields_container_layout = QVBoxLayout()
        fields_container_layout.addWidget(QLabel("<span style='color: rgba(128, 128, 128, 0.5);'>Read, Write & Optional instructions</span>"))
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
        """Get the currently selected field names."""
        return [
            field_name
            for field_name, widget in self.field_widgets.items()
            if widget.is_context_selected()
        ]

    def _get_writable_fields(self) -> list[str]:
        """Get the currently selected writable field names (excluding overwritable fields)."""
        return [
            field_name
            for field_name, widget in self.field_widgets.items()
            if widget.is_writable()
        ]

    def _get_overwritable_fields(self) -> list[str]:
        """Get the currently selected overwritable field names."""
        return [
            field_name
            for field_name, widget in self.field_widgets.items()
            if widget.is_overwritable_selected()
        ]

    def _get_fillable_fields(self) -> list[str]:
        """Get all fields that can be filled (writable or overwritable)."""
        return [
            field_name
            for field_name, widget in self.field_widgets.items()
            if widget.is_writable() or widget.is_overwritable_selected()
        ]

    def _has_fillable_fields(self) -> bool:
        """Return True if any fillable fields are selected."""
        return len(self._get_fillable_fields()) > 0

    def _has_notes_with_fillable_fields(self) -> bool:
        """Return True if there are notes that can be filled (empty writable fields or overwritable fields)."""
        writable_fields = self._get_writable_fields()
        overwritable_fields = self._get_overwritable_fields()
        if not writable_fields and not overwritable_fields:
            return False
        # Use the existing method that checks both conditions
        filtered = self.selected_notes.filter_by_writable_or_overwritable(
            writable_fields, overwritable_fields
        )
        return len(filtered) > 0

    def _get_current_field_instructions(self) -> dict[str, str]:
        """Get current field instructions for the selected fields."""
        selected_fields = self._get_selected_fields()
        return {
            field_name: widget.get_instruction()
            for field_name, widget in self.field_widgets.items()
            if widget.get_instruction() and field_name in selected_fields
        }

    def _update_state(
        self,
        *,
        clear_preview_results: bool = False,
        update_preview_table: bool = True,
    ) -> None:
        """
        Update the UI state based on current selections.

        Args:
            clear_preview_results: Whether to clear existing preview results.
            update_preview_table: Whether to update the preview table display.
        """
        if clear_preview_results:
            self.preview_results.clear()

        field_instructions = self._get_current_field_instructions()
        self.transformer.update_field_instructions(field_instructions)

        self._update_notes_count_label()

        if update_preview_table:
            self._update_preview_table()

        self.update_buttons_state()

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
        writable_fields = self._get_writable_fields()

        # Calculate notes with empty fields among writable fields
        if writable_fields:
            num_notes_empty_field = len(self.selected_notes.filter_by_empty_field(writable_fields))
        else:
            num_notes_empty_field = 0   # No writable fields selected

        # Calculate API calls needed using transformer method
        overwritable_fields = self._get_overwritable_fields()
        num_api_calls_needed = self.transformer.get_num_api_calls_needed(
            self.current_note_type, selected_fields, writable_fields, overwritable_fields, filtered_note_ids
        )
        api_text = "API call" if num_api_calls_needed == 1 else "API calls"

        # Note count description
        empty_text = "note" if num_notes_empty_field == 1 else "notes"
        field_text = "field" if num_notes_empty_field == 1 else "fields"
        appendix_text = f"{num_notes_empty_field} {empty_text} with empty writable {field_text}"

        note_text = "note" if total_count == 1 else "notes"

        # Update label with bold HTML
        label_text = (
            f"<b>{total_count} {note_text} selected, "
            f"{appendix_text} ({num_api_calls_needed} {self.lm_client.id} {api_text}).</b>"
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

        self.field_widgets.clear()

        # Get field names for this note type
        field_names = self.selected_notes.get_field_names(note_type_name)
        # Create FieldWidget for each field
        for row, field_name in enumerate(field_names):
            widget = FieldWidget(field_name, self)
            # Select first two fields by default
            if row < 2:
                widget.set_context_checked(True)
                widget.set_instruction_enabled(True)
            self.field_widgets[field_name] = widget
            # Add child widgets to grid columns
            self.fields_layout.addWidget(widget.context_checkbox, row, 0)
            self.fields_layout.addWidget(widget.writable_checkbox, row, 1)
            self.fields_layout.addWidget(widget.field_label, row, 2)
            self.fields_layout.addWidget(widget.instruction_input, row, 3)

        # Set column stretch so that instruction column expands
        self.fields_layout.setColumnStretch(3, 1)

        # Update state (clears preview results, updates transformer, notes count, preview table, and buttons)
        self._update_state(clear_preview_results=True)

    def _on_field_selection_changed(self) -> None:
        """Handle field checkbox state changes."""
        # Update state (clears preview results, updates transformer, notes count, preview table, and buttons)
        self._update_state(clear_preview_results=True)

    def _on_instruction_changed(self) -> None:
        """Handle instruction input text changes."""
        # Update state (clears preview results, updates transformer, notes count, preview table, and buttons)
        self._update_state(clear_preview_results=True)

    def _update_preview_table(self) -> None:
        """Update the preview table with data from selected notes."""
        # Get selected fields
        selected_fields = self._get_selected_fields()
        # Get filtered note IDs
        filtered_note_ids = self.selected_notes.filter_by_note_type(self.current_note_type)
        # Update the preview table
        self.preview_table.show_notes(filtered_note_ids, selected_fields)

    def update_buttons_state(self) -> None:
        """Update the enabled/disabled state of all buttons based on current state."""
        # Preview button conditions
        preview_enabled = False
        if self.current_note_type:
            filtered_note_ids = self.selected_notes.filter_by_note_type(self.current_note_type)

            # Use helper methods for cleaner logic
            has_fillable_fields = self._has_fillable_fields()
            has_notes_with_fillable_fields = self._has_notes_with_fillable_fields()

            preview_enabled = (
                len(filtered_note_ids) > 0
                and has_fillable_fields
                and len(self.preview_results) == 0
                and has_notes_with_fillable_fields
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
            showInfo("Please select at least one field to include.", parent=self)
            return

        if not self._has_fillable_fields():
            showInfo("Please select at least one field to write to.", parent=self)
            return

        if not self._has_notes_with_fillable_fields():
            showInfo("No notes with empty writable fields found and no overwritable fields selected.", parent=self)
            return

        # Get filtered note IDs
        filtered_note_ids = self.selected_notes.filter_by_note_type(self.current_note_type)

        if not filtered_note_ids:
            showInfo("No notes to transform.", parent=self)
            return

        # Calculate API calls needed using transformer method
        # Note: transformer should already have latest field instructions from _update_state calls
        writable_fields = self._get_writable_fields()
        overwritable_fields = self._get_overwritable_fields()
        api_calls_needed = self.transformer.get_num_api_calls_needed(
            self.current_note_type, selected_fields, writable_fields, overwritable_fields, filtered_note_ids
        )

        # Show warning if API calls > 10
        if api_calls_needed > 10:
            # Need to get empty count for warning message
            num_notes_empty_field = len(self.selected_notes.filter_by_empty_field(writable_fields)) if writable_fields else 0
            max_prompt_size = self.addon_config.get_max_prompt_size()

            warning_message = (
                f"This preview will require {api_calls_needed} API calls.\n\n"
                f"Notes with empty fields: {num_notes_empty_field}\n"
                f"Max prompt size: {max_prompt_size:,} characters\n\n"
                "Do you want to continue?"
            )

            if askUserDialog(warning_message, buttons=["Continue", "Cancel"], parent=self).run() != "Continue":
                return

        def on_preview_success(results: TransformResults, field_updates: FieldUpdates) -> None:
            """Handle successful preview."""

            # Check for error in results
            if results['error']:
                # Show error, ask user if they want to use results
                showWarning(f"An error occurred:\n\n{results['error']}", parent=self)
                disregard_result = True

                if results['num_notes_updated'] > 0 and field_updates:
                    disregard_result = askUserDialog("Preview results anyway?", buttons=["Yes", "No"], parent=self).run() == "No"

                if disregard_result:
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
            num_batches_requested = results['num_batches_requested']
            num_batches_processed = results['num_batches_processed']

            result_info_text = f"Preview complete:\n\n{num_updated} notes would be updated."

            if num_notes_failed > 0:
                result_info_text += f"\n{num_notes_failed} notes failed."
            if num_batches_requested > 1:
                if num_batches_requested != num_batches_processed:
                    result_info_text += f"\n{num_batches_processed} of {num_batches_requested} batches processed."
                else:
                    result_info_text += f"\n{num_batches_processed} batches processed."

            showInfo(result_info_text, parent=self)

        self.transformer.transform(
            note_ids=filtered_note_ids,
            selected_fields=selected_fields,
            writable_fields=writable_fields,
            overwritable_fields=overwritable_fields,
            note_type_name=self.current_note_type,
            on_success=on_preview_success,
        )

    def _on_apply_clicked(self) -> None:
        """Handle apply button click."""
        if not self.preview_results:
            showInfo("No preview results to apply. Please run Preview first.", parent=self)
            return

        # Check for overwritable fields that will cause data loss
        overwritable_fields = self._get_overwritable_fields()
        if overwritable_fields:
            # Determine which notes will have content overwritten
            notes_with_overwritten_content: dict[NoteId, list[str]] = {}
            overwritable_set = set(overwritable_fields)
            for note_id, field_updates in self.preview_results.items():
                note = self.selected_notes.get_note(note_id)
                overwritten_fields_for_note: list[str] = []
                for field_name in field_updates.keys():
                    if field_name in overwritable_set and field_name in note and note[field_name].strip():
                        overwritten_fields_for_note.append(field_name)
                if overwritten_fields_for_note:
                    notes_with_overwritten_content[note_id] = overwritten_fields_for_note

            if notes_with_overwritten_content:
                num_notes = len(notes_with_overwritten_content)
                # Collect unique fields that will be overwritten
                all_overwritten_fields = set()
                for fields in notes_with_overwritten_content.values():
                    all_overwritten_fields.update(fields)
                fields_str = ", ".join(f'"{field}"' for field in sorted(all_overwritten_fields))

                field_text = "field" if len(overwritable_fields) == 1 else "fields"
                note_text = "note" if num_notes == 1 else "notes"

                warning_message = (
                    f"Warning: You have selected {len(overwritable_fields)} overwritable {field_text}.\n\n"
                    f"{num_notes} {note_text} will have their content overwritten in these fields: {fields_str}.\n\n"
                    "Do you want to continue?"
                )
                if askUserDialog(warning_message, buttons=["Continue", "Cancel"], parent=self).run() != "Continue":
                    return

        # Apply field updates using operation (which will trigger Browser refresh)
        def on_success(results: dict[str, int]) -> None:
            """Handle successful application of field updates."""
            updated = results.get("updated", 0)
            failed = results.get("failed", 0)

            if updated > 0:
                showInfo(f"Successfully applied changes to {updated} notes.", parent=self)
                # Clear preview results and refresh UI state
                self.selected_notes.clear_cache()
                self._update_state(
                    clear_preview_results=True,
                    update_preview_table=True,
                )
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
        field_updates: FieldUpdates,
    ) -> None:
        """Update the preview table with preview results and green highlighting."""
        # Get selected fields
        selected_fields = self._get_selected_fields()
        # Get filtered note IDs
        filtered_note_ids = self.selected_notes.filter_by_note_type(self.current_note_type)
        # Update the preview table with field updates for highlighting
        self.preview_table.show_notes(filtered_note_ids, selected_fields, field_updates)
