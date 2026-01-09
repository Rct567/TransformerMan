"""
TransformerMan by Rick Zuidhoek. Licensed under the GNU GPL-3.0.
See <https://www.gnu.org/licenses/gpl-3.0.html> for details.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

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
    from collections.abc import Sequence
    from pathlib import Path
    from anki.collection import Collection
    from anki.notes import NoteId
    from anki.cards import CardId
    from ...lib.lm_clients import LMClient
    from ...lib.addon_config import AddonConfig
    from ...lib.http_utils import LmProgressData


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
        self.is_dark_mode = is_dark_mode
        self.col = col
        self.lm_client = lm_client
        self.addon_config = addon_config
        self.example_notes = SelectedNotes(col, note_ids, card_ids=card_ids)

        # Setup middleware (for logging)
        self.middleware = ResponseMiddleware(
             LogLastRequestResponseMiddleware(self.addon_config, user_files_dir)
        )

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
        self.count_spin.setRange(1, 50)
        self.count_spin.setValue(5)
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
        decks = [deck for deck in self.col.decks.all_names() if not used_deck_roots or deck.split("::")[0] in used_deck_roots]
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

        self.table.set_notes([], selected_fields)

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
            self.table.set_notes([], default_fields)

        self._update_stats_widget()

    def _on_generate_clicked(self) -> None:
        source_text = self.source_text_edit.toPlainText().strip()
        if not source_text:
            showInfo("Please enter some source text.")
            return

        # Get selected fields
        selected_fields = []
        for i in range(self.field_list.count()):
            item = self.field_list.item(i)
            if item and item.checkState() == Qt.CheckState.Checked:
                selected_fields.append(item.text())

        if not selected_fields:
            showInfo("Please select at least one field.")
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

        def generate(col: Collection) -> list[dict[str, str]]:
            # Filter example notes by selected note type
            filtered_examples = None
            if self.example_notes:
                filtered_examples = self.example_notes.filter_by_note_type(model)

            def progress_callback(data: LmProgressData) -> None:
                def update_ui() -> None:
                    progress.update_progress(0, 1, data)

                mw.taskman.run_on_main(update_ui)

            def should_cancel() -> bool:
                return progress.is_cancel_requested()

            return self.generator.generate_notes(
                source_text=source_text,
                note_type=model,
                deck_name=deck_name,
                target_count=target_count,
                selected_fields=selected_fields,
                example_notes=filtered_examples,
                progress_callback=progress_callback,
                should_cancel=should_cancel,
            )

        def on_success(notes: list[dict[str, str]]) -> None:
            progress.cleanup()
            self.generate_btn.setEnabled(True)
            self.generate_btn.setText("Generate notes")
            if notes:
                # Lock note type, deck and field selection after first successful generation
                if not self._is_locked_by_context:
                    self._is_locked_by_context = (model, deck_name)
                    self.note_type_combo.setEnabled(False)
                    self.deck_combo.setEnabled(False)
                    self.field_list.setEnabled(False)

                self.table.append_notes(notes, selected_fields)
                self._update_create_button_state()
            else:
                showInfo("No notes were generated.")

        def on_failure(e: Exception) -> None:
            progress.cleanup()
            self.generate_btn.setEnabled(True)
            self.generate_btn.setText("Generate notes")
            showWarning(f"Generation failed: {e!s}")

        QueryOp(
            parent=self,
            op=generate,
            success=on_success,
        ).failure(on_failure).run_in_background()

    def _on_create_clicked(self) -> None:
        notes_data = self.table.get_all_notes()
        if not notes_data:
            showInfo("No notes to create.")
            return

        note_type_name = self.note_type_combo.currentText()
        deck_name = self.deck_combo.currentText()

        model = self.col.models.by_name(note_type_name)
        if not model:
            return

        deck_id = self.col.decks.id(deck_name)
        if deck_id is None:
            showWarning(f"Deck '{deck_name}' not found.")
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
            showInfo(f"Successfully added {count} notes to deck '{deck_name}'.")
            self.accept()

        def on_failure(e: Exception) -> None:
            showWarning(f"Failed to add notes: {e!s}")

        QueryOp(
            parent=self,
            op=add_notes,
            success=on_success,
        ).failure(on_failure).run_in_background()
