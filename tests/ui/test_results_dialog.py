"""
Tests for results dialog.

Tests the ResultsDialog class which displays transformation results.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from unittest.mock import Mock
    from pytestqt.qtbot import QtBot
    from anki.notes import NoteId

from aqt.qt import QWidget, QLabel, QPushButton, Qt

from transformerman.ui.results_dialog import ResultsDialog


class TestResultsDialog:
    """Test class for ResultsDialog."""

    def test_dialog_creation(
        self,
        qtbot: QtBot,
        parent_widget: QWidget,
        mock_collection: Mock,
        test_note_ids: list[NoteId],
        test_selected_fields: set[str],
        test_note_type_name: str,
        test_transform_results: dict[str, int],
    ) -> None:
        """Test that results dialog can be created."""
        dialog = ResultsDialog(
            parent=parent_widget,
            col=mock_collection,
            note_ids=test_note_ids,
            selected_fields=test_selected_fields,
            note_type_name=test_note_type_name,
            results=test_transform_results,
        )
        qtbot.addWidget(dialog)

        assert dialog.parent() is parent_widget
        assert dialog.col is mock_collection
        assert dialog.note_ids == test_note_ids
        assert dialog.selected_fields == test_selected_fields
        assert dialog.note_type_name == test_note_type_name
        assert dialog.results == test_transform_results

        # Dialog should have correct title
        assert dialog.windowTitle() == "Transformation Results"

        # Should have minimum size set
        assert dialog.minimumWidth() >= 500
        assert dialog.minimumHeight() >= 300

    def test_ui_components_created(
        self,
        qtbot: QtBot,
        parent_widget: QWidget,
        mock_collection: Mock,
        test_note_ids: list[NoteId],
        test_selected_fields: set[str],
        test_note_type_name: str,
        test_transform_results: dict[str, int],
    ) -> None:
        """Test that all UI components are created."""
        dialog = ResultsDialog(
            parent=parent_widget,
            col=mock_collection,
            note_ids=test_note_ids,
            selected_fields=test_selected_fields,
            note_type_name=test_note_type_name,
            results=test_transform_results,
        )
        qtbot.addWidget(dialog)

        # Check key UI components exist
        assert hasattr(dialog, 'results_label')
        assert isinstance(dialog.results_label, QLabel)

        assert hasattr(dialog, 'close_button')
        assert isinstance(dialog.close_button, QPushButton)
        assert dialog.close_button.text() == "Close"

    def test_results_displayed(
        self,
        qtbot: QtBot,
        parent_widget: QWidget,
        mock_collection: Mock,
        test_note_ids: list[NoteId],
        test_selected_fields: set[str],
        test_note_type_name: str,
        test_transform_results: dict[str, int],
    ) -> None:
        """Test that transformation results are displayed."""
        dialog = ResultsDialog(
            parent=parent_widget,
            col=mock_collection,
            note_ids=test_note_ids,
            selected_fields=test_selected_fields,
            note_type_name=test_note_type_name,
            results=test_transform_results,
        )
        qtbot.addWidget(dialog)

        # Results should be loaded and displayed
        label_text = dialog.results_label.text()

        # Check that key results are in the HTML
        assert "5" in label_text  # updated count
        assert "1" in label_text  # failed count
        assert "2" in label_text  # batches processed

        # Should contain HTML formatting
        assert "<div" in label_text
        assert "<p" in label_text
        assert "style=" in label_text  # Should have styling

    def test_results_with_zero_updated(
        self,
        qtbot: QtBot,
        parent_widget: QWidget,
        mock_collection: Mock,
        test_note_ids: list[NoteId],
        test_selected_fields: set[str],
        test_note_type_name: str,
    ) -> None:
        """Test results display when no notes were updated."""
        results = {
            "updated": 0,
            "failed": 3,
            "batches_processed": 1,
        }

        dialog = ResultsDialog(
            parent=parent_widget,
            col=mock_collection,
            note_ids=test_note_ids,
            selected_fields=test_selected_fields,
            note_type_name=test_note_type_name,
            results=results,
        )
        qtbot.addWidget(dialog)

        label_text = dialog.results_label.text()

        # Should show 0 updated
        assert "0" in label_text
        assert "3" in label_text  # failed count

    def test_results_with_only_success(
        self,
        qtbot: QtBot,
        parent_widget: QWidget,
        mock_collection: Mock,
        test_note_ids: list[NoteId],
        test_selected_fields: set[str],
        test_note_type_name: str,
    ) -> None:
        """Test results display when all notes succeeded."""
        results = {
            "updated": 10,
            "failed": 0,
            "batches_processed": 2,
        }

        dialog = ResultsDialog(
            parent=parent_widget,
            col=mock_collection,
            note_ids=test_note_ids,
            selected_fields=test_selected_fields,
            note_type_name=test_note_type_name,
            results=results,
        )
        qtbot.addWidget(dialog)

        label_text = dialog.results_label.text()

        # Should show 10 updated, 0 failed
        assert "10" in label_text
        assert "0" in label_text

    def test_close_button_functionality(
        self,
        qtbot: QtBot,
        parent_widget: QWidget,
        mock_collection: Mock,
        test_note_ids: list[NoteId],
        test_selected_fields: set[str],
        test_note_type_name: str,
        test_transform_results: dict[str, int],
    ) -> None:
        """Test that close button works."""
        dialog = ResultsDialog(
            parent=parent_widget,
            col=mock_collection,
            note_ids=test_note_ids,
            selected_fields=test_selected_fields,
            note_type_name=test_note_type_name,
            results=test_transform_results,
        )
        qtbot.addWidget(dialog)

        # Dialog should start visible
        dialog.show()
        qtbot.waitExposed(dialog)
        assert dialog.isVisible()

        # Click close button
        qtbot.mouseClick(dialog.close_button, Qt.MouseButton.LeftButton)

        # Dialog should be accepted/closed
        qtbot.waitUntil(lambda: not dialog.isVisible())
        assert not dialog.isVisible()

    def test_dialog_inherits_geometry_saving(
        self,
        qtbot: QtBot,
        parent_widget: QWidget,
        mock_collection: Mock,
        test_note_ids: list[NoteId],
        test_selected_fields: set[str],
        test_note_type_name: str,
        test_transform_results: dict[str, int],
    ) -> None:
        """Test that dialog inherits geometry saving from base class."""
        dialog = ResultsDialog(
            parent=parent_widget,
            col=mock_collection,
            note_ids=test_note_ids,
            selected_fields=test_selected_fields,
            note_type_name=test_note_type_name,
            results=test_transform_results,
        )
        qtbot.addWidget(dialog)

        # Should have closeEvent method from base class
        assert hasattr(dialog, 'closeEvent')

        # Should be instance of base dialog class
        from transformerman.ui.base_dialog import TransformerManBaseDialog
        assert isinstance(dialog, TransformerManBaseDialog)
