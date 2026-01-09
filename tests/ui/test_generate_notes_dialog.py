"""
Tests for GenerateNotesDialog.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path
    from unittest.mock import Mock
    from pytestqt.qtbot import QtBot
    from aqt.qt import QWidget
    from transformerman.lib.addon_config import AddonConfig

from aqt.qt import Qt

from transformerman.ui.generate.generate_notes_dialog import GenerateNotesDialog
from transformerman.ui.stats_widget import StatsWidget
from tests.tools import with_test_collection, TestCollection, test_collection as test_collection_fixture

col = test_collection_fixture


class TestGenerateNotesDialog:
    """Test class for GenerateNotesDialog."""

    @with_test_collection("two_deck_collection")
    def test_dialog_creation(
        self,
        qtbot: QtBot,
        parent_widget: QWidget,
        col: TestCollection,
        dummy_lm_client: Mock,
        addon_config: AddonConfig,
        user_files_dir: Path,
        is_dark_mode: bool,
    ) -> None:
        """Test that dialog can be created with all required dependencies."""
        note_ids = list(col.find_notes("*")[0:3])

        dialog = GenerateNotesDialog(
            parent=parent_widget,
            is_dark_mode=is_dark_mode,
            col=col,
            lm_client=dummy_lm_client,
            addon_config=addon_config,
            user_files_dir=user_files_dir,
            note_ids=note_ids,
        )
        qtbot.addWidget(dialog)

        assert dialog.parent() is parent_widget
        assert dialog.is_dark_mode == is_dark_mode
        assert dialog.col is col
        assert dialog.lm_client is dummy_lm_client
        assert dialog.addon_config is addon_config

        # Verify stats widget exists
        assert hasattr(dialog, "stats_widget")
        assert isinstance(dialog.stats_widget, StatsWidget)

        # Verify stat containers exist in the widget
        containers = dialog.stats_widget.stat_containers
        assert "selected" in containers
        assert "api_client" in containers
        assert "client_model" in containers

    @with_test_collection("two_deck_collection")
    def test_stats_update(
        self,
        qtbot: QtBot,
        parent_widget: QWidget,
        col: TestCollection,
        dummy_lm_client: Mock,
        addon_config: AddonConfig,
        user_files_dir: Path,
        is_dark_mode: bool,
    ) -> None:
        """Test that stats update correctly."""
        # Create notes with different note types
        basic_model = col.models.by_name("Basic")
        deck_id = col.decks.id_for_name("Default")
        assert basic_model is not None
        assert deck_id is not None

        note_ids = []
        # Add 3 Basic notes
        for i in range(3):
            note = col.new_note(basic_model)
            note["Front"] = f"Front {i}"
            note["Back"] = f"Back {i}"
            col.add_note(note, deck_id)
            note_ids.append(note.id)

        dialog = GenerateNotesDialog(
            parent=parent_widget,
            is_dark_mode=is_dark_mode,
            col=col,
            lm_client=dummy_lm_client,
            addon_config=addon_config,
            user_files_dir=user_files_dir,
            note_ids=note_ids,
        )
        qtbot.addWidget(dialog)

        # Initial stats check
        stats = dialog.stats_widget.stat_containers
        assert stats["selected"].value_label.text() == "<b>3 notes</b>"
        assert stats["api_client"].value_label.text() == f"<b>{dummy_lm_client.name}</b>"

        # Verify click callbacks are set (by checking cursor)
        assert stats["api_client"].cursor().shape() == Qt.CursorShape.PointingHandCursor
        assert stats["client_model"].cursor().shape() == Qt.CursorShape.PointingHandCursor
