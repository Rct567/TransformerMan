"""
Tests for prompt_builder module.
"""

from __future__ import annotations

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

        prompt_with_writeable_fields = builder.build_prompt(
            target_notes=selected_notes,
            field_selection=FieldSelection(
                selected=["Front", "Back"],
                writable=["Front"],
                overwritable=[],
            ),
            note_type=note_type,
            max_examples=3
        )

        prompt_with_overwritable_fields = builder.build_prompt(
            target_notes=selected_notes,
            field_selection=FieldSelection(
                selected=["Front", "Back"],
                writable=[],
                overwritable=["Front"],
            ),
            note_type=note_type,
            max_examples=3,
        )

        def check_prompt(prompt: str):

            assert "You are an Anki note assistant" in prompt
            assert "Please fill" in prompt

            assert prompt.count('<notes model="Basic">') == 2  # example list + target list

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
        prompt = builder.build_prompt(
            target_notes=selected_notes,
            field_selection=FieldSelection(
                selected=["Front", "Back"],
                writable=["Front"],
                overwritable=[],
            ),
            note_type=note_type,
            max_examples=3
        )

        # Strategic assertions
        assert prompt.count("For field 'Front': Provide a concise question") == 1
        assert prompt.count("For field 'Back': Provide detailed answer") == 0  # Back is not writable
        # Examples should be present from test collection, so exactly 2 <notes> tags
        assert prompt.count('<notes model="Basic">') == 2
        # There should be at least one empty Front field (our target note)
        assert prompt.count('<field name="Front"></field>') >= 1
        # The target note's Back field should be present (with its original content)
        assert f'<field name="Back">{note["Back"]}</field>' in prompt

        col.lock_and_assert_result("test_build_prompt_with_field_instructions", prompt)

    @with_test_collection("two_deck_collection")
    def test_build_prompt_includes_deck_name(
        self,
        col: TestCollection,
    ) -> None:
        """Test build_prompt includes deck name in XML output."""
        # Create a note in a specific deck
        model = col.models.by_name("Basic")
        assert model is not None

        # Get or create a deck with known name
        deck_name = "TestDeckForPrompt"
        deck_id = col.decks.id(deck_name)
        assert deck_id is not None  # Ensure deck was created/found

        note = col.new_note(model)
        note["Front"] = ""  # Empty field
        note["Back"] = "Back content"
        col.add_note(note, deck_id)

        selected_notes = SelectedNotes(col, [note.id])
        builder = PromptBuilder(col)

        # Build prompt
        prompt = builder.build_prompt(
            target_notes=selected_notes,
            field_selection=FieldSelection(
                selected=["Front"],
                writable=["Front"],
                overwritable=[],
            ),
            note_type=NoteModel(col, model),
            max_examples=3
        )

        # Strategic assertions
        assert prompt.count(f'deck="{deck_name}"') == 1  # Our note should have the deck name exactly once
        assert prompt.count('<notes model="Basic">') == 2
        assert prompt.count('<field name="Front">') == 4
        assert prompt.count('<field name="Front"></field>') == 1

    @with_test_collection("two_deck_collection")
    def test_build_prompt_with_examples_section(
        self,
        col: TestCollection,
    ) -> None:
        """Test build_prompt includes examples section when example notes are available."""
        model = col.models.by_name("Basic")
        assert model is not None
        deck = col.decks.all()[0]
        deck_id = deck["id"]

        # Clear any existing notes to have a clean state
        existing_note_ids = col.find_notes('"note:Basic"')
        if existing_note_ids:
            col.remove_notes(existing_note_ids)

        # Create example notes (non-empty Front field)
        example_note_ids = []
        for i in range(2):
            note = col.new_note(model)
            note["Front"] = f"Example front {i}"  # Non-empty field
            note["Back"] = f"Example back {i}"
            col.add_note(note, deck_id)
            example_note_ids.append(note.id)

        # Create target note with empty field
        target_note = col.new_note(model)
        target_note["Front"] = ""  # Empty field
        target_note["Back"] = "Target back"
        col.add_note(target_note, deck_id)

        selected_notes = SelectedNotes(col, [target_note.id])
        builder = PromptBuilder(col)

        # Build prompt
        prompt = builder.build_prompt(
            target_notes=selected_notes,
            field_selection=FieldSelection(
                selected=["Front"],
                writable=["Front"],
                overwritable=[],
            ),
            note_type=NoteModel(col, model),
            max_examples=10
        )

        # Strategic assertions
        assert prompt.count("Here are some example notes") == 1  # Examples section should be present exactly once
        # Since we created examples, there should be exactly 2 <notes> tags
        assert prompt.count('<notes model="Basic">') == 2
        assert '<field name="Front">' in prompt
        # The prompt should contain the target note
        assert f'<note nid="{target_note.id}"' in prompt
        # The prompt should contain example notes
        for note_id in example_note_ids:
            assert f'<note nid="{note_id}"' in prompt
