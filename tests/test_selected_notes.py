"""
Tests for selected_notes module.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from anki.notes import NoteId
    from anki.cards import CardId

from anki.models import NotetypeId

from transformerman.lib.selected_notes import SelectedNotes, NoteModel
from transformerman.lib.prompt_builder import PromptBuilder
from tests.tools import test_collection as test_collection_fixture, with_test_collection, TestCollection

col = test_collection_fixture


class TestSelectedNotes:
    """Test class for SelectedNotes."""

    @with_test_collection("two_deck_collection")
    def test_basic_initialization_and_properties(
        self,
        col: TestCollection,
    ) -> None:
        """Test __init__, get_ids, get_note caching, and __len__."""
        # Get some real note IDs from the collection
        note_ids = col.find_notes("")[:3]  # First 3 notes
        assert len(note_ids) >= 3, "Need at least 3 notes for testing"

        # Create SelectedNotes instance
        selected_notes = SelectedNotes(col, note_ids)

        # Test get_ids returns the same IDs
        assert list(selected_notes.get_ids()) == list(note_ids)

        # Test __len__
        assert len(selected_notes) == len(note_ids)

        # Test get_note with caching
        note1 = selected_notes.get_note(note_ids[0])
        note2 = selected_notes.get_note(note_ids[0])  # Same note, should come from cache
        assert note1 is note2  # Should be same object due to caching

        # Test get_note with different note
        note3 = selected_notes.get_note(note_ids[1])
        assert note3 is not note1  # Different note object

    @with_test_collection("two_deck_collection")
    def test_filter_by_note_type(
        self,
        col: TestCollection,
    ) -> None:
        """Test filter_by_note_type returns only notes of specified type."""
        # Get all note IDs
        all_note_ids = col.find_notes("")
        selected_notes = SelectedNotes(col, all_note_ids)

        # Filter by "Basic" note type (should exist in test collection)
        basic_note_ids = selected_notes.filter_by_note_type("Basic")
        assert basic_note_ids

        # Verify all filtered notes are actually "Basic" type
        for nid in basic_note_ids:
            note = selected_notes.get_note(nid)
            notetype = col.models.get(note.mid)
            assert notetype is not None
            assert notetype['name'] == "Basic"

        # Filter by non-existent note type
        non_existent_note_ids = selected_notes.filter_by_note_type("NonExistentType")
        assert len(non_existent_note_ids) == 0

    @with_test_collection("two_deck_collection")
    def test_get_note_type_counts(
        self,
        col: TestCollection,
    ) -> None:
        """Test get_note_type_counts returns correct counts sorted descending."""
        # Create notes of different types
        basic_model = col.models.by_name("Basic")
        cloze_model = col.models.by_name("Cloze")
        assert basic_model is not None
        assert cloze_model is not None

        deck = col.decks.all()[0]
        deck_id = deck["id"]

        # Add some Basic notes
        basic_note_ids = []
        for _ in range(3):
            note = col.new_note(basic_model)
            note["Front"] = "Front"
            note["Back"] = "Back"
            col.add_note(note, deck_id)
            basic_note_ids.append(note.id)

        # Add some Cloze notes
        cloze_note_ids = []
        for _ in range(2):
            note = col.new_note(cloze_model)
            note["Text"] = "Text {{c1::cloze}}"
            col.add_note(note, deck_id)
            cloze_note_ids.append(note.id)

        # Combine all note IDs
        all_note_ids = list(basic_note_ids) + list(cloze_note_ids)
        selected_notes = SelectedNotes(col, all_note_ids)

        # Get counts
        counts = selected_notes.get_note_type_counts()

        # Verify counts are correct and sorted descending
        assert "Basic" in counts
        assert "Cloze" in counts
        assert counts["Basic"] == 3  # 3 Basic notes
        assert counts["Cloze"] == 2  # 2 Cloze notes

        # Verify sorting (Basic should come first since count 3 > 2)
        counts_list = list(counts.items())
        assert counts_list[0][0] == "Basic"
        assert counts_list[0][1] == 3
        assert counts_list[1][0] == "Cloze"
        assert counts_list[1][1] == 2

    @with_test_collection("two_deck_collection")
    def test_has_empty_field_static(
        self,
        col: TestCollection,
    ) -> None:
        """Test static method has_empty_field with various field states."""
        model = col.models.by_name("Basic")
        assert model is not None
        deck = col.decks.all()[0]
        deck_id = deck["id"]

        # Create note with empty field
        note1 = col.new_note(model)
        note1["Front"] = ""  # Empty
        note1["Back"] = "Not empty"
        col.add_note(note1, deck_id)

        # Create note with no empty fields
        note2 = col.new_note(model)
        note2["Front"] = "Not empty"
        note2["Back"] = "Also not empty"
        col.add_note(note2, deck_id)

        # Test with selected_fields containing empty field
        assert SelectedNotes.has_empty_field(note1, ["Front"]) is True
        assert SelectedNotes.has_empty_field(note1, ["Back"]) is False
        assert SelectedNotes.has_empty_field(note1, ["Front", "Back"]) is True

        # Test with note that has no empty fields
        assert SelectedNotes.has_empty_field(note2, ["Front"]) is False
        assert SelectedNotes.has_empty_field(note2, ["Front", "Back"]) is False

        # Test with field that doesn't exist (should not crash)
        assert SelectedNotes.has_empty_field(note1, ["NonExistentField"]) is False

    @with_test_collection("two_deck_collection")
    def test_has_note_with_empty_field(
        self,
        col: TestCollection,
    ) -> None:
        """Test has_note_with_empty_field returns True/False appropriately."""
        model = col.models.by_name("Basic")
        assert model is not None
        deck = col.decks.all()[0]
        deck_id = deck["id"]

        # Create notes: one with empty field, one without
        note1 = col.new_note(model)
        note1["Front"] = ""  # Empty
        note1["Back"] = "Not empty"
        col.add_note(note1, deck_id)

        note2 = col.new_note(model)
        note2["Front"] = "Not empty"
        note2["Back"] = "Also not empty"
        col.add_note(note2, deck_id)

        # Test with only note that has empty field
        selected_notes1 = SelectedNotes(col, [note1.id])
        assert selected_notes1.has_note_with_empty_field(["Front"]) is True
        assert selected_notes1.has_note_with_empty_field(["Back"]) is False

        # Test with only note that has no empty fields
        selected_notes2 = SelectedNotes(col, [note2.id])
        assert selected_notes2.has_note_with_empty_field(["Front"]) is False
        assert selected_notes2.has_note_with_empty_field(["Front", "Back"]) is False

        # Test with mixed notes
        selected_notes3 = SelectedNotes(col, [note1.id, note2.id])
        assert selected_notes3.has_note_with_empty_field(["Front"]) is True
        assert selected_notes3.has_note_with_empty_field(["Back"]) is False

    @with_test_collection("two_deck_collection")
    def test_filter_by_empty_field(
        self,
        col: TestCollection,
    ) -> None:
        """Test filter_by_empty_field returns only notes with empty fields."""
        model = col.models.by_name("Basic")
        assert model is not None
        deck = col.decks.all()[0]
        deck_id = deck["id"]

        # Create notes with mixed empty/non-empty fields
        note_ids = []
        for i in range(4):
            note = col.new_note(model)
            if i < 2:
                note["Front"] = ""  # Empty
            else:
                note["Front"] = "Filled"
            note["Back"] = f"Back {i}"
            col.add_note(note, deck_id)
            note_ids.append(note.id)

        selected_notes = SelectedNotes(col, note_ids)

        # Filter by empty "Front" field
        filtered = selected_notes.filter_by_empty_field(["Front"])

        # Should have 2 notes (first two have empty Front)
        assert len(filtered) == 2
        filtered_ids = list(filtered.get_ids())
        assert note_ids[0] in filtered_ids
        assert note_ids[1] in filtered_ids
        assert note_ids[2] not in filtered_ids
        assert note_ids[3] not in filtered_ids

        # Filter by "Back" field (all are non-empty)
        filtered2 = selected_notes.filter_by_empty_field(["Back"])
        assert len(filtered2) == 0

    @with_test_collection("two_deck_collection")
    def test_batched_by_prompt_size_empty_selection(
        self,
        col: TestCollection,
    ) -> None:
        """Test batched_by_prompt_size with empty note IDs."""
        selected_notes = SelectedNotes(col, [])
        prompt_builder = PromptBuilder(col)

        batches = selected_notes.batched_by_prompt_size(
            prompt_builder=prompt_builder,
            selected_fields=["Front"],
            writable_fields=["Front"],
            overwritable_fields=None,
            note_type_name="Basic",
            max_chars=1000,
        )

        assert batches == []

    @with_test_collection("two_deck_collection")
    def test_batched_by_prompt_size_no_empty_fields(
        self,
        col: TestCollection,
    ) -> None:
        """Test batched_by_prompt_size when no notes have empty fields."""
        model = col.models.by_name("Basic")
        assert model is not None
        deck = col.decks.all()[0]
        deck_id = deck["id"]

        # Create notes with no empty fields
        note_ids = []
        for i in range(3):
            note = col.new_note(model)
            note["Front"] = f"Front {i}"  # Not empty
            note["Back"] = f"Back {i}"
            col.add_note(note, deck_id)
            note_ids.append(note.id)

        selected_notes = SelectedNotes(col, note_ids)
        prompt_builder = PromptBuilder(col)

        batches = selected_notes.batched_by_prompt_size(
            prompt_builder=prompt_builder,
            selected_fields=["Front"],  # All notes have non-empty Front
            writable_fields=["Front"],
            overwritable_fields=None,
            note_type_name="Basic",
            max_chars=1000,
        )

        assert batches == []

    @with_test_collection("two_deck_collection")
    def test_batched_by_prompt_size_single_batch(
        self,
        col: TestCollection,
    ) -> None:
        """Test batched_by_prompt_size when all notes fit in one batch."""
        model = col.models.by_name("Basic")
        assert model is not None
        deck = col.decks.all()[0]
        deck_id = deck["id"]

        # Create notes with empty fields
        note_ids = []
        for i in range(3):
            note = col.new_note(model)
            note["Front"] = ""  # Empty field
            note["Back"] = f"Back {i}"
            col.add_note(note, deck_id)
            note_ids.append(note.id)

        selected_notes = SelectedNotes(col, note_ids)
        prompt_builder = PromptBuilder(col)

        # Use large max_chars to ensure single batch
        batches = selected_notes.batched_by_prompt_size(
            prompt_builder=prompt_builder,
            selected_fields=["Front"],
            writable_fields=["Front"],
            overwritable_fields=None,
            note_type_name="Basic",
            max_chars=500000,  # Very large
        )

        # Should be one batch with all 3 notes
        assert len(batches) == 1
        batch = batches[0]
        assert len(batch) == 3
        assert set(batch.get_ids()) == set(note_ids)

    @with_test_collection("two_deck_collection")
    def test_batched_by_prompt_size_multiple_batches(
        self,
        col: TestCollection,
    ) -> None:
        """Test batched_by_prompt_size when notes require multiple batches."""
        model = col.models.by_name("Basic")
        assert model is not None
        deck = col.decks.all()[0]
        deck_id = deck["id"]

        # Create many notes with empty fields
        note_ids = []
        for i in range(10):
            note = col.new_note(model)
            note["Front"] = ""  # Empty field
            # Add minimal content to Back - just enough to create prompts
            note["Back"] = f"Back {i}"
            col.add_note(note, deck_id)
            note_ids.append(note.id)

        selected_notes = SelectedNotes(col, note_ids)
        prompt_builder = PromptBuilder(col, max_examples=3)

        # Use small max_chars to force multiple batches
        # Need to find a value that allows some notes but not all
        # Let's try with a moderate size
        batches = selected_notes.batched_by_prompt_size(
            prompt_builder=prompt_builder,
            selected_fields=["Front"],
            writable_fields=["Front"],
            overwritable_fields=None,
            note_type_name="Basic",
            max_chars=1000,  # Moderate size to get multiple batches
        )

        # Should have multiple batches (unless all fit in one)
        # At least some batches should be created
        assert len(batches) >= 1

        # If we have only one batch, all notes should be in it
        if len(batches) == 1:
            assert len(batches[0]) == 10
        else:
            # Multiple batches - verify properties
            total_notes_in_batches = sum(len(batch) for batch in batches)
            assert total_notes_in_batches <= 10  # Some might be skipped if single note exceeds limit

            # Verify no note appears in multiple batches
            all_batch_note_ids: list[int] = []
            for batch in batches:
                all_batch_note_ids.extend(batch.get_ids())
            assert len(all_batch_note_ids) == len(set(all_batch_note_ids))

    @with_test_collection("two_deck_collection")
    def test_batched_by_prompt_size_single_note_exceeds_limit(
        self,
        col: TestCollection,
    ) -> None:
        """Test batched_by_prompt_size when single note exceeds max size."""
        model = col.models.by_name("Basic")
        assert model is not None
        deck = col.decks.all()[0]
        deck_id = deck["id"]

        # Create a note with empty field
        note = col.new_note(model)
        note["Front"] = ""  # Empty field
        # Add lots of content to Back to make prompt large
        note["Back"] = "Very large content " * 1000
        col.add_note(note, deck_id)

        selected_notes = SelectedNotes(col, [note.id])
        prompt_builder = PromptBuilder(col, max_examples=3)

        # Use tiny max_chars so even single note exceeds limit
        batches = selected_notes.batched_by_prompt_size(
            prompt_builder=prompt_builder,
            selected_fields=["Front"],
            writable_fields=["Front"],
            overwritable_fields=None,
            note_type_name="Basic",
            max_chars=10,  # Extremely small
        )
        batches_increased_max_chars = selected_notes.batched_by_prompt_size(
            prompt_builder=prompt_builder,
            selected_fields=["Front"],
            writable_fields=["Front"],
            overwritable_fields=None,
            note_type_name="Basic",
            max_chars=1000,  # Increased to allow the note (prompt size is 842)
        )
        batches_increased_max_chars_with_large_field = selected_notes.batched_by_prompt_size(
            prompt_builder=prompt_builder,
            selected_fields=["Front", "Back"],
            writable_fields=["Front", "Back"],
            overwritable_fields=None,
            note_type_name="Basic",
            max_chars=1000,  # Increased to allow the note (prompt size is 842)
        )


        # Should be empty (note skipped with warning logged)
        assert batches == []
        assert len(batches_increased_max_chars) == 1  # Now should pass with max_chars=1000
        assert batches_increased_max_chars_with_large_field == []  # Now should fail with max_chars=1000

    @with_test_collection("two_deck_collection")
    def test_get_notes(
        self,
        col: TestCollection,
    ) -> None:
        """Test get_notes returns correct Note objects."""
        # Get some real note IDs
        note_ids = col.find_notes("")[:3]
        selected_notes = SelectedNotes(col, note_ids)

        # Get notes with default (all notes)
        notes = selected_notes.get_notes()
        assert len(notes) == len(note_ids)
        for i, note in enumerate(notes):
            assert note.id == note_ids[i]

        # Get notes with specific subset
        subset_ids = note_ids[:2]
        subset_notes = selected_notes.get_notes(subset_ids)
        assert len(subset_notes) == 2
        for i, note in enumerate(subset_notes):
            assert note.id == subset_ids[i]

    @with_test_collection("two_deck_collection")
    def test_new_selected_notes(
        self,
        col: TestCollection,
    ) -> None:
        """Test new_selected_notes creates new instance with shared cache."""
        # Get some note IDs
        all_note_ids = col.find_notes("")[:4]
        selected_notes = SelectedNotes(col, all_note_ids)

        # Create new instance with subset
        subset_ids = all_note_ids[:2]
        new_selected_notes = selected_notes.new_selected_notes(subset_ids)

        # Verify new instance has correct IDs
        assert list(new_selected_notes.get_ids()) == list(subset_ids)

        # Test 1: Parent gets note first, then child gets same note
        note_id = subset_ids[0]
        note_from_parent = selected_notes.get_note(note_id)
        note_from_child = new_selected_notes.get_note(note_id)
        # They should represent the same note (same ID, same fields)
        assert note_from_parent.id == note_from_child.id
        # Check a field to ensure they're the same note
        # (can't use 'is' because Anki might create new wrapper objects)

        # Test 2: Child gets note first, then parent gets same note
        note_id2 = subset_ids[1]
        note_from_child2 = new_selected_notes.get_note(note_id2)
        note_from_parent2 = selected_notes.get_note(note_id2)
        assert note_from_child2.id == note_from_parent2.id

    @with_test_collection("two_deck_collection")
    def test_note_model(
        self,
        col: TestCollection,
    ) -> None:
        """Test NoteModel class."""
        # Test by_name
        model = NoteModel.by_name(col, "Basic")
        assert model is not None
        assert model.name == "Basic"
        assert "Front" in model.get_fields()
        assert "Back" in model.get_fields()

        # Test by_id
        model_by_id = NoteModel.by_id(col, model.id)
        assert model_by_id is not None
        assert model_by_id.id == model.id
        assert model_by_id.name == "Basic"

        # Test non-existent
        assert NoteModel.by_name(col, "NonExistent") is None
        assert NoteModel.by_id(col, NotetypeId(999999)) is None

    @with_test_collection("two_deck_collection")
    def test_note_cache_sharing(
        self,
        col: TestCollection,
    ) -> None:
        """Test that cache is shared between parent and child SelectedNotes instances."""
        # Get some note IDs
        all_note_ids = col.find_notes("")[:3]
        parent_notes = SelectedNotes(col, all_note_ids)

        # Get a note from parent to populate cache
        note_from_parent = parent_notes.get_note(all_note_ids[0])

        # Create child with subset
        child_note_ids = all_note_ids[:2]
        child_notes = parent_notes.new_selected_notes(child_note_ids)

        # Child should get the same note (same ID)
        note_from_child = child_notes.get_note(all_note_ids[0])
        assert note_from_parent.id == note_from_child.id

        # Child getting new note should mean parent can get it from cache
        note_from_child2 = child_notes.get_note(all_note_ids[1])
        note_from_parent2 = parent_notes.get_note(all_note_ids[1])
        assert note_from_child2.id == note_from_parent2.id

    @with_test_collection("two_deck_collection")
    def test_empty_field_detection_with_multiple_fields(
        self,
        col: TestCollection,
    ) -> None:
        """Test empty field detection with multiple selected fields."""
        model = col.models.by_name("Basic")
        assert model is not None
        deck = col.decks.all()[0]
        deck_id = deck["id"]

        # Create notes with various empty field combinations
        note1 = col.new_note(model)
        note1["Front"] = ""  # Empty
        note1["Back"] = ""   # Empty
        col.add_note(note1, deck_id)

        note2 = col.new_note(model)
        note2["Front"] = "Filled"
        note2["Back"] = ""   # Empty
        col.add_note(note2, deck_id)

        note3 = col.new_note(model)
        note3["Front"] = ""  # Empty
        note3["Back"] = "Filled"
        col.add_note(note3, deck_id)

        note4 = col.new_note(model)
        note4["Front"] = "Filled"
        note4["Back"] = "Filled"
        col.add_note(note4, deck_id)

        selected_notes = SelectedNotes(col, [note1.id, note2.id, note3.id, note4.id])

        # Test has_note_with_empty_field with different field combinations
        assert selected_notes.has_note_with_empty_field(["Front"]) is True
        assert selected_notes.has_note_with_empty_field(["Back"]) is True
        assert selected_notes.has_note_with_empty_field(["Front", "Back"]) is True

        # Test filter_by_empty_field
        filtered_front = selected_notes.filter_by_empty_field(["Front"])
        assert len(filtered_front) == 2  # note1 and note3
        filtered_ids = list(filtered_front.get_ids())
        assert note1.id in filtered_ids
        assert note3.id in filtered_ids

        filtered_back = selected_notes.filter_by_empty_field(["Back"])
        assert len(filtered_back) == 2  # note1 and note2

        filtered_both = selected_notes.filter_by_empty_field(["Front", "Back"])
        assert len(filtered_both) == 3  # note1, note2, note3 (all except note4)

    @with_test_collection("empty_collection")
    def test_get_most_common_deck_multiple_decks(
        self,
        col: TestCollection,
    ) -> None:
        """Test get_most_common_deck returns correct deck name."""
        # Create decks
        deck1_id = col.decks.id("Deck1")
        deck2_id = col.decks.id("Deck2")
        deck3_id = col.decks.id("Parent::Child")
        assert deck1_id is not None
        assert deck2_id is not None
        assert deck3_id is not None

        # Create notes in different decks
        model = col.models.by_name("Basic")
        assert model is not None

        note_ids: list[NoteId] = []
        card_ids: list[CardId] = []

        # Add 3 notes to Deck1
        for _ in range(3):
            note = col.new_note(model)
            note["Front"] = "Front"
            note["Back"] = "Back"
            col.add_note(note, deck1_id)
            note_ids.append(note.id)
            card_ids.extend(note.card_ids())

        # Add 2 notes to Deck2
        for _ in range(2):
            note = col.new_note(model)
            note["Front"] = "Front"
            note["Back"] = "Back"
            col.add_note(note, deck2_id)
            note_ids.append(note.id)
            card_ids.extend(note.card_ids())

        # Add 4 notes to Parent::Child (most common)
        for _ in range(4):
            note = col.new_note(model)
            note["Front"] = "Front"
            note["Back"] = "Back"
            col.add_note(note, deck3_id)
            note_ids.append(note.id)
            card_ids.extend(note.card_ids())

        # Test with card IDs (preferred)
        selected_notes_with_cards = SelectedNotes(col, note_ids, card_ids=card_ids)
        most_common_deck = selected_notes_with_cards.get_most_common_deck()
        assert most_common_deck == "Parent::Child"

        # Test with note IDs only (no card IDs)
        selected_notes_without_cards = SelectedNotes(col, note_ids, card_ids=None)
        most_common_deck2 = selected_notes_without_cards.get_most_common_deck()
        assert most_common_deck2 == "Parent::Child"

        # Test with empty selection
        selected_notes_empty = SelectedNotes(col, [], card_ids=[])
        assert selected_notes_empty.get_most_common_deck() == ""

        # Test with single deck
        single_deck_note_ids = note_ids[:1]
        single_deck_card_ids = card_ids[:1]
        selected_notes_single = SelectedNotes(col, single_deck_note_ids, card_ids=single_deck_card_ids)
        deck_name = selected_notes_single.get_most_common_deck()
        assert deck_name == "Deck1"

