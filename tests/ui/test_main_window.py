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
    from anki.notes import NoteId

from aqt.qt import QWidget, QCheckBox, QLineEdit, QComboBox, QPushButton, Qt

from transformerman.ui.main_window import TransformerManMainWindow
from tests.tools import with_test_collection, MockCollection, test_collection as test_collection_fixture

col = test_collection_fixture

class TestTransformerManMainWindow:
    """Test class for TransformerManMainWindow."""

    @with_test_collection("empty_collection")
    @patch('transformerman.ui.main_window.SelectedNotes')
    def test_window_creation(  # noqa: PLR0913
        self,
        mock_selected_notes_cls: Mock,
        qtbot: QtBot,
        parent_widget: QWidget,
        col: MockCollection,
        dummy_lm_client: Mock,
        addon_config: Mock,
        user_files_dir: Path,
        is_dark_mode: bool,
        test_note_ids: list[NoteId],
    ) -> None:
        """Test that main window can be created with all required dependencies."""
        # Mock SelectedNotes instance
        mock_selected_notes = Mock()
        mock_selected_notes.get_note_type_counts.return_value = {}
        mock_selected_notes.__len__ = Mock(return_value=0)
        mock_selected_notes_cls.return_value = mock_selected_notes

        window = TransformerManMainWindow(
            parent=parent_widget,
            is_dark_mode=is_dark_mode,
            col=col,
            note_ids=test_note_ids,
            lm_client=dummy_lm_client,
            addon_config=addon_config,
            user_files_dir=user_files_dir,
        )
        qtbot.addWidget(window)

        assert window.parent() is parent_widget
        assert window.is_dark_mode == is_dark_mode
        assert window.col is col
        assert window.note_ids == test_note_ids
        assert window.lm_client is dummy_lm_client
        assert window.addon_config is addon_config
        assert window.user_files_dir == user_files_dir

        # Window should have correct title
        assert window.windowTitle() == "TransformerMan"

        # Should have minimum size set
        assert window.minimumWidth() >= 500
        assert window.minimumHeight() >= 400

    @with_test_collection("empty_collection")
    @patch('transformerman.ui.main_window.SelectedNotes')
    def test_ui_components_created(  # noqa: PLR0913
        self,
        mock_selected_notes_cls: Mock,
        qtbot: QtBot,
        parent_widget: QWidget,
        col: MockCollection,
        dummy_lm_client: Mock,
        addon_config: Mock,
        user_files_dir: Path,
        is_dark_mode: bool,
        test_note_ids: list[NoteId],
    ) -> None:
        """Test that all UI components are created."""
        # Mock SelectedNotes instance
        mock_selected_notes = Mock()
        mock_selected_notes.get_note_type_counts.return_value = {"Basic": 3}
        mock_selected_notes.get_field_names.return_value = []
        mock_selected_notes.__len__ = Mock(return_value=0)
        mock_empty_filter = Mock()
        mock_empty_filter.note_ids = []
        mock_empty_filter.__len__ = Mock(return_value=0)
        mock_selected_notes.filter_by_empty_field.return_value = mock_empty_filter
        mock_selected_notes.filter_by_note_type.return_value = []
        mock_selected_notes_cls.return_value = mock_selected_notes

        window = TransformerManMainWindow(
            parent=parent_widget,
            is_dark_mode=is_dark_mode,
            col=col,
            note_ids=test_note_ids,
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
        addon_config: Mock,
        user_files_dir: Path,
        is_dark_mode: bool,
        test_note_ids: list[NoteId],
    ) -> None:

        """Test that note type combo box is populated with note types."""
        # Mock SelectedNotes to return specific note type counts
        mock_selected_notes = Mock()
        mock_selected_notes.get_note_type_counts.return_value = {
            "Basic": 3,
            "Cloze": 1,
        }
        # Add methods needed by _on_note_type_changed
        mock_selected_notes.filter_by_note_type.return_value = test_note_ids[:2]  # Return first 2 notes
        mock_selected_notes.get_field_names.return_value = ["Front", "Back"]
        mock_selected_notes.filter_by_empty_field.return_value.note_ids = []
        mock_selected_notes.filter_by_empty_field.return_value.__len__ = Mock(return_value=0)

        with patch('transformerman.ui.main_window.SelectedNotes', return_value=mock_selected_notes):
            window = TransformerManMainWindow(
                parent=parent_widget,
                is_dark_mode=is_dark_mode,
                col=col,
                note_ids=test_note_ids,
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

    @with_test_collection("empty_collection")
    @patch('transformerman.ui.main_window.SelectedNotes')
    def test_field_checkboxes_created(  # noqa: PLR0913
        self,
        mock_selected_notes_cls: Mock,
        qtbot: QtBot,
        parent_widget: QWidget,
        col: MockCollection,
        dummy_lm_client: Mock,
        addon_config: Mock,
        user_files_dir: Path,
        is_dark_mode: bool,
        test_note_ids: list[NoteId],
    ) -> None:
        """Test that field checkboxes and instruction inputs are created."""
        # Mock SelectedNotes instance
        mock_selected_notes = Mock()
        mock_selected_notes.get_note_type_counts.return_value = {}
        mock_selected_notes.filter_by_note_type.return_value = test_note_ids[:2]
        mock_selected_notes.get_field_names.return_value = ["Front", "Back"]
        mock_selected_notes.filter_by_empty_field.return_value.note_ids = []
        mock_selected_notes.filter_by_empty_field.return_value.__len__ = Mock(return_value=0)
        mock_selected_notes.__len__ = Mock(return_value=0)
        mock_selected_notes_cls.return_value = mock_selected_notes

        window = TransformerManMainWindow(
            parent=parent_widget,
            is_dark_mode=is_dark_mode,
            col=col,
            note_ids=test_note_ids,
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

    @with_test_collection("empty_collection")
    @patch('transformerman.ui.main_window.SelectedNotes')
    def test_field_selection_enables_input(  # noqa: PLR0913
        self,
        mock_selected_notes_cls: Mock,
        qtbot: QtBot,
        parent_widget: QWidget,
        col: MockCollection,
        dummy_lm_client: Mock,
        addon_config: Mock,
        user_files_dir: Path,
        is_dark_mode: bool,
        test_note_ids: list[NoteId],
    ) -> None:
        """Test that checking/unchecking fields enables/disables instruction inputs."""
        # Mock SelectedNotes instance
        mock_selected_notes = Mock()
        mock_selected_notes.get_note_type_counts.return_value = {}
        mock_selected_notes.filter_by_note_type.return_value = test_note_ids[:2]
        mock_selected_notes.get_field_names.return_value = ["Front", "Back"]
        mock_selected_notes.filter_by_empty_field.return_value.note_ids = []
        mock_selected_notes.filter_by_empty_field.return_value.__len__ = Mock(return_value=0)
        mock_selected_notes.__len__ = Mock(return_value=0)
        mock_selected_notes_cls.return_value = mock_selected_notes

        window = TransformerManMainWindow(
            parent=parent_widget,
            is_dark_mode=is_dark_mode,
            col=col,
            note_ids=test_note_ids,
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

    @with_test_collection("empty_collection")
    @patch('transformerman.ui.main_window.SelectedNotes')
    def test_preview_button_state(  # noqa: PLR0913
        self,
        mock_selected_notes_cls: Mock,
        qtbot: QtBot,
        parent_widget: QWidget,
        col: MockCollection,
        dummy_lm_client: Mock,
        addon_config: Mock,
        user_files_dir: Path,
        is_dark_mode: bool,
        test_note_ids: list[NoteId],
    ) -> None:
        """Test that preview button is enabled when notes and fields are selected."""
        # Mock SelectedNotes instance
        mock_selected_notes = Mock()
        mock_selected_notes.get_note_type_counts.return_value = {}
        mock_selected_notes.filter_by_note_type.return_value = test_note_ids[:2]  # Has notes
        mock_selected_notes.get_field_names.return_value = ["Front", "Back"]
        mock_selected_notes.has_note_with_empty_field.return_value = False  # No empty fields
        mock_selected_notes.filter_by_empty_field.return_value.note_ids = []
        mock_selected_notes.filter_by_empty_field.return_value.__len__ = Mock(return_value=0)
        mock_selected_notes.__len__ = Mock(return_value=0)
        mock_selected_notes_cls.return_value = mock_selected_notes

        window = TransformerManMainWindow(
            parent=parent_widget,
            is_dark_mode=is_dark_mode,
            col=col,
            note_ids=test_note_ids,
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

        # With notes selected and fields checked, preview button should be enabled
        assert window.preview_button.text() == "Preview"
        assert window.preview_button.isEnabled()

        # Test with no notes selected (empty filtered list)
        mock_selected_notes.filter_by_note_type.return_value = []  # No notes
        # Trigger note type change again to update button state
        window.note_type_combo.currentTextChanged.emit("Basic")
        qtbot.wait(100)  # Give time for state update

        # With no notes, preview button should be disabled
        assert not window.preview_button.isEnabled()

    @with_test_collection("empty_collection")
    @patch('transformerman.ui.main_window.SelectedNotes')
    def test_apply_button_initial_state(  # noqa: PLR0913
        self,
        mock_selected_notes_cls: Mock,
        qtbot: QtBot,
        parent_widget: QWidget,
        col: MockCollection,
        dummy_lm_client: Mock,
        addon_config: Mock,
        user_files_dir: Path,
        is_dark_mode: bool,
        test_note_ids: list[NoteId],
    ) -> None:
        """Test that apply button starts disabled."""
        # Mock SelectedNotes instance
        mock_selected_notes = Mock()
        mock_selected_notes.get_note_type_counts.return_value = {}
        mock_selected_notes.__len__ = Mock(return_value=0)
        mock_selected_notes_cls.return_value = mock_selected_notes

        window = TransformerManMainWindow(
            parent=parent_widget,
            is_dark_mode=is_dark_mode,
            col=col,
            note_ids=test_note_ids,
            lm_client=dummy_lm_client,
            addon_config=addon_config,
            user_files_dir=user_files_dir,
        )
        qtbot.addWidget(window)

        # Apply button should start disabled (no preview results yet)
        assert not window.apply_button.isEnabled()

    @with_test_collection("empty_collection")
    @patch('transformerman.ui.main_window.SelectedNotes')
    @patch('transformerman.ui.main_window.transform_notes_with_progress')
    @patch('transformerman.ui.main_window.showInfo')
    def test_preview_button_click_triggers_transformation(  # noqa: PLR0913
        self,
        mock_show_info: Mock,
        mock_transform: Mock,
        mock_selected_notes_cls: Mock,
        qtbot: QtBot,
        parent_widget: QWidget,
        col: MockCollection,
        dummy_lm_client: Mock,
        addon_config: Mock,
        user_files_dir: Path,
        is_dark_mode: bool,
        test_note_ids: list[NoteId],
    ) -> None:
        """Test that preview button click triggers transformation process."""
        # Mock SelectedNotes instance
        mock_selected_notes = Mock()
        mock_selected_notes.get_note_type_counts.return_value = {}
        mock_selected_notes.filter_by_note_type.return_value = test_note_ids[:2]
        mock_selected_notes.get_field_names.return_value = ["Front", "Back"]
        mock_selected_notes.has_note_with_empty_field.return_value = True
        mock_selected_notes.filter_by_empty_field.return_value.note_ids = test_note_ids[:1]
        mock_selected_notes.filter_by_empty_field.return_value.__len__ = Mock(return_value=1)
        mock_selected_notes.__len__ = Mock(return_value=0)
        mock_selected_notes_cls.return_value = mock_selected_notes

        window = TransformerManMainWindow(
            parent=parent_widget,
            is_dark_mode=is_dark_mode,
            col=col,
            note_ids=test_note_ids,
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

        # Should call transform_notes_with_progress
        mock_transform.assert_called_once()

        # Check key arguments
        call_args = mock_transform.call_args
        assert call_args[1]['parent'] is window
        assert call_args[1]['col'] is col
        assert call_args[1]['lm_client'] is dummy_lm_client
        assert call_args[1]['addon_config'] is addon_config
        assert call_args[1]['user_files_dir'] == user_files_dir

        # showInfo should not be called (since we mocked has_note_with_empty_field to return True)
        mock_show_info.assert_not_called()

    @with_test_collection("empty_collection")
    @patch('transformerman.ui.main_window.SelectedNotes')
    def test_note_type_change_updates_ui(  # noqa: PLR0913
        self,
        mock_selected_notes_cls: Mock,
        qtbot: QtBot,
        parent_widget: QWidget,
        col: MockCollection,
        dummy_lm_client: Mock,
        addon_config: Mock,
        user_files_dir: Path,
        is_dark_mode: bool,
        test_note_ids: list[NoteId],
    ) -> None:
        """Test that changing note type updates field display and counts."""
        # Mock SelectedNotes instance
        mock_selected_notes = Mock()
        mock_selected_notes.get_note_type_counts.return_value = {}
        mock_selected_notes.filter_by_note_type.return_value = test_note_ids[:2]  # 2 notes
        mock_selected_notes.filter_by_empty_field.return_value.note_ids = []
        mock_selected_notes.filter_by_empty_field.return_value.__len__ = Mock(return_value=0)
        mock_selected_notes.__len__ = Mock(return_value=0)
        def get_field_names_side_effect(note_type: str) -> list[str]:
            field_map = {
                "Basic": ["Front", "Back"],
                "Cloze": ["Text", "Extra"],
            }
            return field_map.get(note_type, [])
        mock_selected_notes.get_field_names.side_effect = get_field_names_side_effect
        mock_selected_notes_cls.return_value = mock_selected_notes

        window = TransformerManMainWindow(
            parent=parent_widget,
            is_dark_mode=is_dark_mode,
            col=col,
            note_ids=test_note_ids,
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
        assert "Extra" in window.field_checkboxes
        assert "Front" not in window.field_checkboxes  # Old fields cleared
