"""
Tests for prompt_builder module.
"""

from __future__ import annotations

from transformerman.lib.prompt_builder import PromptBuilder
from transformerman.lib.selected_notes import SelectedNotes
from tests.tools import test_collection as test_collection_fixture, with_test_collection, MockCollection

col = test_collection_fixture


class TestPromptBuilder:
    """Test class for PromptBuilder."""

    @with_test_collection("two_deck_collection")
    def test_build_prompt_basic(
        self,
        col: MockCollection,
    ) -> None:
        """Test build_prompt creates basic prompt with notes containing empty fields."""
        # Get some real note IDs
        note_ids = col.find_notes("")[:2]
        selected_notes = SelectedNotes(col, note_ids)

        # Create notes with empty fields for testing
        model = col.models.by_name("Basic")
        assert model is not None
        deck = col.decks.all()[0]
        deck_id = deck["id"]

        # Clear existing notes and create test notes
        for nid in note_ids:
            col.remove_notes([nid])

        # Create notes with empty Front field
        test_note_ids = []
        for i in range(2):
            note = col.new_note(model)
            note["Front"] = ""  # Empty field
            note["Back"] = f"Back content {i}"
            col.add_note(note, deck_id)
            test_note_ids.append(note.id)

        selected_notes = SelectedNotes(col, test_note_ids)
        builder = PromptBuilder(col)

        # Build prompt
        prompt = builder.build_prompt(
            target_notes=selected_notes,
            selected_fields=["Front"],
            note_type_name="Basic",
        )

        # Strategic assertions about the prompt structure
        assert "You are an Anki note assistant" in prompt
        assert "Please fill the empty fields" in prompt
        # Examples should be present from test collection, so exactly 2 <notes> tags
        assert prompt.count("<notes model=\"Basic\">") == 2

        # Check that our created notes appear in the prompt
        for note_id in test_note_ids:
            assert f'<note nid="{note_id}"' in prompt

        # Check that empty Front fields are present for our notes
        # (There might be more fields from examples, so we don't count exact number)
        assert "<field name=\"Front\"></field>" in prompt

        # There should be exactly 2 </notes> tags (examples + target)
        assert prompt.count("</notes>") == 2

    @with_test_collection("two_deck_collection")
    def test_build_prompt_with_field_instructions(
        self,
        col: MockCollection,
    ) -> None:
        """Test build_prompt includes field-specific instructions when provided."""
        # Create a note with empty field
        model = col.models.by_name("Basic")
        assert model is not None
        deck = col.decks.all()[0]
        deck_id = deck["id"]

        note = col.new_note(model)
        note["Front"] = ""  # Empty field
        note["Back"] = "Back content"
        col.add_note(note, deck_id)

        selected_notes = SelectedNotes(col, [note.id])
        builder = PromptBuilder(col)

        # Set field instructions
        instructions = {"Front": "Provide a concise question", "Back": "Provide detailed answer"}
        builder.update_field_instructions(instructions)

        # Build prompt
        prompt = builder.build_prompt(
            target_notes=selected_notes,
            selected_fields=["Front", "Back"],
            note_type_name="Basic",
        )

        # Strategic assertions
        assert prompt.count("For field 'Front': Provide a concise question") == 1
        assert prompt.count("For field 'Back': Provide detailed answer") == 1
        # Examples should be present from test collection, so exactly 2 <notes> tags
        assert prompt.count("<notes model=\"Basic\">") == 2
        assert "<field name=\"Front\">" in prompt
        assert "<field name=\"Back\">Back content</field>" in prompt

    @with_test_collection("two_deck_collection")
    def test_build_prompt_without_field_instructions(
        self,
        col: MockCollection,
    ) -> None:
        """Test build_prompt uses default instructions when no field instructions provided."""
        # Create a note with empty field
        model = col.models.by_name("Basic")
        assert model is not None
        deck = col.decks.all()[0]
        deck_id = deck["id"]

        note = col.new_note(model)
        note["Front"] = ""  # Empty field
        note["Back"] = "Back content"
        col.add_note(note, deck_id)

        selected_notes = SelectedNotes(col, [note.id])
        builder = PromptBuilder(col)

        # Don't set any field instructions
        # Build prompt
        prompt = builder.build_prompt(
            target_notes=selected_notes,
            selected_fields=["Front"],
            note_type_name="Basic",
        )

        # Strategic assertions
        assert prompt.count("Fill empty fields intelligently") == 1
        assert "For field 'Front':" not in prompt  # No field-specific instructions
        # Examples should be present from test collection, so exactly 2 <notes> tags
        assert prompt.count("<notes model=\"Basic\">") == 2
        assert "<field name=\"Front\">" in prompt

    @with_test_collection("two_deck_collection")
    def test_build_prompt_includes_deck_name(
        self,
        col: MockCollection,
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
            selected_fields=["Front"],
            note_type_name="Basic",
        )

        # Strategic assertions
        assert prompt.count(f'deck="{deck_name}"') == 1  # Our note should have the deck name exactly once
        # Examples should be present from test collection, so exactly 2 <notes> tags
        assert prompt.count("<notes model=\"Basic\">") == 2
        assert "<field name=\"Front\">" in prompt

    @with_test_collection("two_deck_collection")
    def test_build_prompt_with_examples_section(
        self,
        col: MockCollection,
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
            selected_fields=["Front"],
            note_type_name="Basic",
        )

        # Strategic assertions
        assert prompt.count("Here are some example notes") == 1  # Examples section should be present exactly once
        # Since we created examples, there should be exactly 2 <notes> tags
        assert prompt.count("<notes model=\"Basic\">") == 2
        assert "<field name=\"Front\">" in prompt
        # The prompt should contain the target note
        assert f'<note nid="{target_note.id}"' in prompt
        # The prompt should contain example notes
        for note_id in example_note_ids:
            assert f'<note nid="{note_id}"' in prompt
