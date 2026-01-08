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
    QPushButton,
    QScrollArea,
    QWidget,
    QApplication,
    Qt,
)
from aqt.utils import showInfo, showWarning, askUserDialog

from .base_dialog import TransformerManBaseDialog
from .preview_table import PreviewTable
from .field_widgets import FieldWidget, FieldWidgets, FieldSelectionChangedEvent, FieldInstructionChangedEvent
from .stats_widget import StatsWidget, StatKeyValue
from .settings_dialog import SettingsDialog
from .prompt_preview_dialog import PromptPreviewDialog

from ..ui.transform_notes import TransformNotesWithProgress
from ..lib.response_middleware import LogLastRequestResponseMiddleware, CacheResponseMiddleware, ResponseMiddleware
from ..lib.selected_notes import SelectedNotes, NoteModel

import logging

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path
    from anki.collection import Collection
    from anki.notes import NoteId
    from anki.cards import CardId
    from ..lib.lm_clients import LMClient
    from ..lib.addon_config import AddonConfig
    from ..lib.field_updates import FieldUpdates
    from ..lib.transform_operations import TransformResults

try:
    from ..version import TRANSFORMERMAN_VERSION
    tm_version = TRANSFORMERMAN_VERSION
except ImportError:
    tm_version = ""


class TransformerManMainWindow(TransformerManBaseDialog):
    """Main window for TransformerMan plugin."""

    preview_results: FieldUpdates | None

    def __init__(
        self,
        parent: QWidget,
        is_dark_mode: bool,
        col: Collection,
        note_ids: Sequence[NoteId],
        lm_client: LMClient,
        addon_config: AddonConfig,
        user_files_dir: Path,
        card_ids: Sequence[CardId] | None = None,
    ) -> None:
        """
        Initialize the main window.

        Args:
            parent: Parent widget.
            is_dark_mode: Whether the application is in dark mode.
            col: Anki collection.
            note_ids: Sequence of selected note IDs.
            lm_client: LM client instance.
            addon_config: Addon configuration instance.
            user_files_dir: Directory for user files.
            card_ids: Sequence of selected card IDs (optional). If provided, used for deck detection.
        """
        super().__init__(parent, is_dark_mode)
        self.is_dark_mode = is_dark_mode
        self.col = col
        self.lm_client = lm_client
        self.addon_config = addon_config
        self.logger = logging.getLogger(__name__)

        # Setup transform middleware
        self.middleware = ResponseMiddleware(
            LogLastRequestResponseMiddleware(self.addon_config, user_files_dir),
            CacheResponseMiddleware(self.addon_config, user_files_dir),
        )

        self.selected_notes = SelectedNotes(col, note_ids, card_ids=card_ids)
        self.field_widgets = FieldWidgets()
        self._setup_event_listeners()

        # Initialize transformer
        self.transformer = TransformNotesWithProgress(
            parent=self,
            col=col,
            selected_notes=self.selected_notes,
            lm_client=self.lm_client,
            addon_config=self.addon_config,
            middleware=self.middleware,
        )

        # State
        self.note_type_counts: dict[str, int] = {}
        self.current_note_model: NoteModel | None = None

        # Preview state
        self.preview_results = None  # note_id -> field_name -> new_value

        self._setup_ui()
        self._load_note_types()

    def _setup_event_listeners(self) -> None:
        """Setup event listeners for the event manager."""
        self.field_widgets.event_manager.subscribe(
            FieldSelectionChangedEvent,
            lambda _: self._update_state(clear_preview_results=True),
        )
        self.field_widgets.event_manager.subscribe(
            FieldInstructionChangedEvent,
            lambda _: self._update_state(clear_preview_results=True),
        )

    def _setup_ui(self) -> None:
        """Setup the UI components."""

        if tm_version != "":
            self.setWindowTitle("TransformerMan v"+tm_version)
        else:
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

        # Stats section
        stat_config = {
            "selected": StatKeyValue("Selected"),
            "empty_fields": StatKeyValue("Empty writable fields"),
            "overwrite_stats": StatKeyValue("Overwritable fields"),
            "api_client": StatKeyValue("Api client"),
            "client_model": StatKeyValue("Model"),
            "api_calls": StatKeyValue("Api calls"),
        }
        self.stats_widget = StatsWidget(self, self.is_dark_mode, stat_config)
        layout.addWidget(self.stats_widget)

        # Fields section
        layout.addWidget(QLabel("Select fields:"))

        # Scrollable area for fields
        self.scroll_area_of_fields = QScrollArea()
        self.scroll_area_of_fields.setWidgetResizable(True)

        self.fields_widget = QWidget()
        fields_container_layout = QVBoxLayout()
        fields_container_layout.addWidget(QLabel(
            "<span style='color: rgba(128, 128, 128, 0.5);'>Read, Write & Optional instructions</span>"
        ))
        self.fields_widget.setLayout(fields_container_layout)

        self.fields_layout = QGridLayout()
        fields_container_layout.addLayout(self.fields_layout)
        fields_container_layout.addStretch()

        self.scroll_area_of_fields.setWidget(self.fields_widget)

        layout.addWidget(self.scroll_area_of_fields)

        # Preview Table
        layout.addWidget(QLabel("Selected notes:"))
        self.preview_table = PreviewTable(self, self.is_dark_mode, self.selected_notes.get_notes)
        layout.addWidget(self.preview_table, 1)

        # Button layout
        button_layout = QHBoxLayout()
        button_layout.setContentsMargins(0, 6, 0, 2)

        # Preview button
        self.preview_button = QPushButton("Preview")
        self.preview_button.setToolTip("Preview transformation")
        self.preview_button.clicked.connect(self._on_preview_clicked)
        button_layout.addWidget(self.preview_button)

        # Discard button
        self.discard_button = QPushButton("Discard")
        self.discard_button.setToolTip("Discard transformation results")
        self.discard_button.clicked.connect(self._on_discard_clicked)
        button_layout.addWidget(self.discard_button)

        # Apply button
        self.apply_button = QPushButton("Apply")
        self.apply_button.setToolTip("Apply transformation")
        self.apply_button.clicked.connect(self._on_apply_clicked)
        button_layout.addWidget(self.apply_button)

        # Set initial button states
        self.update_buttons_state()

        button_layout.addStretch()
        layout.addLayout(button_layout)

    def _has_notes_with_fillable_fields(self) -> bool:
        """Return True if there are notes that can be filled (empty writable fields or overwritable fields)."""
        field_selection = self.field_widgets.get_field_selection()
        if not field_selection.writable and not field_selection.overwritable:
            return False
        # Use the existing method that checks both conditions
        filtered = self.selected_notes.filter_by_writable_or_overwritable(field_selection.writable, field_selection.overwritable)
        return len(filtered) > 0

    def _update_state(
        self,
        *,
        clear_preview_results: bool = False,
        update_preview_table: bool = True,
        reload_notes: bool = False,
    ) -> None:
        """
        Update the UI state based on current selections.

        Args:
            clear_preview_results: Whether to clear existing preview results.
            update_preview_table: Whether to update the preview table display.
            reload_notes: Whether to reload the notes from Anki (avoiding cached results).
        """
        if clear_preview_results:
            self.preview_results = None

        field_instructions = self.field_widgets.get_current_field_instructions()
        self.transformer.update_field_instructions(field_instructions)

        self._update_stats_widget()

        if update_preview_table:
            self._update_preview_table(reload_notes)
        elif reload_notes:
            raise ValueError("Cannot reload notes without updating preview table")

        self.update_buttons_state()

    def _update_stats_widget(self) -> None:
        """Update the stats widget."""
        overwritable_fields: Sequence[str]
        if not self.current_note_model:
            total_count = 0
            num_notes_empty_field = 0
            num_api_calls_needed = 0
            overwritable_fields = []
        else:
            selected_notes_from_note = self.selected_notes.filter_by_note_type(self.current_note_model)
            total_count = len(selected_notes_from_note)
            field_selection = self.field_widgets.get_field_selection()
            num_notes_empty_field = (
                len(self.selected_notes.filter_by_empty_field(field_selection.writable)) if field_selection.writable else 0
            )

            num_api_calls_needed = self.transformer.get_num_api_calls_needed(selected_notes_from_note, field_selection)
            overwritable_fields = field_selection.overwritable

        note_text = "note" if total_count == 1 else "notes"
        empty_text = "note" if num_notes_empty_field == 1 else "notes"

        def open_config_dialog() -> None:
            """Open the addon configuration dialog."""
            SettingsDialog(parent=self, addon_config=self.addon_config).exec()

            self.addon_config.reload()
            new_lm_client, error = self.addon_config.get_client()
            if error:
                showWarning(f"{error}.\n\nPlease check your settings.", title="Configuration Error", parent=self)
                self.close()
                return
            if new_lm_client:
                self.lm_client = new_lm_client
                self.transformer.lm_client = new_lm_client
                self._update_state(clear_preview_results=True)

        show_model = bool(self.lm_client.get_model())
        self.stats_widget.update_stats({
            "selected": StatKeyValue("Selected", f"{total_count} {note_text}"),
            "empty_fields": StatKeyValue("Empty writable fields", f"{num_notes_empty_field} {empty_text}"),
            "overwrite_stats": StatKeyValue("Overwritable fields", f"{total_count} {note_text}", len(overwritable_fields) > 0),
            "api_client": StatKeyValue("Api client", self.lm_client.name, click_callback=open_config_dialog),
            "client_model": StatKeyValue("Model", self.lm_client.get_model(), visible=show_model, click_callback=open_config_dialog),
            "api_calls": StatKeyValue("Api calls", str(num_api_calls_needed))
        })

    def _load_note_types(self) -> None:
        """Load note types (from selected notes)."""
        self.note_type_counts = self.selected_notes.get_note_type_counts()

        if not self.note_type_counts:
            self._update_stats_widget()
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

        # Clear existing field widgets
        while self.fields_layout.count():
            item = self.fields_layout.takeAt(0)
            if item is not None:
                widget = item.widget()
                if widget:
                    widget.deleteLater()

        self.field_widgets.clear()

        # Get note type model
        model = NoteModel.by_name(self.col, note_type_name)
        assert model is not None
        self.current_note_model = model

        # Create FieldWidget for each field
        for row_index, field_name in enumerate(self.current_note_model.get_fields()):
            widget = FieldWidget(field_name, self.current_note_model.id, self.addon_config, self.field_widgets.event_manager)
            # Select first two fields by default
            if row_index < 2:
                widget.set_context_checked(True)
                widget.set_instruction_enabled(True)
            self.field_widgets.add(field_name, widget)
            # Add child widgets to grid columns
            self.fields_layout.addWidget(widget.read_checkbox, row_index, 0)
            self.fields_layout.addWidget(widget.writable_checkbox, row_index, 1)
            self.fields_layout.addWidget(widget.field_label, row_index, 2)
            self.fields_layout.addWidget(widget.instruction_input, row_index, 3)

        # Set column stretch so that instruction column expands
        self.fields_layout.setColumnStretch(3, 1)

        # Adjust scroll area height based on content
        QApplication.processEvents()
        content_height = self.fields_widget.sizeHint().height()
        min_height = min(content_height + 10, 250)
        max_height = (self.height() // 2) - 60

        if min_height > max_height:
            min_height = max_height

        self.scroll_area_of_fields.setMinimumHeight(min_height)
        self.scroll_area_of_fields.setMaximumHeight(max_height)

        # Update state (clears preview results, updates transformer, notes count, preview table, and buttons)
        self._update_state(clear_preview_results=True)

    def _update_preview_table(self, reload_notes: bool = False) -> None:
        """Update the preview table with data from selected notes."""
        if not self.current_note_model:
            return
        # Clear note cache if requested
        if reload_notes:
            self.selected_notes.clear_cache(clear_notes_cache=True, clear_deck_cache=False)
        # Get selected fields
        selected_fields = self.field_widgets.get_field_selection().selected
        # Get filtered note IDs
        filtered_notes = self.selected_notes.filter_by_note_type(self.current_note_model)
        # Update the preview table
        self.preview_table.show_notes(filtered_notes, selected_fields)

    def update_buttons_state(self) -> None:
        """Update the enabled/disabled state of all buttons based on current state."""
        # Preview button conditions
        preview_enabled = False
        if self.current_note_model:
            filtered_note_ids = self.selected_notes.filter_by_note_type(self.current_note_model)

            # Use helper methods for cleaner logic
            has_fillable_fields = self.field_widgets.has_fillable_fields()
            has_notes_with_fillable_fields = self._has_notes_with_fillable_fields()

            preview_enabled = (
                len(filtered_note_ids) > 0
                and has_fillable_fields
                and self.preview_results is None
                and has_notes_with_fillable_fields
            )

        apply_enabled = self.preview_results is not None and len(self.preview_results) > 0 and not self.preview_results.is_applied
        discard_enabled = apply_enabled

        # Update buttons
        self.preview_button.setEnabled(preview_enabled)
        self.apply_button.setEnabled(apply_enabled)
        self.discard_button.setEnabled(discard_enabled)

        # Update button styles based on enabled state and dark mode
        if self.is_dark_mode:
            apply_style = "background-color: #2e7d32;" if apply_enabled else ""
            discard_style = "background-color: #893f3f;" if discard_enabled else ""
        else:
            apply_style = "background-color: #81c784; border-color:#419245" if apply_enabled else ""
            discard_style = "background-color: #e8b1b1; border-color:#ac5e5e" if discard_enabled else ""

        self.apply_button.setStyleSheet(apply_style)
        self.discard_button.setStyleSheet(discard_style)

    def _on_preview_clicked(self) -> None:
        """Handle preview button click."""
        # Get field selection
        field_selection = self.field_widgets.get_field_selection()

        if not field_selection.selected:
            showInfo("Please select at least one field to include.", parent=self)
            return

        if not self.field_widgets.has_fillable_fields():
            showInfo("Please select at least one field to write to.", parent=self)
            return

        if not self._has_notes_with_fillable_fields():
            showInfo("No notes with empty writable fields found and no overwritable fields selected.", parent=self)
            return

        # Get filtered note IDs
        if not self.current_note_model:
            return
        filtered_note_ids = self.selected_notes.filter_by_note_type(self.current_note_model)

        if not filtered_note_ids:
            showInfo("No notes to transform.", parent=self)
            return

        # disable buttons during preview
        self.preview_button.setEnabled(False)
        self.preview_button.repaint()

        # Calculate API calls needed using transformer method
        # Note: transformer should already have latest field instructions from _update_state calls
        # selected_notes_from_note = self.selected_notes.new_selected_notes(filtered_note_ids).with_note_type(self.current_note_model)
        selected_notes_from_note = self.selected_notes.filter_by_note_type(self.current_note_model)

        transform_args = (selected_notes_from_note, field_selection)
        api_calls_needed = self.transformer.get_num_api_calls_needed(*transform_args)

        if api_calls_needed == 0 and not self.transformer.is_cached(selected_notes_from_note, field_selection):
            showWarning("No API calls possible with on the current selection and configuration (check prompt size limit).", parent=self)
            self.update_buttons_state()
            return

        # Show warning if API calls > 10
        if api_calls_needed > 10:
            # Need to get empty count for warning message
            num_notes_empty_field = (
                len(self.selected_notes.filter_by_empty_field(field_selection.writable)) if field_selection.writable else 0
            )
            max_prompt_size = self.addon_config.get_max_prompt_size()

            warning_message = (
                f"This preview will require {api_calls_needed} API calls.\n\n"
                f"Notes with empty fields: {num_notes_empty_field}\n"
                f"Max prompt size: {max_prompt_size:,} characters\n\n"
                "Do you want to continue?"
            )

            if askUserDialog(warning_message, buttons=["Continue", "Cancel"], parent=self).run() != "Continue":
                self._update_state()
                return

        def on_transform_success(results: TransformResults, field_updates: FieldUpdates) -> None:
            """Handle successful transformation (set preview)."""

            # Check for error in results
            if results.error:
                # Show error, ask user if they want to use results
                showWarning(f"An error occurred:\n\n{results.error}", parent=self)
                disregard_result = True

                if results.num_notes_updated > 0 and field_updates:
                    disregard_result = askUserDialog("Preview results anyway?", buttons=["Yes", "No"], parent=self).run() == "No"

                if disregard_result:
                    self.preview_results = None
                    self.update_buttons_state()
                    return

            if results.is_canceled and len(field_updates) == 0:
                showInfo("Preview canceled by user.", parent=self)
                self.preview_results = None
                self.update_buttons_state()
                return

            # Store preview results
            self.preview_results = field_updates

            # Update button states
            self.update_buttons_state()

            # Update preview table with green highlighting
            self._update_preview_table_with_results(results, field_updates)

            # Check for no field updates (results might be from cache)
            if field_updates.is_applied:
                showInfo("Preview complete, but field updates are already applied.", parent=self)
                return
            if len(field_updates) == 0:
                showInfo("Preview complete, but no field updates found.", parent=self)
                return

            # Show summary of results used for preview
            num_updated = results.num_notes_updated
            num_notes_failed = results.num_notes_failed
            num_batches_requested = results.num_batches_requested
            num_batches_processed = results.num_batches_processed

            result_info_text: list[str] = []

            if results.is_canceled:
                result_info_text.append("Transformation was canceled by user.")
            else:
                result_info_text.append(f"Transformation complete:\n\n{num_updated} notes would be updated.")

            if num_notes_failed > 0:
                result_info_text.append(f"{num_notes_failed} notes failed.")
            if num_batches_requested > 1:
                if num_batches_requested != num_batches_processed:
                    result_info_text.append(f"{num_batches_processed} of {num_batches_requested} batches processed.")
                else:
                    result_info_text.append(f"{num_batches_processed} batches processed.")

            showInfo("\n".join(result_info_text), parent=self)

        # Check for Shift key modifier
        prompt_interceptor = None
        if QApplication.keyboardModifiers() & Qt.KeyboardModifier.ShiftModifier:

            def interceptor(template: str) -> str:
                dialog = PromptPreviewDialog(self, template)
                if dialog.exec():
                    return dialog.get_template() or ""
                # If canceled, we raise an exception to stop the process
                raise Exception("Prompt preview canceled by user")

            prompt_interceptor = interceptor

        try:
            self.transformer.transform(
                selected_notes=selected_notes_from_note,
                field_selection=field_selection,
                on_success=on_transform_success,
                prompt_interceptor=prompt_interceptor,
            )
        except Exception as e:
            if str(e) == "Prompt preview canceled by user":
                self.update_buttons_state()
                return
            raise e

    def _on_apply_clicked(self) -> None:
        """Handle apply button click."""
        if not self.preview_results:
            showInfo("No preview results to apply. Please run Preview first.", parent=self)
            return

        # Check for overwritable fields that will cause data loss
        if self.preview_results.has_overwritable_fields():
            notes_with_overwritten_content = self.preview_results.get_notes_with_overwritten_content(self.selected_notes.get_note)

            if notes_with_overwritten_content:
                num_notes = len(notes_with_overwritten_content)
                # Collect unique fields that will be overwritten
                all_overwritten_fields = set()
                for fields in notes_with_overwritten_content.values():
                    all_overwritten_fields.update(fields)
                fields_str = ", ".join(f'"{field}"' for field in sorted(all_overwritten_fields))

                overwritable_fields = self.preview_results.get_overwritable_fields()
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
            else:
                showInfo(f"No notes were updated. {failed} notes failed.", parent=self)

            # Clear preview results and refresh UI state
            self._update_state(
                clear_preview_results=True,
                update_preview_table=True,
                reload_notes=True,
            )

        def on_failure(exception: Exception) -> None:
            """Handle failure of field updates operation."""
            self.logger.error(f"Error applying field updates: {exception!r}")
            showInfo(f"Error applying changes: {exception!s}", parent=self)

        self.transformer.apply_field_updates(
            field_updates=self.preview_results,
            on_success=on_success,
            on_failure=on_failure,
        )

    def _on_discard_clicked(self) -> None:
        """Handle discard button click."""
        # Clear preview results and refresh UI state
        self._update_state(
            clear_preview_results=True,
            update_preview_table=True,
        )

    def _update_preview_table_with_results(
        self,
        results: TransformResults,
        field_updates: FieldUpdates,
    ) -> None:
        """Update the preview table with preview results and green highlighting."""
        if not self.current_note_model:
            return
        # Get selected fields
        selected_fields = self.field_widgets.get_field_selection().selected
        # Get filtered note IDs
        filtered_note_ids = self.selected_notes.filter_by_note_type(self.current_note_model)
        # Update the preview table with field updates for highlighting
        self.preview_table.show_notes(filtered_note_ids, selected_fields, field_updates)
