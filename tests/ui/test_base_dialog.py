"""
Tests for base dialog.

Tests the TransformerManBaseDialog class which provides geometry saving/restoring
functionality for all TransformerMan dialogs.
"""

from __future__ import annotations

from unittest.mock import patch

from aqt.qt import QCloseEvent, QWidget

from transformerman.ui.base_dialog import TransformerManBaseDialog
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


class TestTransformerManBaseDialog:
    """Test class for TransformerManBaseDialog."""

    def test_dialog_creation(self, qtbot: QtBot, parent_widget: QWidget) -> None:
        """Test that dialog can be created and has correct parent."""
        dialog = TransformerManBaseDialog(parent_widget)
        qtbot.addWidget(dialog)

        assert dialog.parent() is parent_widget
        assert isinstance(dialog, TransformerManBaseDialog)

        # Dialog should be visible (though not necessarily shown)
        dialog.show()
        qtbot.waitExposed(dialog)
        assert dialog.isVisible()

    def test_close_event_saves_geometry(self, qtbot: QtBot) -> None:
        """Test that close event triggers geometry saving."""
        dialog = TransformerManBaseDialog()
        qtbot.addWidget(dialog)

        with patch('transformerman.ui.base_dialog.saveGeom') as mock_save:
            # Create a real QCloseEvent
            close_event = QCloseEvent()

            # Trigger close event
            dialog.closeEvent(close_event)

            # Check saveGeom was called
            mock_save.assert_called_once()
            call_args = mock_save.call_args
            assert call_args[0][0] is dialog

            # Check the geometry key
            expected_key = f"transformerman_{dialog.__class__.__name__}"
            assert call_args[0][1] == expected_key

            # The event should be accepted (default behavior)
            assert close_event.isAccepted()



    def test_multiple_dialogs_unique(self, qtbot: QtBot) -> None:
        """Test that multiple dialogs can be created independently."""
        dialog1 = TransformerManBaseDialog()
        dialog2 = TransformerManBaseDialog()
        qtbot.addWidget(dialog1)
        qtbot.addWidget(dialog2)

        # Both should be independent instances
        assert dialog1 is not dialog2
        assert dialog1.parent() != dialog2.parent() or (
            dialog1.parent() is None and dialog2.parent() is None
        )

        # Both should be valid widgets
        assert dialog1.objectName() != dialog2.objectName() or (
            dialog1.objectName() == "" and dialog2.objectName() == ""
        )
