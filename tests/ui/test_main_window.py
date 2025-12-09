"""
Tests for main window.

Tests the TransformerManMainWindow class - the main transformation interface.
Focuses on user experiences: window creation, note type selection, field display,
and button interactions.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import Mock, patch

if TYPE_CHECKING:
    from pathlib import Path
    from pytestqt.qtbot import QtBot
    from transformerman.lib.addon_config import AddonConfig

from aqt.qt import QWidget, QCheckBox, QLineEdit, QComboBox, QPushButton, Qt

from transformerman.ui.main_window import TransformerManMainWindow
from tests.tools import with_test_collection, MockCollection, test_collection as test_collection_fixture

col = test_collection_fixture

class TestTransformerManMainWindow:
    """Test class for TransformerManMainWindow."""

    @with_test_collection("two_deck_collection")
    def test_window_creation(
        self,
        qtbot: QtBot,
        parent_widget: QWidget,
        col: MockCollection,
        dummy_lm_client: Mock,
        addon_config: AddonConfig,
        user_files_dir: Path,
        is_dark_mode: bool,
    ) -> None:
        """Test that main window can be created with all required dependencies."""
        note_ids = list(col.find_notes("*")[0:3])

        window = TransformerManMainWindow(
            parent=parent_widget,
            is_dark_mode=is_dark_mode,
            col=col,
            note_ids=note_ids,
            lm_client=dummy_lm_client,
            addon_config=addon_config,
            user_files_dir=user_files_dir,
        )
        qtbot.addWidget(window)

        assert window.parent() is parent_widget
        assert window.is_dark_mode == is_dark_mode
        assert window.col is col
        assert window.note_ids == note_ids
        assert window.lm_client is dummy_lm_client
        assert window.addon_config is addon_config
        assert window.user_files_dir == user_files_dir

        # Window should have correct title
        assert window.windowTitle() == "TransformerMan"

        # Should have minimum size set
        assert window.minimumWidth() >= 500
        assert window.minimumHeight() >= 400

        # Verify SelectedNotes was created and has correct note count
        assert window.selected_notes.get_ids() == note_ids
        assert len(window.selected_notes) == 3
        assert window.selected_notes.get_note_type_counts() == {"Basic": 3}

    @with_test_collection("two_deck_collection")
    def test_ui_components_created(
        self,
        qtbot: QtBot,
        parent_widget: QWidget,
        col: MockCollection,
        dummy_lm_client: Mock,
        addon_config: AddonConfig,
        user_files_dir: Path,
        is_dark_mode: bool,
    ) -> None:
        """Test that all UI components are created."""
        note_ids = list(col.find_notes("*")[0:3])

        window = TransformerManMainWindow(
            parent=parent_widget,
            is_dark_mode=is_dark_mode,
            col=col,
            note_ids=note_ids,
            lm_client=dummy_lm_client,
            addon_config=addon_config,
            user_files_dir=user_files_dir,
        )
        qtbot.addWidget(window)

        # Check key UI components exist
        assert hasattr(window, 'note_type_combo')
        assert isinstance(window.note_type_combo, QComboBox)

        assert hasattr(window, 'notes_count_label')
        # Label should have bold HTML text with empty field count
        label_text = window.notes_count_label.text()
        assert label_text != ""
        assert label_text.startswith("<b>")
        assert label_text.endswith("</b>")
        assert "notes selected" in label_text
        # May or may not have "notes with empty fields" depending on empty field count
        # Accept either case

        assert hasattr(window, 'preview_button')
        assert isinstance(window.preview_button, QPushButton)
        assert window.preview_button.text() == "Preview"

        assert hasattr(window, 'apply_button')
        assert isinstance(window.apply_button, QPushButton)
        assert window.apply_button.text() == "Apply"

        assert hasattr(window, 'preview_table')
        # preview_table is a PreviewTable widget

    @with_test_collection("empty_collection")
    def test_note_type_selection_populated(
        self,
        qtbot: QtBot,
        parent_widget: QWidget,
        col: MockCollection,
        dummy_lm_client: Mock,
        addon_config: AddonConfig,
        user_files_dir: Path,
        is_dark_mode: bool,
    ) -> None:

        """Test that note type combo box is populated with note types."""
        # Create notes with different note types
        basic_model = col.models.by_name("Basic")
        cloze_model = col.models.by_name("Cloze")
        assert basic_model is not None
        assert cloze_model is not None
        deck = col.decks.all()[0]
        deck_id = deck["id"]

        note_ids = []

        # Add 3 Basic notes
        for i in range(3):
            note = col.new_note(basic_model)
            note["Front"] = f"Front {i}"
            note["Back"] = f"Back {i}"
            col.add_note(note, deck_id)
            note_ids.append(note.id)

        # Add 1 Cloze note
        cloze_note = col.new_note(cloze_model)
        cloze_note["Text"] = "This is a {{c1::cloze}} deletion"
        cloze_note["Back Extra"] = "Extra info"
        col.add_note(cloze_note, deck_id)
        note_ids.append(cloze_note.id)

        window = TransformerManMainWindow(
            parent=parent_widget,
            is_dark_mode=is_dark_mode,
            col=col,
            note_ids=note_ids,
            lm_client=dummy_lm_client,
            addon_config=addon_config,
            user_files_dir=user_files_dir,
        )
        qtbot.addWidget(window)

        # Note type combo should be populated
        assert window.note_type_combo.count() == 2
        assert window.note_type_combo.itemText(0) == "Basic"
        assert window.note_type_combo.itemText(1) == "Cloze"

        # First (most common) note type should be selected
        assert window.note_type_combo.currentText() == "Basic"
        assert window.current_note_type == "Basic"


    @with_test_collection("two_deck_collection")
    def test_field_checkboxes_created(
        self,
        qtbot: QtBot,
        parent_widget: QWidget,
        col: MockCollection,
        dummy_lm_client: Mock,
        addon_config: AddonConfig,
        user_files_dir: Path,
        is_dark_mode: bool,
    ) -> None:
        """Test that field checkboxes and instruction inputs are created."""
        note_ids = list(col.find_notes("*")[0:2])

        window = TransformerManMainWindow(
            parent=parent_widget,
            is_dark_mode=is_dark_mode,
            col=col,
            note_ids=note_ids,
            lm_client=dummy_lm_client,
            addon_config=addon_config,
            user_files_dir=user_files_dir,
        )
        qtbot.addWidget(window)

        # Set up combo box with Basic note type and trigger change
        window.note_type_combo.addItem("Basic")
        window.note_type_combo.setCurrentText("Basic")
        # Trigger the signal
        window.note_type_combo.currentTextChanged.emit("Basic")

        # Wait for signal to be processed
        qtbot.waitUntil(lambda: len(window.field_checkboxes) > 0)

        # Should have field checkboxes for Basic note type fields
        assert len(window.field_checkboxes) > 0
        assert "Front" in window.field_checkboxes
        assert "Back" in window.field_checkboxes

        # Checkboxes should be QCheckBox instances
        front_checkbox = window.field_checkboxes["Front"]
        assert isinstance(front_checkbox, QCheckBox)
        assert front_checkbox.text() == "Front"

        # First two fields should be checked by default
        assert front_checkbox.isChecked()

        # Should have corresponding instruction inputs
        assert "Front" in window.field_instructions
        front_input = window.field_instructions["Front"]
        assert isinstance(front_input, QLineEdit)
        assert front_input.placeholderText() == "Optional instructions for this field..."

        # Instruction input should be enabled for checked fields
        assert front_input.isEnabled()

    @with_test_collection("two_deck_collection")
    def test_field_selection_enables_input(
        self,
        qtbot: QtBot,
        parent_widget: QWidget,
        col: MockCollection,
        dummy_lm_client: Mock,
        addon_config: AddonConfig,
        user_files_dir: Path,
        is_dark_mode: bool,
    ) -> None:
        """Test that checking/unchecking fields enables/disables instruction inputs."""
        note_ids = list(col.find_notes("*")[0:2])

        window = TransformerManMainWindow(
            parent=parent_widget,
            is_dark_mode=is_dark_mode,
            col=col,
            note_ids=note_ids,
            lm_client=dummy_lm_client,
            addon_config=addon_config,
            user_files_dir=user_files_dir,
        )
        qtbot.addWidget(window)

        # Set up combo box with Basic note type and trigger change
        window.note_type_combo.addItem("Basic")
        window.note_type_combo.setCurrentText("Basic")
        window.note_type_combo.currentTextChanged.emit("Basic")
        qtbot.waitUntil(lambda: len(window.field_checkboxes) > 0)

        front_checkbox = window.field_checkboxes["Front"]
        front_input = window.field_instructions["Front"]

        # Initially should be enabled (checked by default)
        assert front_checkbox.isChecked()
        assert front_input.isEnabled()

        # Unchecking should disable input - trigger the checkbox stateChanged signal
        front_checkbox.setChecked(False)
        front_checkbox.stateChanged.emit(0)  # 0 = Unchecked

        assert not front_input.isEnabled()

        # Re-checking should re-enable input
        front_checkbox.setChecked(True)
        front_checkbox.stateChanged.emit(2)  # 2 = Checked

        assert front_input.isEnabled()

    @with_test_collection("two_deck_collection")
    def test_preview_button_state(
        self,
        qtbot: QtBot,
        parent_widget: QWidget,
        col: MockCollection,
        dummy_lm_client: Mock,
        addon_config: AddonConfig,
        user_files_dir: Path,
        is_dark_mode: bool,
    ) -> None:
        """Test that preview button state reflects whether there are empty fields to fill."""
        note_ids = list(col.find_notes("*")[0:2])

        window = TransformerManMainWindow(
            parent=parent_widget,
            is_dark_mode=is_dark_mode,
            col=col,
            note_ids=note_ids,
            lm_client=dummy_lm_client,
            addon_config=addon_config,
            user_files_dir=user_files_dir,
        )
        qtbot.addWidget(window)

        # Set up combo box with Basic note type and trigger change
        window.note_type_combo.addItem("Basic")
        window.note_type_combo.setCurrentText("Basic")
        window.note_type_combo.currentTextChanged.emit("Basic")
        qtbot.waitUntil(lambda: len(window.field_checkboxes) > 0)

        # With notes selected and fields checked but no empty fields,
        # preview button should be disabled (nothing to transform)
        assert window.preview_button.text() == "Preview"
        assert not window.preview_button.isEnabled()

    @with_test_collection("two_deck_collection")
    def test_apply_button_initial_state(
        self,
        qtbot: QtBot,
        parent_widget: QWidget,
        col: MockCollection,
        dummy_lm_client: Mock,
        addon_config: AddonConfig,
        user_files_dir: Path,
        is_dark_mode: bool,
    ) -> None:
        """Test that apply button starts disabled."""
        note_ids = list(col.find_notes("*")[0:2])

        window = TransformerManMainWindow(
            parent=parent_widget,
            is_dark_mode=is_dark_mode,
            col=col,
            note_ids=note_ids,
            lm_client=dummy_lm_client,
            addon_config=addon_config,
            user_files_dir=user_files_dir,
        )
        qtbot.addWidget(window)

        # Apply button should start disabled (no preview results yet)
        assert not window.apply_button.isEnabled()

    @with_test_collection("empty_collection")
    @patch('transformerman.ui.main_window.TransformNotesWithProgress')
    @patch('transformerman.ui.main_window.showInfo')
    def test_preview_button_click_triggers_transformation(  # noqa: PLR0913
        self,
        mock_show_info: Mock,
        mock_transformer_class: Mock,
        qtbot: QtBot,
        parent_widget: QWidget,
        col: MockCollection,
        dummy_lm_client: Mock,
        addon_config: AddonConfig,
        user_files_dir: Path,
        is_dark_mode: bool,
    ) -> None:
        """Test that preview button click triggers transformation process."""
        # Add some notes to the collection
        model = col.models.by_name("Basic")
        assert model is not None
        deck = col.decks.all()[0]
        deck_id = deck["id"]

        note_ids = []
        # Add 2 Basic notes, one with empty Front field
        for i in range(2):
            note = col.new_note(model)
            note["Front"] = "" if i == 0 else f"Front {i}"  # First note has empty Front
            note["Back"] = f"Back {i}"
            col.add_note(note, deck_id)
            note_ids.append(note.id)

        # Setup the mock transformer to return appropriate values
        mock_transformer_instance = Mock()
        mock_transformer_instance.get_num_api_calls_needed.return_value = 1
        mock_transformer_class.return_value = mock_transformer_instance

        window = TransformerManMainWindow(
            parent=parent_widget,
            is_dark_mode=is_dark_mode,
            col=col,
            note_ids=note_ids,
            lm_client=dummy_lm_client,
            addon_config=addon_config,
            user_files_dir=user_files_dir,
        )
        qtbot.addWidget(window)

        # Set up combo box with Basic note type and trigger change
        window.note_type_combo.addItem("Basic")
        window.note_type_combo.setCurrentText("Basic")
        window.note_type_combo.currentTextChanged.emit("Basic")
        qtbot.waitUntil(lambda: len(window.field_checkboxes) > 0)

        # Click preview button
        qtbot.mouseClick(window.preview_button, Qt.MouseButton.LeftButton)

        # Should call transformer.transform() method
        mock_transformer_instance.transform.assert_called_once()

        # Check key arguments to transformer.transform()
        call_args = mock_transformer_instance.transform.call_args
        assert 'note_ids' in call_args[1]
        assert 'prompt_builder' in call_args[1]
        assert 'selected_fields' in call_args[1]
        assert 'note_type_name' in call_args[1]
        assert 'on_success' in call_args[1]

        # showInfo should not be called (we have notes with empty fields)
        mock_show_info.assert_not_called()

    @with_test_collection("empty_collection")
    def test_note_type_change_updates_ui(
        self,
        qtbot: QtBot,
        parent_widget: QWidget,
        col: MockCollection,
        dummy_lm_client: Mock,
        addon_config: AddonConfig,
        user_files_dir: Path,
        is_dark_mode: bool,
    ) -> None:
        """Test that changing note type updates field display and counts."""
        # Create notes with different note types
        basic_model = col.models.by_name("Basic")
        cloze_model = col.models.by_name("Cloze")
        assert basic_model is not None
        assert cloze_model is not None
        deck = col.decks.all()[0]
        deck_id = deck["id"]

        note_ids = []

        # Add 2 Basic notes
        for i in range(2):
            note = col.new_note(basic_model)
            note["Front"] = f"Front {i}"
            note["Back"] = f"Back {i}"
            col.add_note(note, deck_id)
            note_ids.append(note.id)

        # Add 2 Cloze notes
        for i in range(2):
            cloze_note = col.new_note(cloze_model)
            cloze_note["Text"] = f"This is a {{c1::cloze}} deletion {i}"
            cloze_note["Back Extra"] = f"Extra info {i}"
            col.add_note(cloze_note, deck_id)
            note_ids.append(cloze_note.id)

        window = TransformerManMainWindow(
            parent=parent_widget,
            is_dark_mode=is_dark_mode,
            col=col,
            note_ids=note_ids,
            lm_client=dummy_lm_client,
            addon_config=addon_config,
            user_files_dir=user_files_dir,
        )
        qtbot.addWidget(window)

        # Add note types to combo box
        window.note_type_combo.addItems(["Basic", "Cloze"])

        # Change to Basic note type by triggering the signal
        window.note_type_combo.setCurrentText("Basic")
        window.note_type_combo.currentTextChanged.emit("Basic")
        qtbot.waitUntil(lambda: len(window.field_checkboxes) > 0)

        assert window.current_note_type == "Basic"
        assert "Front" in window.field_checkboxes
        assert "Back" in window.field_checkboxes

        # Change to Cloze note type by triggering the signal
        window.note_type_combo.setCurrentText("Cloze")
        window.note_type_combo.currentTextChanged.emit("Cloze")
        qtbot.waitUntil(lambda: "Text" in window.field_checkboxes)

        assert window.current_note_type == "Cloze"
        assert "Text" in window.field_checkboxes
        assert "Back Extra" in window.field_checkboxes
        assert "Front" not in window.field_checkboxes  # Old fields cleared
