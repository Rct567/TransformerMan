"""
Tests for GenerateNotesDialog.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable

import unittest.mock

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from pathlib import Path
    from unittest.mock import Mock
    from pytestqt.qtbot import QtBot
    from aqt.qt import QWidget
    from transformerman.lib.addon_config import AddonConfig
    from transformerman.lib.lm_clients import DummyLMClient

from aqt.qt import Qt

from transformerman.ui.generate.generate_notes_dialog import GenerateNotesDialog
from transformerman.ui.generate.generating_notes import find_duplicates, GenerationRequest
from transformerman.ui.stats_widget import StatsWidget
from transformerman.lib.xml_parser import NewNote
from tests.tools import with_test_collection, TestCollection, test_collection as test_collection_fixture

col = test_collection_fixture


patch_generating_query_op = unittest.mock.patch("transformerman.ui.generate.generating_notes.QueryOp")


def run_sync(col: TestCollection) -> Callable[..., unittest.mock.Mock]:
    """Helper to make QueryOp run synchronously."""

    def _run_sync(*args: Any, **kwargs: Any) -> unittest.mock.Mock:
        op = kwargs.get("op") or args[1]
        success = kwargs.get("success") or args[2]
        success(op(col))
        m = unittest.mock.Mock()
        m.failure.return_value = m
        return m

    return _run_sync


class TestGenerateNotesDialog:
    """Test class for GenerateNotesDialog."""

    @patch_generating_query_op
    @with_test_collection("two_deck_collection")
    def test_dialog_creation_and_generate_notes(
        self,
        mock_query_op_generating: Mock,
        qtbot: QtBot,
        parent_widget: QWidget,
        col: TestCollection,
        dummy_lm_client: DummyLMClient,
        addon_config: AddonConfig,
        user_files_dir: Path,
        is_dark_mode: bool,
    ) -> None:
        """Test that dialog can be created with all required dependencies."""
        mock_query_op_generating.side_effect = run_sync(col)
        addon_config.update_setting("max_examples", 9)
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

        # assert button is enabled
        assert not dialog.create_btn.isEnabled()
        assert dialog.generate_btn.isEnabled()

        # add some text to textarea and click generate button
        dialog.source_text_edit.setPlainText("Some text")
        qtbot.mouseClick(dialog.generate_btn, Qt.MouseButton.LeftButton)

        # check prompt
        qtbot.waitUntil(lambda: dialog.notes_generator.generator.prompt is not None)
        assert dialog.notes_generator.generator.prompt
        assert dialog.notes_generator.generator.prompt.count("<note nid=") == 9

    @with_test_collection("two_deck_collection")
    def test_stats_update(
        self,
        qtbot: QtBot,
        parent_widget: QWidget,
        col: TestCollection,
        dummy_lm_client: DummyLMClient,
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

    @with_test_collection("two_deck_collection")
    def test_duplicate_highlighting(
        self,
        qtbot: QtBot,
        parent_widget: QWidget,
        col: TestCollection,
        dummy_lm_client: DummyLMClient,
        addon_config: AddonConfig,
        user_files_dir: Path,
        is_dark_mode: bool,
    ) -> None:
        """Test that duplicates are correctly highlighted."""
        # 1. Create an existing note in the collection
        basic_model = col.models.by_name("Basic")
        deck_id = col.decks.id_for_name("Default")
        assert basic_model is not None
        assert deck_id is not None

        existing_note = col.new_note(basic_model)
        existing_note["Front"] = "Existing Front"
        existing_note["Back"] = "Existing Back"
        col.add_note(existing_note, deck_id)

        # 2. Initialize dialog
        dialog = GenerateNotesDialog(
            parent=parent_widget,
            is_dark_mode=is_dark_mode,
            col=col,
            lm_client=dummy_lm_client,
            addon_config=addon_config,
            user_files_dir=user_files_dir,
            note_ids=[],
        )
        qtbot.addWidget(dialog)

        # Mock the generator to return a duplicate note and a unique note
        generated_notes = [
            NewNote({"Front": "Existing Front", "Back": "New Back"}),  # Duplicate Front
            NewNote({"Front": "New Front", "Back": "Existing Back"}),  # Duplicate Back
            NewNote({"Front": "Unique Front", "Back": "Unique Back"}),  # No duplicates
        ]

        # Set up the table columns
        dialog.table.update_columns(["Front", "Back"])

        # Append notes to table
        dialog.table.append_notes(generated_notes)

        # Run duplicate check synchronously for testing
        # 1. Verify logic: find_duplicates
        duplicates = find_duplicates(col, generated_notes, "Default")

        assert 0 in duplicates
        assert "Front" in duplicates[0]
        assert "Back" not in duplicates[0]

        assert 1 in duplicates
        assert "Back" in duplicates[1]
        assert "Front" not in duplicates[1]

        assert 2 not in duplicates

        # 2. Verify UI: highlight_duplicates
        dialog.table.highlight_duplicates(duplicates, start_row=0)

        # Check row 0, col 0 (Front) - Should be highlighted
        item_0_0 = dialog.table.item(0, 0)
        assert item_0_0 is not None
        # Check background color.
        bg_brush = item_0_0.background()
        assert bg_brush.style() != 0  # Qt.BrushStyle.NoBrush

        # Check row 0, col 1 (Back) - Should NOT be highlighted
        item_0_1 = dialog.table.item(0, 1)
        assert item_0_1 is not None
        assert "Duplicate content" in item_0_0.toolTip()
        assert "Duplicate content" not in item_0_1.toolTip()

        # Check row 1, col 1 (Back) - Should be highlighted
        item_1_1 = dialog.table.item(1, 1)
        assert item_1_1 is not None
        assert "Duplicate content" in item_1_1.toolTip()

    @with_test_collection("two_deck_collection")
    def test_duplicate_deletion(
        self,
        qtbot: QtBot,
        parent_widget: QWidget,
        col: TestCollection,
        dummy_lm_client: DummyLMClient,
        addon_config: AddonConfig,
        user_files_dir: Path,
        is_dark_mode: bool,
    ) -> None:
        """Test that fully duplicate notes are automatically deleted."""
        # 1. Create existing notes
        basic_model = col.models.by_name("Basic")
        deck_id = col.decks.id_for_name("decka")
        assert basic_model is not None
        assert deck_id is not None

        note1 = col.new_note(basic_model)
        note1["Front"] = "Duplicate Front"
        note1["Back"] = "Duplicate Back"
        col.add_note(note1, deck_id)

        # 2. Initialize dialog
        dialog = GenerateNotesDialog(
            parent=parent_widget,
            is_dark_mode=is_dark_mode,
            col=col,
            lm_client=dummy_lm_client,
            addon_config=addon_config,
            user_files_dir=user_files_dir,
            note_ids=[],
        )
        qtbot.addWidget(dialog)
        dialog.deck_combo.setCurrentText("decka")

        # Mock generated notes
        generated_notes = [
            NewNote({"Front": "Duplicate Front", "Back": "Duplicate Back"}, deck_name="decka"),
            NewNote({"Front": "Unique Front", "Back": "Duplicate Back"}, deck_name="decka"),
            NewNote({"Front": "Unique Front 2", "Back": "Unique Back 2"}, deck_name="decka"),
        ]

        # Mock the generator to return notes
        with unittest.mock.patch.object(dialog.notes_generator, "generate") as mock_generate:
            # Mock showInfo to verify notification
            with unittest.mock.patch("transformerman.ui.generate.generate_notes_dialog.showInfo") as mock_show_info:
                # Trigger generation
                def mock_generate_side_effect(
                    parent: QWidget,
                    request: GenerationRequest,
                    on_success: Callable[[Sequence[NewNote], dict[int, list[str]], int], None],
                    on_failure: Callable[[Exception], None],
                    prompt_interceptor: bool = False,
                ) -> None:
                    # Simulate successful generation with duplicates
                    # We need to manually calculate duplicates and ignored count for the mock
                    model_fields = request.note_type.get_fields()
                    all_duplicates = find_duplicates(col, generated_notes, "decka", model_fields)
                    model_fields_set = set(model_fields)
                    filtered_notes: list[NewNote] = []
                    duplicates: dict[int, list[str]] = {}
                    ignored_count = 0

                    for i, note in enumerate(generated_notes):
                        dup_fields = all_duplicates.get(i, [])
                        actual_fields = [k for k in note if k in model_fields_set]
                        if dup_fields and len(dup_fields) == len(actual_fields):
                            ignored_count += 1
                        else:
                            if dup_fields:
                                duplicates[len(filtered_notes)] = dup_fields
                            filtered_notes.append(note)

                    on_success(filtered_notes, duplicates, ignored_count)

                mock_generate.side_effect = mock_generate_side_effect

                dialog.source_text_edit.setPlainText("Some text")
                qtbot.mouseClick(dialog.generate_btn, Qt.MouseButton.LeftButton)

                # Verify showInfo was called for ignored notes
                mock_show_info.assert_called_once()
                assert "Ignored 1 fully duplicate note" in mock_show_info.call_args[0][0]

        # Verify final state
        # Row 0 (Full duplicate) should be gone.
        # Row 1 (Partial) should be at index 0.
        # Row 2 (Unique) should be at index 1.
        assert dialog.table.rowCount() == 2

        # Check content of remaining rows
        item_0_0 = dialog.table.item(0, 0)
        assert item_0_0 is not None
        assert item_0_0.text() == "Unique Front"

        item_1_0 = dialog.table.item(1, 0)
        assert item_1_0 is not None
        assert item_1_0.text() == "Unique Front 2"

        # Check highlighting on partial duplicate (now at row 0)
        # "Back" field (col 1) should be highlighted
        item_0_1 = dialog.table.item(0, 1)
        assert item_0_1 is not None
        assert "Duplicate content" in item_0_1.toolTip()

        # "Front" field (col 0) should NOT be highlighted
        item_0_0 = dialog.table.item(0, 0)
        assert item_0_0 is not None
        assert "Duplicate content" not in item_0_0.toolTip()
