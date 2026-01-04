"""
Tests for prompt_builder module.
"""

from __future__ import annotations

import pytest

from transformerman.lib.prompt_builder import PromptBuilder
from transformerman.lib.selected_notes import NoteModel, SelectedNotes
from transformerman.ui.field_widgets import FieldSelection
from tests.tools import test_collection as test_collection_fixture, with_test_collection, TestCollection

col = test_collection_fixture


class TestPromptBuilder:
    """Test class for PromptBuilder."""

    @with_test_collection("two_deck_collection")
    def test_build_prompt_basic(
        self,
        col: TestCollection,
    ) -> None:
        """Test build_prompt creates basic prompt with notes containing empty fields."""
        # Get two existing note IDs
        note_ids = sorted(col.find_notes(""))[:2]
        # Modify them to have empty Front fields
        model = col.models.by_name("Basic")
        assert model is not None
        for nid in note_ids:
            note = col.get_note(nid)
            note["Front"] = ""  # Empty field
            col.update_note(note)

        selected_notes = SelectedNotes(col, note_ids)
        builder = PromptBuilder(col)

        note_type = NoteModel.by_name(col, "Basic")
        assert note_type

        prompt_with_writeable_fields = builder.get_prompt_renderer(
            target_notes=selected_notes.filter_by_note_type(note_type),
            field_selection=FieldSelection(
                selected=["Front", "Back"],
                writable=["Front"],
                overwritable=[],
            ),
            max_examples=3,
        )(None)

        prompt_with_overwritable_fields = builder.get_prompt_renderer(
            target_notes=selected_notes.filter_by_note_type(note_type),
            field_selection=FieldSelection(
                selected=["Front", "Back"],
                writable=[],
                overwritable=["Front"],
            ),
            max_examples=3,
        )(None)

        def check_prompt(prompt: str):

            assert "You are an Anki note assistant" in prompt
            assert "Please fill" in prompt

            assert prompt.count('<notes model="Basic"') == 2  # example list + target list

            # Check that our modified notes appear in the prompt
            for note_id in note_ids:
                assert f'<note nid="{note_id}"' in prompt

            assert prompt.count('<field name="Front"></field>') == 2  # 2 notes selected and targeted
            assert prompt.count('<field name="Front"') == 5  # 3 example fields + 2 empty fields
            assert prompt.count("</notes>") == 2  # examples + target list
            assert prompt.count("<") == prompt.count(">")  # Basic XML well-formedness

        check_prompt(prompt_with_writeable_fields)
        check_prompt(prompt_with_overwritable_fields)

        col.lock_and_assert_result("test_build_prompt_basic_with_writeable_fields", prompt_with_writeable_fields)
        col.lock_and_assert_result("test_build_prompt_basic_with_overwritable_fields", prompt_with_overwritable_fields)

    @with_test_collection("two_deck_collection")
    def test_build_prompt_with_field_instructions(
        self,
        col: TestCollection,
    ) -> None:
        """Test build_prompt includes field-specific instructions when provided."""
        # Use an existing note and modify it to have empty Front field
        note_ids = sorted(col.find_notes(""))
        assert len(note_ids) >= 1
        note_id = note_ids[0]
        note = col.get_note(note_id)
        note["Front"] = ""  # Empty field
        col.update_note(note)

        selected_notes = SelectedNotes(col, [note_id])
        builder = PromptBuilder(col)

        # Set field instructions
        instructions = {"Front": "Provide a concise question", "Back": "Provide detailed answer"}
        builder.update_field_instructions(instructions)

        note_type = NoteModel.by_name(col, "Basic")
        assert note_type

        # Build prompt
        prompt = builder.get_prompt_renderer(
            target_notes=selected_notes.filter_by_note_type(note_type),
            field_selection=FieldSelection(
                selected=["Front", "Back"],
                writable=["Front"],
                overwritable=[],
            ),
            max_examples=3,
        )(None)

        # Strategic assertions
        assert prompt.count("For field 'Front': Provide a concise question") == 1
        assert prompt.count("For field 'Back': Provide detailed answer") == 0  # Back is not writable
        # Examples should be present from test collection, so exactly 2 <notes> tags
        assert prompt.count('<notes model="Basic"') == 2
        # There should be at least one empty Front field (our target note)
        assert prompt.count('<field name="Front"></field>') >= 1
        # The target note's Back field should be present (with its original content)
        assert f'<field name="Back">{note["Back"]}</field>' in prompt

        col.lock_and_assert_result("test_build_prompt_with_field_instructions", prompt)

    @with_test_collection("two_deck_collection")
    def test_build_prompt_exception_trigger_scenario(
        self,
        col: TestCollection,
    ) -> None:
        """Test if the ValueError exception in build_prompt can be triggered."""

        # Create a scenario where:
        # 1. At least one note has empty writable fields (so precondition passes)
        # 2. But one note has neither empty writable fields nor overwritable fields

        model = col.models.by_name("Basic")
        assert model is not None
        note_ids = sorted(col.find_notes("note:Basic"))
        assert len(note_ids) >= 1

        # Create note 1: has empty writable field (Front)
        note1 = col.get_note(note_ids[0])
        note1["Front"] = ""  # Empty field
        note1["Back"] = "Note 1 back content"
        col.update_note(note1)

        # Create note 2: has neither empty writable fields nor overwritable fields
        note2 = col.get_note(note_ids[1])
        note2["Front"] = "Note 2 front content"  # Not empty
        note2["Back"] = "Note 2 back content"
        col.update_note(note2)

        # Prompt builder
        builder = PromptBuilder(col)
        note_type = NoteModel(col, model)

        # Check with both notes (should be ok, note1 satisfies the precondition)
        prompt = builder.get_prompt_renderer(
            target_notes=SelectedNotes(col, [note1.id, note2.id]).filter_by_note_type(note_type),
            field_selection=FieldSelection(
                selected=["Front", "Back"],
                writable=["Front"],  # Only Front is writable
                overwritable=[],  # No overwritable fields
            ),
            max_examples=2,
        )(None)

        col.lock_and_assert_result("test_build_prompt_exception_trigger_scenario", prompt)

        # Try to build prompt with non-overwritable writable fields that is not empty
        # This should trigger an exception

        with pytest.raises(ValueError, match=f"Target notes does not have any notes with empty writable fields or overwritable fields"):
            builder.get_prompt_renderer(
                target_notes=SelectedNotes(col, [note2.id]).filter_by_note_type(
                    note_type
                ),  # Only note2, meaning there are not valid target notes
                field_selection=FieldSelection(
                    selected=["Front", "Back"],
                    writable=["Front"],
                    overwritable=[],
                ),
                max_examples=2,
            )

    @with_test_collection("two_deck_collection")
    def test_build_prompt_with_examples_section(
        self,
        col: TestCollection,
    ) -> None:
        """Test build_prompt includes examples section when example notes are available."""
        # Use existing notes and modify them
        note_ids = sorted(col.find_notes(""))[:3]  # Get 3 notes

        # Modify first 2 notes to have non-empty Front fields (examples)
        example_note_ids = []
        for i, note_id in enumerate(note_ids[:2]):
            note = col.get_note(note_id)
            note["Front"] = f"Example front {i}"  # Non-empty field
            note["Back"] = f"Example back {i}"
            col.update_note(note)
            example_note_ids.append(note_id)

        # Modify third note to have empty Front field (target)
        target_note_id = note_ids[2]
        target_note = col.get_note(target_note_id)
        target_note["Front"] = ""  # Empty field
        target_note["Back"] = "Target back"
        col.update_note(target_note)

        selected_notes = SelectedNotes(col, [target_note_id])
        builder = PromptBuilder(col)

        note_type = NoteModel.by_name(col, "Basic")
        assert note_type

        # Build prompt
        prompt = builder.get_prompt_renderer(
            target_notes=selected_notes.filter_by_note_type(note_type),
            field_selection=FieldSelection(
                selected=["Front"],
                writable=["Front"],
                overwritable=[],
            ),
            max_examples=10,
        )(None)

        col.lock_and_assert_result("test_build_prompt_with_examples_section", prompt)

        assert prompt.count("Here are some example notes") == 1  # Examples section should be present exactly once
        assert prompt.count('<notes model="Basic"') == 2  # examples + target
        assert f'<note nid="{target_note_id}"' in prompt
        assert prompt.count('<note nid="') == 11  # 10 examples + 1 target

    @with_test_collection("two_deck_collection")
    def test_format_notes_with_mixed_decks(
        self,
        col: TestCollection,
    ) -> None:
        """Test that deck stays on individual notes when notes have different decks."""
        # Get two notes and put them in different decks
        note_ids = col.find_notes("")

        selected_notes = SelectedNotes(col, note_ids)
        builder = PromptBuilder(col)
        note_type = NoteModel.by_name(col, "Basic")
        assert note_type

        prompt = builder.get_prompt_renderer(
            target_notes=selected_notes.filter_by_note_type(note_type),
            field_selection=FieldSelection(selected=["Front"], writable=["Front"], overwritable=["Front"]),
            max_examples=1,
        )(None)

        col.lock_and_assert_result("test_format_notes_with_mixed_decks", prompt)

        assert prompt.count("Here are some example notes") == 0
        assert prompt.count('deck="decka"') == 10
        assert prompt.count('deck="deckb"') == 6
        assert prompt.count('<notes model="Basic">') == 1
