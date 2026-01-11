"""
TransformerMan by Rick Zuidhoek. Licensed under the GNU GPL-3.0.
See <https://www.gnu.org/licenses/gpl-3.0.html> for details.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal
from collections.abc import Sequence
from collections.abc import MutableMapping
from collections.abc import Iterable
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
    Qt,
)
from aqt import mw
from aqt.utils import showInfo, showWarning
from aqt.operations import QueryOp

from ..base_dialog import TransformerManBaseDialog
from .generated_notes_table import GeneratedNotesTable
from ..progress_dialog import ProgressDialog
from ...lib.note_generator import NoteGenerator
from ...lib.selected_notes import NoteModel
from ...lib.selected_notes import SelectedNotes
from ...lib.response_middleware import LogLastRequestResponseMiddleware, ResponseMiddleware
from ..stats_widget import StatsWidget, StatKeyValue, open_config_dialog

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence, MutableMapping
    from pathlib import Path
    from anki.collection import Collection
    from anki.notes import Note, NoteId
    from anki.cards import CardId
    from ...lib.lm_clients import LMClient
    from ...lib.addon_config import AddonConfig
    from ...lib.http_utils import LmProgressData
    from ...lib.xml_parser import NewNote


class GenerateNotesDialog(TransformerManBaseDialog):
    """Dialog for generating and adding new Anki notes."""

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

        self.generator = NoteGenerator(col, lm_client, self.middleware)
        self._is_locked_by_context = False

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
        selection_layout.addWidget(self.deck_combo, 1, 1)

        selection_layout.setColumnStretch(1, 1)
        layout.addLayout(selection_layout)

        # Stats section
        stat_config = {
            "selected": StatKeyValue("Selected"),
            "api_client": StatKeyValue("Api client"),
            "client_model": StatKeyValue("Model"),
        }
        self.stats_widget = StatsWidget(self, self.is_dark_mode, stat_config)
        layout.addWidget(self.stats_widget)

        # Top Section: Source Text and Field Selection
        top_layout = QHBoxLayout()

        # Input Section
        input_layout = QVBoxLayout()
        input_layout.addWidget(QLabel("Source Text / Keywords:"))
        self.source_text_edit = QTextEdit()
        self.source_text_edit.setPlaceholderText("Enter text to generate notes from...")
        input_layout.addWidget(self.source_text_edit)
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
        self.table.itemChanged.connect(self._update_create_button_state)
        model = self.table.model()
        if model:
            model.rowsInserted.connect(self._update_create_button_state)
            model.rowsRemoved.connect(self._update_create_button_state)

    def _update_create_button_state(self) -> None:
        self.create_btn.setEnabled(self.table.rowCount() > 0)

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

        self._update_stats_widget()

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
        if self._is_locked_by_context:
            return

        selected_fields = []
        for i in range(self.field_list.count()):
            item = self.field_list.item(i)
            if item and item.checkState() == Qt.CheckState.Checked:
                selected_fields.append(item.text())

        self.table.update_columns(selected_fields)

    def _update_stats_widget(self) -> None:
        """Update the stats widget."""
        note_type_name = self.note_type_combo.currentText()
        model = NoteModel.by_name(self.col, note_type_name)

        total_count = 0
        if model and self.example_notes:
            total_count = len(self.example_notes.filter_by_note_type(model))

        note_text = "note" if total_count == 1 else "notes"

        def on_client_updated(new_lm_client: LMClient) -> None:
            self.lm_client = new_lm_client
            self.generator.lm_client = new_lm_client
            self._update_stats_widget()

        def open_dialog() -> None:
            open_config_dialog(self, self.addon_config, on_client_updated)

        show_model = bool(self.lm_client.get_model())
        self.stats_widget.update_stats({
            "selected": StatKeyValue("Selected", f"{total_count} {note_text}"),
            "api_client": StatKeyValue("Api client", self.lm_client.name, click_callback=open_dialog),
            "client_model": StatKeyValue("Model", self.lm_client.get_model(), visible=show_model, click_callback=open_dialog),
        })

    def _on_note_type_changed(self) -> None:
        # Update table columns and field list when note type changes
        note_type_name = self.note_type_combo.currentText()
        model = NoteModel.by_name(self.col, note_type_name)
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

            # Update table columns based on default selection (first 2 fields)
            default_fields = fields[:2] if len(fields) >= 2 else fields
            self.table.update_columns(default_fields)
            self.table.set_notes([])

        self._update_stats_widget()

    def _on_generate_clicked(self) -> None:
        source_text = self.source_text_edit.toPlainText().strip()
        if not source_text:
            showInfo("Please enter some source text.", parent=self)
            return

        # Get selected fields
        selected_fields = []
        for i in range(self.field_list.count()):
            item = self.field_list.item(i)
            if item and item.checkState() == Qt.CheckState.Checked:
                selected_fields.append(item.text())

        if not selected_fields:
            showInfo("Please select at least one field.", parent=self)
            return

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

        self.generate_btn.setEnabled(False)
        self.generate_btn.setText("Generating...")

        # Create progress dialog
        progress = ProgressDialog(1, self)
        progress.show()

        def generate(col: Collection) -> tuple[Sequence[NewNote], dict[int, list[str]], int]:
            # Filter example notes by selected note type
            filtered_examples = None
            if self.example_notes:
                filtered_examples = self.example_notes.filter_by_note_type(model)

            def progress_callback(data: LmProgressData) -> None:
                def update_ui() -> None:
                    progress.update_progress(0, 1, data)

                if mw and mw.taskman:
                    mw.taskman.run_on_main(update_ui)

            def should_cancel() -> bool:
                return progress.is_cancel_requested()

            raw_notes = self.generator.generate_notes(
                source_text=source_text,
                note_type=model,
                deck_name=deck_name,
                target_count=target_count,
                selected_fields=selected_fields,
                example_notes=filtered_examples,
                progress_callback=progress_callback,
                should_cancel=should_cancel,
            )

            def set_progress_to_filter_duplicates() -> None:
                progress.setLabelText("Checking for duplicate content...")
                progress.setValue(1)

            if mw and mw.taskman:
                mw.taskman.run_on_main(set_progress_to_filter_duplicates)

            model_fields = model.get_fields()
            all_duplicates = find_duplicates(col, raw_notes, deck_name, model_fields)
            model_fields_set = set(model_fields)
            filtered_notes: list[NewNote] = []
            duplicates: dict[int, list[str]] = {}
            ignored_count = 0

            for i, note in enumerate(raw_notes):
                duplicate_fields = all_duplicates.get(i, [])
                # Only count keys that are actual fields of the note type
                actual_note_fields = [k for k in note if k in model_fields_set]

                # If all actual fields in the note are duplicates, ignore it
                if duplicate_fields and len(duplicate_fields) == len(actual_note_fields):
                    ignored_count += 1
                else:
                    if duplicate_fields:
                        duplicates[len(filtered_notes)] = duplicate_fields
                    filtered_notes.append(note)

            return filtered_notes, duplicates, ignored_count

        def on_success(result: tuple[Sequence[NewNote], dict[int, list[str]], int]) -> None:
            notes, duplicates, ignored_count = result
            progress.cleanup()
            self.generate_btn.setEnabled(True)
            self.generate_btn.setText("Generate notes")
            if notes or ignored_count > 0:
                # Lock note type, deck and field selection after first successful generation
                if not self._is_locked_by_context:
                    self._is_locked_by_context = (model, deck_name)
                    self.note_type_combo.setEnabled(False)
                    self.deck_combo.setEnabled(False)
                    self.field_list.setEnabled(False)

                if notes:
                    start_row = self.table.rowCount()
                    self.table.append_notes(notes)
                    self.table.highlight_duplicates(duplicates, start_row=start_row)
                    self._update_create_button_state()

                if ignored_count > 0:
                    note_text = "note" if ignored_count == 1 else "notes"
                    showInfo(f"Ignored {ignored_count} fully duplicate {note_text}.", parent=self)
            else:
                showInfo("No notes were generated.", parent=self)

        def on_failure(e: Exception) -> None:
            progress.cleanup()
            self.generate_btn.setEnabled(True)
            self.generate_btn.setText("Generate notes")
            showWarning(f"Generation failed: {e!s}", parent=self)

        QueryOp(
            parent=self,
            op=generate,
            success=on_success,
        ).failure(on_failure).run_in_background()

    def _on_create_clicked(self) -> None:
        notes_data = self.table.get_all_notes()
        if not notes_data:
            showInfo("No notes to create.", parent=self)
            return

        note_type_name = self.note_type_combo.currentText()
        deck_name = self.deck_combo.currentText()

        model = self.col.models.by_name(note_type_name)
        if not model:
            return

        deck_id = self.col.decks.id(deck_name)
        if deck_id is None:
            showWarning(f"Deck '{deck_name}' not found.", parent=self)
            return

        def add_notes(col: Collection) -> int:
            count = 0
            for data in notes_data:
                note = col.new_note(model)
                for field, value in data.items():
                    if field in note:
                        note[field] = value
                col.add_note(note, deck_id)
                count += 1
            return count

        def on_success(count: int) -> None:
            showInfo(f"Successfully added {count} notes to deck '{deck_name}'.", parent=self)
            self.accept()

        def on_failure(e: Exception) -> None:
            showWarning(f"Failed to add notes: {e!s}", parent=self)

        QueryOp(
            parent=self,
            op=add_notes,
            success=on_success,
        ).failure(on_failure).run_in_background()


def find_duplicates(
    col: Collection, notes: Sequence[MutableMapping[str, str]], deck_name: str, field_names: Sequence[str] | None = None
) -> dict[int, list[str]]:
    """
    Find duplicates for a list of notes within a specific deck.
    Returns a dict mapping relative row index to a list of duplicate field names.

    Args:
        col: Anki collection
        notes: List of note dictionaries to check for duplicates
        deck_name: Name of the deck to search within (can include :: for subdecks)
        field_names: Optional list of actual field names for the note type to filter keys
    """
    duplicates: dict[int, list[str]] = {}
    batch_size = 10

    # Process notes in batches
    for batch_start in range(0, len(notes), batch_size):
        batch_end = min(batch_start + batch_size, len(notes))
        batch_notes = notes[batch_start:batch_end]

        # Get all potential duplicate note IDs for this batch
        batch_note_ids = get_duplicate_note_ids(col, batch_notes, deck_name, field_names)

        if not batch_note_ids:
            continue

        # Load all notes at once
        existing_notes = {nid: col.get_note(nid) for nid in batch_note_ids}

        # Check each note in the batch against the existing notes
        for i, note in enumerate(batch_notes):
            note_index = batch_start + i
            duplicate_fields = _find_duplicate_fields_in_notes(note, existing_notes.values())

            if duplicate_fields:
                duplicates[note_index] = duplicate_fields

    return duplicates


def _find_duplicate_fields_in_notes(note: MutableMapping[str, str], existing_notes: Iterable[Note]) -> list[str]:
    """Helper function to find which fields in a note have duplicates in existing notes.

    Args:
        note: Note dictionary to check
        existing_notes: Iterable of existing Anki notes to check against

    Returns:
        List of field names that have duplicate values
    """
    duplicate_fields = []

    for existing_note in existing_notes:
        for field, value in note.items():
            if field in existing_note and existing_note[field] == value:
                if field not in duplicate_fields:
                    duplicate_fields.append(field)

    return duplicate_fields


def get_duplicate_note_ids(
    col: Collection, notes: Sequence[MutableMapping[str, str]], deck_name: str, field_names: Sequence[str] | None = None
) -> Sequence[NoteId]:
    """Get all potential duplicate note IDs for a list of notes.

    Args:
        col: Anki collection
        notes: A list of note dictionaries to check
        deck_name: Name of the deck to search within
        field_names: Optional list of actual field names for the note type to filter keys

    Returns:
        List of note IDs that potentially contain duplicates
    """
    if not notes:
        return []

    # Construct query: "deck:DeckName" AND (
    #   ("Field1:Val1_1" OR "Field2:Val2_1" ...) OR
    #   ("Field1:Val1_2" OR "Field2:Val2_2" ...) OR
    #   ...
    # )
    note_queries = []
    for note in notes:
        field_parts = []
        for field, value in note.items():
            # If field_names provided, skip keys that aren't actual fields
            if field_names is not None and field not in field_names:
                continue

            if not value.strip():
                continue
            # Escape double quotes in value
            escaped_value = value.replace('"', '\\"')
            field_parts.append(f'"{field}:{escaped_value}"')

        if field_parts:
            note_queries.append(f"({' OR '.join(field_parts)})")

    if not note_queries:
        return []

    # Escape deck name and construct final query
    root_deck_name_escaped = deck_name.split("::", maxsplit=1)[0].replace('"', '\\"')
    combined_query = " OR ".join(note_queries)
    query = f'"deck:{root_deck_name_escaped}" AND ({combined_query})'

    return col.find_notes(query)
