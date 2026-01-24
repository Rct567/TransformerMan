"""
TransformerMan by Rick Zuidhoek. Licensed under the GNU GPL-3.0.
See <https://www.gnu.org/licenses/gpl-3.0.html> for details.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal
from collections.abc import Sequence
from pathlib import Path

from aqt.qt import (
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QTextEdit,
    QComboBox,
    QSpinBox,
    QPushButton,
    QWidget,
    QListWidget,
    QListWidgetItem,
    QApplication,
    Qt,
    QMessageBox,
    QCloseEvent,
)

from aqt.utils import showInfo, showWarning

from ...lib.utilities import JSON_TYPE, create_slug, override
from ..base_dialog import TransformerManBaseDialog
from .generated_notes_table import GeneratedNotesTable
from .generating_notes import GeneratingNotesManager, GenerationRequest
from ...lib.selected_notes import NoteModel
from ...lib.selected_notes import SelectedNotes
from ...lib.response_middleware import LogLastRequestResponseMiddleware, ResponseMiddleware
from ..stats_widget import StatsWidget, StatKeyValue, open_config_dialog
from ..ui_utilities import debounce, celebrate_milestone

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path
    from anki.collection import Collection
    from anki.notes import Note, NoteId
    from anki.cards import CardId
    from ...lib.lm_clients import LMClient
    from ...lib.addon_config import AddonConfig
    from ...lib.xml_parser import NewNote


class GenerateNotesDialog(TransformerManBaseDialog):
    """Main dialog for generating notes (TransformerMan > Generate notes)."""

    _is_locked_by_context: tuple[NoteModel, str] | Literal[False]

    def __init__(
        self,
        parent: QWidget,
        is_dark_mode: bool,
        col: Collection,
        lm_client: LMClient,
        addon_config: AddonConfig,
        user_files_dir: Path,
        note_ids: Sequence[NoteId],
        card_ids: Sequence[CardId] | None = None,
    ) -> None:
        super().__init__(parent, is_dark_mode)
        self.col = col
        self.lm_client = lm_client
        self.addon_config = addon_config
        self.example_notes = SelectedNotes(col, note_ids, card_ids=card_ids)

        # Setup middleware (for logging)
        self.middleware = ResponseMiddleware(LogLastRequestResponseMiddleware(self.addon_config, user_files_dir))

        self.notes_generator = GeneratingNotesManager(col, lm_client, self.middleware, self.addon_config)
        self._is_locked_by_context = False
        self._last_source_text_value = ""  # Track last loaded/saved text to avoid overwriting unsaved changes
        self._prompt_too_large = False

        self.setWindowTitle("TransformerMan: Generate notes")
        self.setMinimumWidth(800)
        self.setMinimumHeight(600)

        self._setup_ui()
        self._populate_dropdowns()
        self._set_defaults()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Selection section (Note type and Deck)
        selection_layout = QGridLayout()

        # Note type
        note_type_text = QLabel("Select note type:")
        note_type_text.setMinimumWidth(145)
        selection_layout.addWidget(note_type_text, 0, 0)
        self.note_type_combo = QComboBox()
        self.note_type_combo.currentTextChanged.connect(self._on_note_type_changed)
        selection_layout.addWidget(self.note_type_combo, 0, 1)

        # Deck
        deck_text = QLabel("Select deck:")
        deck_text.setMinimumWidth(145)
        selection_layout.addWidget(deck_text, 1, 0)
        self.deck_combo = QComboBox()
        self.deck_combo.currentTextChanged.connect(self._on_deck_changed)
        selection_layout.addWidget(self.deck_combo, 1, 1)

        selection_layout.setColumnStretch(1, 1)
        layout.addLayout(selection_layout)

        # Stats section
        stat_config = {
            "selected": StatKeyValue("Selected"),
            "api_client": StatKeyValue("Api client"),
            "client_model": StatKeyValue("Model"),
            "examples": StatKeyValue("Examples", title="Number of example notes used in the generated prompt."),
        }
        self.stats_widget = StatsWidget(self, self.is_dark_mode, stat_config)
        layout.addWidget(self.stats_widget)

        # Top Section: Source Text and Field Selection
        top_layout = QHBoxLayout()

        # Input Section
        input_layout = QVBoxLayout()
        input_layout.addWidget(QLabel("Source Text / Keywords:"))
        self.source_text_edit = QTextEdit()
        self.source_text_edit.setPlaceholderText("Enter text to generate notes from (optional)...")
        input_layout.addWidget(self.source_text_edit)
        self.source_text_edit.textChanged.connect(self._check_current_prompt_length)
        top_layout.addLayout(input_layout, 2)

        # Field Selection Section
        field_layout = QVBoxLayout()
        field_layout.addWidget(QLabel("Fields to use:"))
        self.field_list = QListWidget()
        self.field_list.setToolTip("Select fields to be used for generation and examples.")
        self.field_list.itemChanged.connect(self._on_field_selection_changed)
        field_layout.addWidget(self.field_list)
        top_layout.addLayout(field_layout, 1)

        layout.addLayout(top_layout)

        # Warning label for source text length
        self.source_text_warning_label = QLabel()
        self.source_text_warning_label.setStyleSheet("color: orange;")
        self.source_text_warning_label.setWordWrap(True)
        self.source_text_warning_label.setVisible(False)
        layout.addWidget(self.source_text_warning_label)

        # Settings Section
        settings_layout = QHBoxLayout()
        settings_layout.addStretch()

        settings_layout.addWidget(QLabel("Count:"))
        self.count_spin = QSpinBox()
        self.count_spin.setRange(1, 1000)
        self.count_spin.setValue(10)
        self.count_spin.setMinimumWidth(55)
        settings_layout.addWidget(self.count_spin)

        self.generate_btn = QPushButton("Generate notes")
        self.generate_btn.clicked.connect(self._on_generate_clicked)
        settings_layout.addWidget(self.generate_btn)

        layout.addLayout(settings_layout)

        # Preview Table
        layout.addWidget(QLabel("Generated Notes (Editable):"))
        self.table = GeneratedNotesTable(self)
        layout.addWidget(self.table)

        # Action Section
        action_layout = QHBoxLayout()
        action_layout.addStretch()
        self.create_btn = QPushButton("Create new notes")
        self.create_btn.clicked.connect(self._on_create_clicked)
        self.create_btn.setEnabled(False)
        action_layout.addWidget(self.create_btn)
        layout.addLayout(action_layout)

        # Connect table changes to update create button state
        self.table.itemChanged.connect(self._update_state)
        model = self.table.model()
        if model:
            model.rowsInserted.connect(self._update_state)
            model.rowsRemoved.connect(self._update_state)

    def _update_state(self) -> None:
        """Update the UI state based on current selections."""
        self._update_stats_widget()
        self._update_buttons_state()

        # Handle locking
        is_locked = bool(self._is_locked_by_context)
        self.note_type_combo.setEnabled(not is_locked)
        self.deck_combo.setEnabled(not is_locked)
        self.field_list.setEnabled(not is_locked)

        if not is_locked and self.table.rowCount() == 0:
            selected_fields = self._get_selected_fields()
            self.table.update_columns(selected_fields)

        assert self.table.rowCount() == 0 or is_locked, "Table should be empty if not locked by context."

    def _update_buttons_state(self) -> None:
        """Update the enabled/disabled state of all buttons based on current state."""
        self.create_btn.setEnabled(self.table.rowCount() > 0)
        self.generate_btn.setEnabled(not self._prompt_too_large)

    def _get_current_prompt_length(self) -> int | None:
        """Get the length of the prompt that would be generated with current settings, or None if cannot determine."""
        text = self.source_text_edit.toPlainText().strip()
        if not text:
            return None

        model = self._get_selected_note_type()
        if not model:
            return None

        deck_name = self.deck_combo.currentText()
        selected_fields = self._get_selected_fields()
        filtered_examples = self.example_notes.filter_by_note_type(model)

        # Build prompt and return length
        prompt = self.notes_generator.generator.prompt_builder.build_prompt(
            source_text=text,
            note_type=model,
            deck_name=deck_name,
            target_count=self.count_spin.value(),
            selected_fields=selected_fields,
            example_notes=filtered_examples,
            max_examples=self.addon_config.get_max_examples(),
        )
        return len(prompt)

    @debounce(300)
    def _check_current_prompt_length(self) -> None:
        prompt_length = self._get_current_prompt_length()
        self._prompt_too_large = False
        if prompt_length is not None:
            max_size = self.addon_config.get_max_prompt_size()
            if prompt_length > max_size:
                warning_text = f"Warning: Generated prompt ({prompt_length:,} chars) exceeds max prompt size ({max_size:,} chars)."
                self.source_text_warning_label.setText(warning_text)
                self._prompt_too_large = True

        self.source_text_warning_label.setVisible(self._prompt_too_large)
        self._update_state()

    def _on_deck_changed(self) -> None:
        """Handle deck selection change."""
        self._load_source_text()
        self._update_state()

    def _get_selected_note_type(self) -> NoteModel | None:
        """Get the currently selected note type model."""
        note_type_name = self.note_type_combo.currentText()
        if not note_type_name:
            return None
        model = NoteModel.by_name(self.col, note_type_name)
        return model

    def _get_source_text_config_key(self, include_deck: bool = True) -> str | None:
        """Get the config key for the source text."""
        model = self._get_selected_note_type()
        if not model:
            return None

        if include_deck:
            deck_name = self.deck_combo.currentText()
            if deck_name:
                root_deck = deck_name.split("::")[0]
                deck_slug = create_slug(root_deck)
                return f"generate_source_text_{deck_slug}_{model.id}"

        return f"generate_source_text_{model.id}"

    def _save_source_text(self) -> None:
        """Save source text to config."""
        config_key = self._get_source_text_config_key(include_deck=True)
        if config_key:
            source_text = self.source_text_edit.toPlainText().strip()
            self.addon_config.update_setting(config_key, source_text)
            self._last_source_text_value = source_text

    def _load_source_text(self) -> None:
        """Load source text from config."""
        model = self._get_selected_note_type()
        if not model:
            return

        current_text = self.source_text_edit.toPlainText().strip()

        # If the field has content that wasn't just loaded/saved, don't overwrite it
        if current_text and current_text != self._last_source_text_value:
            return

        # Try with deck first
        config_key = self._get_source_text_config_key(include_deck=True)
        source_text: JSON_TYPE = ""

        if config_key and config_key in self.addon_config:
            source_text = self.addon_config.get(config_key, "")
        else:
            # Fallback to without deck
            config_key_no_deck = self._get_source_text_config_key(include_deck=False)
            if config_key_no_deck and config_key_no_deck in self.addon_config:
                source_text = self.addon_config.get(config_key_no_deck, "")

        if isinstance(source_text, str) and source_text:
            self.source_text_edit.blockSignals(True)
            self.source_text_edit.setPlainText(source_text)
            self.source_text_edit.blockSignals(False)
            self._last_source_text_value = source_text

    def _get_selected_fields(self) -> list[str]:
        """Get the list of currently selected fields."""
        selected_fields = []
        for i in range(self.field_list.count()):
            item = self.field_list.item(i)
            if item and item.checkState() == Qt.CheckState.Checked:
                selected_fields.append(item.text())
        return selected_fields

    def _populate_dropdowns(self) -> None:
        # Note Types
        if self.example_notes:
            note_types = list(self.example_notes.get_note_type_counts().keys())
        else:
            note_types = sorted([m["name"] for m in self.col.models.all()])
        self.note_type_combo.addItems(note_types)

        # Decks (only those who share the same root with any card of selected notes)
        used_decks = self.example_notes.get_most_common_decks(2000, all_cards=True)
        used_deck_roots = set(deck.split("::")[0] for deck in used_decks)
        decks = [
            deck.name for deck
            in self.col.decks.all_names_and_ids(include_filtered=False)
            if not used_deck_roots or deck.name.split("::")[0] in used_deck_roots
        ]
        self.deck_combo.addItems(decks)

        self._update_state()

    def _set_defaults(self) -> None:
        if self.example_notes:
            # Set default note type to most common
            counts = self.example_notes.get_note_type_counts()
            if counts:
                most_common_type = next(iter(counts.keys()))
                self.note_type_combo.setCurrentText(most_common_type)

            # Set default deck to most common
            most_common_deck = self.example_notes.get_most_common_deck()
            if most_common_deck:
                most_common_deck_root = most_common_deck.split("::")[0]
                self.deck_combo.setCurrentText(most_common_deck_root)

    def _on_field_selection_changed(self, _item: QListWidgetItem) -> None:
        """Update table columns when field selection changes (if not locked)."""
        self._update_state()

    def _update_stats_widget(self) -> None:
        """Update the stats widget."""
        model = self._get_selected_note_type()

        total_count = 0
        if model and self.example_notes:
            total_count = len(self.example_notes.filter_by_note_type(model))

        note_text = "note" if total_count == 1 else "notes"

        def on_close() -> None:
            self._check_current_prompt_length()

        def on_client_updated(new_lm_client: LMClient) -> None:
            self.lm_client = new_lm_client
            self.notes_generator.lm_client = new_lm_client
            self.notes_generator.generator.lm_client = new_lm_client
            self._update_state()

        def open_dialog() -> None:
            open_config_dialog(self, self.addon_config, on_client_updated, on_close)

        show_model = bool(self.lm_client.get_model())

        self.stats_widget.update_stats({
            "selected": StatKeyValue("Selected", f"{total_count} {note_text}"),
            "api_client": StatKeyValue("Api client", self.lm_client.name, click_callback=open_dialog),
            "client_model": StatKeyValue("Model", self.lm_client.get_model(), visible=show_model, click_callback=open_dialog),
            "examples": StatKeyValue("Examples", str(self.addon_config.get_max_examples()), click_callback=open_dialog),
        })

    def _on_note_type_changed(self) -> None:
        # Update table columns and field list when note type changes
        model = self._get_selected_note_type()
        if model:
            fields = model.get_fields()

            # Update field list
            self.field_list.blockSignals(True)
            self.field_list.clear()
            for i, field in enumerate(fields):
                item = QListWidgetItem(field)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                # Default to first 2 fields selected
                state = Qt.CheckState.Checked if i < 2 else Qt.CheckState.Unchecked
                item.setCheckState(state)
                self.field_list.addItem(item)
            self.field_list.blockSignals(False)

            self.table.set_notes([])

        self._load_source_text()
        self._update_state()

    def _on_generate_clicked(self) -> None:

        source_text = self.source_text_edit.toPlainText().strip()

        # Get selected fields
        selected_fields = []
        for i in range(self.field_list.count()):
            item = self.field_list.item(i)
            if item and item.checkState() == Qt.CheckState.Checked:
                selected_fields.append(item.text())

        if not selected_fields:
            showInfo("Please select at least one field.", parent=self)
            return

        # Save source text to config
        self._save_source_text()

        deck_name = self.deck_combo.currentText()
        target_count = self.count_spin.value()

        if self._is_locked_by_context:
            model, deck_name = self._is_locked_by_context
        else:
            selected_model = NoteModel.by_name(self.col, self.note_type_combo.currentText())
            if not selected_model:
                return
            else:
                model = selected_model
            deck_name = self.deck_combo.currentText()

        # Filter example notes by selected note type
        filtered_examples = None
        if self.example_notes:
            filtered_examples = self.example_notes.filter_by_note_type(model)

        # If no source text, we need to make sure we have some examples or can find some
        if not source_text:
            examples = self.notes_generator.generator.prompt_builder.get_example_notes(
                note_type=model,
                example_notes=filtered_examples,
                field_names=selected_fields,
                max_examples=self.addon_config.get_max_examples(),
                deck_name=deck_name,
            )

            if not examples:
                showInfo(
                    "Please enter some source text or ensure there are existing notes of this type to use as examples.",
                    parent=self,
                )
                return

        self.generate_btn.setEnabled(False)
        self.generate_btn.setText("Generating...")

        def on_success(notes: Sequence[NewNote], duplicates: dict[int, list[str]], ignored_count: int) -> None:
            self.generate_btn.setEnabled(True)
            self.generate_btn.setText("Generate notes")
            if notes or ignored_count > 0:
                if notes:
                    if not self._is_locked_by_context:  # Lock note type, deck and field selection after first successful generation
                        self._is_locked_by_context = (model, deck_name)

                    start_row = self.table.rowCount()
                    self.table.append_notes(notes)
                    self.table.highlight_duplicates(duplicates, start_row=start_row)

                if ignored_count > 0:
                    note_text = "note" if ignored_count == 1 else "notes"
                    showInfo(f"Ignored {ignored_count} fully duplicate {note_text}.", parent=self)
            else:
                showInfo("No notes were generated.", parent=self)

            self._update_state()

        def on_failure(e: Exception) -> None:
            self.generate_btn.setEnabled(True)
            self.generate_btn.setText("Generate notes")
            if str(e) == "Prompt preview canceled by user":
                self._update_state()
                return
            showWarning(f"Generation failed: {e!s}", parent=self)
            self._update_state()

        # Check for Shift key modifier
        prompt_interceptor = bool(QApplication.keyboardModifiers() & Qt.KeyboardModifier.ShiftModifier)

        request = GenerationRequest(
            source_text=source_text,
            note_type=model,
            deck_name=deck_name,
            target_count=target_count,
            selected_fields=selected_fields,
            example_notes=filtered_examples,
        )

        self.notes_generator.generate(
            parent=self,
            request=request,
            on_success=on_success,
            on_failure=on_failure,
            prompt_interceptor=prompt_interceptor,
        )

    def _on_create_clicked(self) -> None:

        # Disable button during creation
        self.create_btn.setEnabled(False)
        self.create_btn.repaint()

        notes_data = self.table.get_all_notes()
        if not notes_data:
            showInfo("No notes to create.", parent=self)
            return

        deck_name = self.deck_combo.currentText()

        model = self._get_selected_note_type()
        if not model:
            return

        deck_id = self.col.decks.id(deck_name)
        if deck_id is None:
            showWarning(f"Deck '{deck_name}' not found.", parent=self)
            return

        def on_success(notes: list[Note]) -> None:
            count = len(notes)
            showInfo(f"Successfully added {count} notes to deck '{deck_name}'.", parent=self)

            # Milestone tracking
            self.addon_config.increase_counter("notes_generated_count", count)
            old_count, new_count = self.addon_config.increase_counter("times_notes_generated")
            milestone = self.addon_config.get_milestone_reached(old_count, new_count)

            if milestone:
                celebrate_milestone(
                    f"You have generated notes {new_count:,} times! 🚀",
                    addon_config=self.addon_config,
                    parent=self,
                )

            # Clear table and update UI state
            self.table.set_notes([])

            # Unlock UI to allow further generation or changes
            self._is_locked_by_context = False
            self._update_state()

        def on_failure(e: Exception) -> None:
            showWarning(f"Failed to add notes: {e!s}", parent=self)

        self.notes_generator.create_notes(
            parent=self,
            notes_data=notes_data,
            note_type=model,
            deck_id=deck_id,
            on_success=on_success,
            on_failure=on_failure,
        )

    @override
    def closeEvent(self, a0: QCloseEvent | None) -> None:
        """Handle dialog close event with warning if there are unsaved generated notes."""
        if a0 is not None and self.table.rowCount() > 0:
            reply = QMessageBox.question(
                self,
                "Unsaved Generated Notes",
                "You have generated notes that will be lost if you close this dialog.\n\nDo you want to close anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.No:
                a0.ignore()
                return
        super().closeEvent(a0)
