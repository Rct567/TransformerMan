"""
Tests for selected_notes module.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from anki.notes import NoteId
    from anki.cards import CardId

from anki.models import NotetypeId

from transformerman.lib.selected_notes import SelectedNotes, NoteModel, SelectedNotesFromType, SelectedNotesBatch
from transformerman.ui.field_widgets import FieldSelection
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
        note_type = NoteModel.by_name(col, "Basic")
        assert note_type

        # Filter by "Basic" note type (should exist in test collection)
        basic_note_ids = selected_notes.filter_by_note_type(note_type).get_ids()
        assert basic_note_ids

        # Verify all filtered notes are actually "Basic" type
        for nid in basic_note_ids:
            note = selected_notes.get_note(nid)
            notetype = col.models.get(note.mid)
            assert notetype is not None
            assert notetype["name"] == "Basic"

        # Filter by non-existent note type
        non_existing_note_type = NoteModel.by_name(col, "Basic (type in the answer)")
        assert non_existing_note_type is not None
        non_existent_note_ids = selected_notes.filter_by_note_type(non_existing_note_type)
        assert len(non_existent_note_ids) == 0

    @with_test_collection("empty_collection")
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

        deck_id = col.decks.id_for_name("Default")
        assert deck_id

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

    @with_test_collection("empty_collection")
    def test_has_empty_field_static(
        self,
        col: TestCollection,
    ) -> None:
        """Test static method has_empty_field with various field states."""
        model = col.models.by_name("Basic")
        assert model is not None

        deck_id = col.decks.id_for_name("Default")
        assert deck_id

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

    @with_test_collection("empty_collection")
    def test_has_note_with_empty_field(
        self,
        col: TestCollection,
    ) -> None:
        """Test has_note_with_empty_field returns True/False appropriately."""
        model = col.models.by_name("Basic")
        assert model is not None
        deck_id = col.decks.id_for_name("Default")
        assert deck_id

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

    @with_test_collection("empty_collection")
    def test_filter_by_empty_field(
        self,
        col: TestCollection,
    ) -> None:
        """Test filter_by_empty_field returns only notes with empty fields."""
        model = col.models.by_name("Basic")
        assert model is not None
        deck_id = col.decks.id_for_name("Default")
        assert deck_id

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

    @with_test_collection("empty_collection")
    def test_batched_by_prompt_size_empty_selection(
        self,
        col: TestCollection,
    ) -> None:
        """Test batched_by_prompt_size with empty note IDs."""
        selected_notes = SelectedNotes(col, [])
        prompt_builder = PromptBuilder(col)
        note_type = NoteModel.by_name(col, "Basic")
        assert note_type

        batches = selected_notes.filter_by_note_type(note_type).batched_by_prompt_size(
            prompt_builder=prompt_builder,
            field_selection=FieldSelection(
                selected=["Front"],
                writable=["Front"],
                overwritable=[],
            ),
            max_chars=1000,
            max_examples=10,
        )

        assert batches == []

    @with_test_collection("empty_collection")
    def test_batched_by_prompt_size_no_empty_fields(
        self,
        col: TestCollection,
    ) -> None:
        """Test batched_by_prompt_size when no notes have empty fields."""
        model = col.models.by_name("Basic")
        assert model is not None
        deck_id = col.decks.id_for_name("Default")
        assert deck_id

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

        batches = selected_notes.filter_by_note_type(NoteModel(col, model)).batched_by_prompt_size(
            prompt_builder=prompt_builder,
            field_selection=FieldSelection(
                selected=["Front"],
                writable=["Front"],
                overwritable=[],
            ),
            max_chars=1000,
            max_examples=10,
        )

        assert batches == []

    @with_test_collection("empty_collection")
    def test_batched_by_prompt_size_single_batch(
        self,
        col: TestCollection,
    ) -> None:
        """Test batched_by_prompt_size when all notes fit in one batch."""
        model = col.models.by_name("Basic")
        assert model is not None
        deck_id = col.decks.id_for_name("Default")
        assert deck_id

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
        batches = selected_notes.filter_by_note_type(NoteModel(col, model)).batched_by_prompt_size(
            prompt_builder=prompt_builder,
            field_selection=FieldSelection(
                selected=["Front"],
                writable=["Front"],
                overwritable=[],
            ),
            max_chars=500000,  # Very large
            max_examples=10,
        )

        # Should be one batch with all 3 notes
        assert len(batches) == 1
        batch = batches[0]
        assert len(batch) == 3
        assert set(batch.get_ids()) == set(note_ids)

    @with_test_collection("empty_collection")
    def test_batched_by_prompt_size_multiple_batches(
        self,
        col: TestCollection,
    ) -> None:
        """Test batched_by_prompt_size when notes require multiple batches."""
        model = col.models.by_name("Basic")
        assert model is not None
        deck_id = col.decks.id_for_name("Default")
        assert deck_id

        # Create many notes with empty fields
        note_ids = []
        for i in range(100):
            note = col.new_note(model)
            note["Front"] = ""  # Empty field
            # Add minimal content to Back - just enough to create prompts
            note["Back"] = f"Back {i}"
            col.add_note(note, deck_id)
            note_ids.append(note.id)

        selected_notes = SelectedNotes(col, note_ids)
        prompt_builder = PromptBuilder(col)

        # Test with different max_chars to ensure multiple batches are created

        test_cases = [
            (20_000, 1, 1),  # (max_chars, min_expected_batches, max_expected_batches)
            (9_500, 2, 2),
            (4_900, 4, 5),
            (2_500, 13, 18),
        ]

        num_prompts_tried = []
        for max_chars, min_batches, max_batches in test_cases:
            selected_notes_from_note = selected_notes.filter_by_note_type(NoteModel(col, model))
            batches = selected_notes_from_note.batched_by_prompt_size(
                prompt_builder=prompt_builder,
                field_selection=FieldSelection(
                    selected=["Front", "Back"],
                    writable=["Front"],
                    overwritable=[],
                ),
                max_chars=max_chars,
                max_examples=10,
            )

            # Verify batch count is reasonable
            assert min_batches <= len(batches) <= max_batches, (
                f"Expected {min_batches}-{max_batches} batches for max_chars={max_chars}, got {len(batches)}"
            )

            # Verify all notes are included
            total_notes_in_batches = sum(len(batch) for batch in batches)
            assert total_notes_in_batches == 100

            # Verify each batch fits within max_chars (sample a few)
            for i, batch in enumerate(batches[:3]):  # Check first 3 batches
                # Build prompt for this batch
                prompt = prompt_builder.get_prompt_renderer(
                    target_notes=batch.filter_by_note_type(NoteModel(col, model)),
                    field_selection=FieldSelection(
                        selected=["Front", "Back"],
                        writable=["Front"],
                        overwritable=[],
                    ),
                    max_examples=10,
                )(None)
                assert len(prompt) <= max_chars, f"Batch {i} exceeds max_chars ({len(prompt)} > {max_chars})"

            assert selected_notes_from_note.batching_stats
            assert selected_notes_from_note.batching_stats.num_prompts_tried <= 50

            num_prompts_tried.append(selected_notes_from_note.batching_stats.num_prompts_tried)

            # Verify no note appears in multiple batches
            all_batch_note_ids: list[int] = []
            for batch in batches:
                all_batch_note_ids.extend(batch.get_ids())
            assert len(all_batch_note_ids) == len(set(all_batch_note_ids))

        assert num_prompts_tried[0] <= 2
        assert num_prompts_tried[1] <= 7
        assert num_prompts_tried[2] <= 21
        assert num_prompts_tried[3] <= 81

    @with_test_collection("empty_collection")
    def test_batched_by_prompt_size_respects_max_notes_per_batch(
        self,
        col: TestCollection,
    ) -> None:
        """Test that batched_by_prompt_size respects the max_notes_per_batch limit."""
        model = col.models.by_name("Basic")
        assert model is not None
        deck_id = col.decks.id_for_name("Default")
        assert deck_id

        # Create 10 notes
        note_ids = []
        for i in range(10):
            note = col.new_note(model)
            note["Front"] = ""
            note["Back"] = f"Back {i}"
            col.add_note(note, deck_id)
            note_ids.append(note.id)

        selected_notes = SelectedNotes(col, note_ids)
        prompt_builder = PromptBuilder(col)
        note_type = NoteModel(col, model)

        # Set max_notes_per_batch to 2
        max_notes = 2
        batches = selected_notes.filter_by_note_type(note_type).batched_by_prompt_size(
            prompt_builder=prompt_builder,
            field_selection=FieldSelection(
                selected=["Front"],
                writable=["Front"],
                overwritable=[],
            ),
            max_chars=500000,  # Large enough to fit all notes
            max_examples=10,
            max_notes_per_batch=max_notes,
        )

        # Verify each batch has at most 2 notes
        assert len(batches) == 5
        for batch in batches:
            assert len(batch) <= max_notes

    @with_test_collection("empty_collection")
    def test_batched_by_prompt_size_single_note_exceeds_limit(
        self,
        col: TestCollection,
    ) -> None:
        """Test batched_by_prompt_size when single note exceeds max size."""
        model = col.models.by_name("Basic")
        assert model is not None
        deck_id = col.decks.id_for_name("Default")
        assert deck_id

        # Create a note with empty field
        note = col.new_note(model)
        note["Front"] = ""  # Empty field
        # Add lots of content to Back to make prompt large
        note["Back"] = "Very large content " * 1000
        col.add_note(note, deck_id)

        selected_notes = SelectedNotes(col, [note.id])
        prompt_builder = PromptBuilder(col)

        # Use tiny max_chars so even single note exceeds limit
        batches = selected_notes.filter_by_note_type(NoteModel(col, model)).batched_by_prompt_size(
            prompt_builder=prompt_builder,
            field_selection=FieldSelection(
                selected=["Front"],
                writable=["Front"],
                overwritable=[],
            ),
            max_chars=10,  # Extremely small
            max_examples=3,
        )
        batches_increased_max_chars = selected_notes.filter_by_note_type(NoteModel(col, model)).batched_by_prompt_size(
            prompt_builder=prompt_builder,
            field_selection=FieldSelection(
                selected=["Front"],
                writable=["Front"],
                overwritable=[],
            ),
            max_chars=1000,  # Increased to allow the note (prompt size is 842)
            max_examples=3,
        )
        batches_increased_max_chars_with_large_field = selected_notes.filter_by_note_type(NoteModel(col, model)).batched_by_prompt_size(
            prompt_builder=prompt_builder,
            field_selection=FieldSelection(
                selected=["Front", "Back"],
                writable=["Front", "Back"],
                overwritable=[],
            ),
            max_chars=1000,  # Increased to allow the note (prompt size is 842)
            max_examples=3,
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
        note_ids = col.find_notes("")
        selected_notes = SelectedNotes(col, note_ids)
        assert len(selected_notes) == len(note_ids) == 16

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

    @with_test_collection("empty_collection")
    def test_empty_field_detection_with_multiple_fields(
        self,
        col: TestCollection,
    ) -> None:
        """Test empty field detection with multiple selected fields."""
        model = col.models.by_name("Basic")
        assert model is not None
        deck_id = col.decks.id_for_name("Default")
        assert deck_id

        # Create notes with various empty field combinations
        note1 = col.new_note(model)
        note1["Front"] = ""  # Empty
        note1["Back"] = ""  # Empty
        col.add_note(note1, deck_id)

        note2 = col.new_note(model)
        note2["Front"] = "Filled"
        note2["Back"] = ""  # Empty
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

    @with_test_collection("empty_collection")
    def test_new_selected_notes_card_ids(
        self,
        col: TestCollection,
    ) -> None:
        """Test new_selected_notes correctly filters and passes card_ids."""
        # Create deck and model
        deck_id = col.decks.id("TestDeck")
        assert deck_id is not None
        model = col.models.by_name("Basic")
        assert model is not None

        # Create notes with their card IDs
        note_ids: list[NoteId] = []
        card_ids: list[CardId] = []

        for i in range(5):
            note = col.new_note(model)
            note["Front"] = f"Front {i}"
            note["Back"] = f"Back {i}"
            col.add_note(note, deck_id)
            note_ids.append(note.id)
            card_ids.extend(note.card_ids())

        # Create SelectedNotes with both note_ids and card_ids
        selected_notes = SelectedNotes(col, note_ids, card_ids=card_ids)

        # Test filtering to subset of notes (first 3)
        subset_note_ids = note_ids[:3]
        filtered_notes = selected_notes.new_selected_notes(subset_note_ids)

        # Verify the filtered instance has correct note IDs
        assert set(filtered_notes.get_ids()) == set(subset_note_ids)

        # Verify the filtered instance has correct card IDs
        # Get expected card IDs for the subset
        expected_card_ids: list[CardId] = []
        for note_id in subset_note_ids:
            note = col.get_note(note_id)
            expected_card_ids.extend(note.card_ids())

        # The filtered instance should have these card IDs
        filtered_card_ids = filtered_notes.get_selected_card_ids()
        assert filtered_card_ids is not None
        assert set(filtered_card_ids) == set(expected_card_ids)

        # Test with empty subset
        empty_filtered = selected_notes.new_selected_notes([])
        assert len(empty_filtered) == 0
        assert empty_filtered.get_selected_card_ids() is None  # Empty list becomes None in constructor

        # Test with original instance that has no card_ids (None)
        selected_notes_no_cards = SelectedNotes(col, note_ids, card_ids=None)
        filtered_no_cards = selected_notes_no_cards.new_selected_notes(subset_note_ids)
        assert set(filtered_no_cards.get_ids()) == set(subset_note_ids)
        assert filtered_no_cards.get_selected_card_ids() is None  # Should remain None when original has None

    @with_test_collection("empty_collection")
    def test_card_ids_filtered_to_note_subset(
        self,
        col: TestCollection,
    ) -> None:
        """Test that card_ids are filtered to only include cards from the note subset.

        This tests the logic in new_selected_notes where:
        - If card_ids are defined, they should be filtered to only include cards
          from the subset of notes being selected
        - This ensures that when note_ids is a sub-selection, card_ids is also
          a corresponding sub-selection
        """
        # Create deck and model
        deck_id = col.decks.id("TestDeck")
        assert deck_id is not None
        model = col.models.by_name("Basic")
        assert model is not None

        # Create 5 notes with their card IDs
        note_ids: list[NoteId] = []
        all_card_ids: list[CardId] = []
        note_to_cards_map: dict[NoteId, list[CardId]] = {}

        for i in range(5):
            note = col.new_note(model)
            note["Front"] = f"Front {i}"
            note["Back"] = f"Back {i}"
            col.add_note(note, deck_id)
            note_ids.append(note.id)
            cards = list(note.card_ids())
            all_card_ids.extend(cards)
            note_to_cards_map[note.id] = cards

        # Create SelectedNotes with all notes and all cards
        selected_notes = SelectedNotes(col, note_ids, card_ids=all_card_ids)
        assert selected_notes.get_selected_card_ids() == all_card_ids

        # Test 1: Create subset with first 3 notes using new_selected_notes
        subset_note_ids = note_ids[:3]
        subset_selected_notes = selected_notes.new_selected_notes(subset_note_ids)

        # Expected card IDs should only be from the subset of notes
        expected_card_ids = []
        for nid in subset_note_ids:
            expected_card_ids.extend(note_to_cards_map[nid])

        # Verify card IDs are filtered correctly
        filtered_card_ids = subset_selected_notes.get_selected_card_ids()
        assert filtered_card_ids is not None
        assert set(filtered_card_ids) == set(expected_card_ids)

        # Verify no cards from excluded notes are present
        excluded_note_ids = note_ids[3:]
        excluded_card_ids = []
        for nid in excluded_note_ids:
            excluded_card_ids.extend(note_to_cards_map[nid])

        assert filtered_card_ids is not None
        for card_id in excluded_card_ids:
            assert card_id not in filtered_card_ids

        # Test 2: Create subset with different notes (last 2) using new_selected_notes
        subset_note_ids_2 = note_ids[3:]
        subset_selected_notes_2 = selected_notes.new_selected_notes(subset_note_ids_2)

        expected_card_ids_2 = []
        for nid in subset_note_ids_2:
            expected_card_ids_2.extend(note_to_cards_map[nid])

        filtered_card_ids_2 = subset_selected_notes_2.get_selected_card_ids()
        assert filtered_card_ids_2 is not None
        assert set(filtered_card_ids_2) == set(expected_card_ids_2)

        # Test 3: Create subset using new_selected_notes_batch
        subset_note_ids_3 = note_ids[1:4]
        selected_notes_by_type = selected_notes.filter_by_note_type(NoteModel(col, model))
        assert selected_notes_by_type.get_selected_card_ids()
        subset_batch = selected_notes_by_type.new_selected_notes_batch(subset_note_ids_3)

        expected_card_ids_3 = []
        for nid in subset_note_ids_3:
            expected_card_ids_3.extend(note_to_cards_map[nid])

        batch_card_ids = subset_batch.get_selected_card_ids()
        assert batch_card_ids is not None
        assert set(batch_card_ids) == set(expected_card_ids_3)

        # Test 4: Verify edge case with single note
        subset_note_ids_4 = [note_ids[0]]
        subset_single = selected_notes.new_selected_notes(subset_note_ids_4)

        expected_card_ids_4 = note_to_cards_map[note_ids[0]]
        single_card_ids = subset_single.get_selected_card_ids()
        assert single_card_ids is not None
        assert set(single_card_ids) == set(expected_card_ids_4)


class TestSelectedNotesFromNote:
    """Test class for SelectedNotesFromNote."""

    @with_test_collection("two_deck_collection")
    def test_factory_method_and_preservation(
        self,
        col: TestCollection,
    ) -> None:
        """Test that filter_by_note_type creates SelectedNotesFromType and sub-selections preserve note_type."""
        # Get note IDs
        note_ids = col.find_notes("")[:4]
        selected_notes = SelectedNotes(col, note_ids)

        # Get note type
        note_type = NoteModel.by_name(col, "Basic")
        assert note_type

        # Test factory method
        selected_from_note = selected_notes.filter_by_note_type(note_type)
        assert isinstance(selected_from_note, SelectedNotesFromType)
        assert selected_from_note.note_type == note_type
        assert list(selected_from_note.get_ids()) == list(note_ids)

        # Test sub-selection preserves note_type
        subset_ids = note_ids[:2]
        subset = selected_from_note.new_selected_notes(subset_ids)

        assert isinstance(subset, SelectedNotesFromType)
        assert subset.note_type == note_type
        assert list(subset.get_ids()) == list(subset_ids)

        # Test batch creation
        batch = selected_from_note.new_selected_notes_batch(subset_ids)
        assert isinstance(batch, SelectedNotesFromType)
        assert isinstance(batch, SelectedNotesBatch)


class SelectedNotesParent:
    """Test class for parent() method."""

    @with_test_collection("two_deck_collection")
    def test_parent_returns_none_for_root_selection(
        self,
        col: TestCollection,
    ) -> None:
        """Test that .parent() returns None for root SelectedNotes (no parent)."""
        note_ids = col.find_notes("")[:3]
        selected_notes = SelectedNotes(col, note_ids)

        # Root selection should have no parent
        assert selected_notes.parent() is None

    @with_test_collection("two_deck_collection")
    def test_parent_after_filter_by_note_type(
        self,
        col: TestCollection,
    ) -> None:
        """Test that .parent() returns to previous selection after filter_by_note_type."""
        # add some "Cloze" notes to the collection for testing
        for _ in range(2):
            model = col.models.by_name("Cloze")
            deck_id = col.decks.id_for_name("Default")
            assert model and deck_id
            note = col.new_note(model)
            col.add_note(note, deck_id)

        collection_note_ids = col.find_notes("")
        selected_notes = SelectedNotes(col, collection_note_ids)

        # Filter by note type
        note_type = NoteModel.by_name(col, "Cloze")
        assert note_type
        filtered = selected_notes.filter_by_note_type(note_type)
        assert filtered
        assert list(collection_note_ids) != list(filtered.get_ids())
        assert collection_note_ids == selected_notes.get_ids()

        # .parent() should return to the original selection
        parent = filtered.parent()
        assert parent is not None
        assert (parent.get_ids()) == list(collection_note_ids)
        assert parent == selected_notes
        assert parent.get_ids() != filtered.get_ids()
        assert parent != filtered

    @with_test_collection("two_deck_collection")
    def test_parent_after_new_selected_notes(
        self,
        col: TestCollection,
    ) -> None:
        """Test that .parent() returns to previous selection after new_selected_notes."""
        note_ids = col.find_notes("")[:4]
        selected_notes = SelectedNotes(col, note_ids)

        # Create sub-selection
        subset_ids = note_ids[:2]
        subset = selected_notes.new_selected_notes(subset_ids)

        # .parent() should return to the original selection
        parent = subset.parent()
        assert parent is not None
        assert list(parent.get_ids()) == list(note_ids)

    @with_test_collection("empty_collection")
    def test_parent_after_filter_by_empty_field(
        self,
        col: TestCollection,
    ) -> None:
        """Test that .parent() returns to previous selection after filter_by_empty_field."""
        model = col.models.by_name("Basic")
        assert model is not None
        deck_id = col.decks.id_for_name("Default")
        assert deck_id

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

        # Filter by empty field
        filtered = selected_notes.filter_by_empty_field(["Front"])

        # .parent() should return to the original selection
        parent = filtered.parent()
        assert parent is not None
        assert list(parent.get_ids()) == list(note_ids)

    @with_test_collection("empty_collection")
    def test_parent_after_batched_by_prompt_size(
        self,
        col: TestCollection,
    ) -> None:
        """Test that .parent() returns to previous selection after batched_by_prompt_size."""
        model = col.models.by_name("Basic")
        assert model is not None
        deck_id = col.decks.id_for_name("Default")
        assert deck_id

        # Create notes with empty fields
        note_ids = []
        for i in range(10):
            note = col.new_note(model)
            note["Front"] = ""  # Empty field
            note["Back"] = f"Back {i}"
            col.add_note(note, deck_id)
            note_ids.append(note.id)

        selected_notes = SelectedNotes(col, note_ids)
        prompt_builder = PromptBuilder(col)
        note_type = NoteModel(col, model)

        # Get batches
        selected_from_type = selected_notes.filter_by_note_type(note_type)
        batches = selected_from_type.batched_by_prompt_size(
            prompt_builder=prompt_builder,
            field_selection=FieldSelection(
                selected=["Front", "Back"],
                writable=["Front"],
                overwritable=[],
            ),
            max_chars=5000,
            max_examples=10,
        )

        batch = batches[0]
        parent = batch.parent()
        assert parent is not None
        assert isinstance(parent, SelectedNotesFromType)

    @with_test_collection("two_deck_collection")
    def test_chaining_end_multiple_times(
        self,
        col: TestCollection,
    ) -> None:
        """Test chaining multiple .parent() calls (each goes back one level)."""
        note_ids = col.find_notes("")[:4]
        selected_notes = SelectedNotes(col, note_ids)
        note_type = NoteModel.by_name(col, "Basic")
        assert note_type

        # Create chain: SelectedNotes -> SelectedNotesFromType -> sub-selection
        filtered = selected_notes.filter_by_note_type(note_type)
        subset_ids = list(filtered.get_ids())[:2] if filtered.get_ids() else []
        subset = filtered.new_selected_notes(subset_ids) if subset_ids else filtered

        # First .parent() returns to filtered
        parent1 = subset.parent()
        assert parent1 is filtered

        # Second .parent() returns to original selection (if filtered was created from selected_notes)
        parent2 = parent1.parent() if parent1 else None
        assert parent2 is selected_notes

    @with_test_collection("empty_collection")
    def test_parent_preserves_note_type(
        self,
        col: TestCollection,
    ) -> None:
        """Test that .parent() preserves note_type when returning from SelectedNotesFromType."""
        model = col.models.by_name("Basic")
        assert model is not None
        deck_id = col.decks.id_for_name("Default")
        assert deck_id

        # Create notes
        note_ids = []
        for i in range(3):
            note = col.new_note(model)
            note["Front"] = ""
            note["Back"] = f"Back {i}"
            col.add_note(note, deck_id)
            note_ids.append(note.id)

        selected_notes = SelectedNotes(col, note_ids)
        note_type = NoteModel(col, model)

        # Filter by note type
        filtered = selected_notes.filter_by_note_type(note_type)

        # Filter by empty field
        filtered_empty = filtered.filter_by_empty_field(["Front"])

        # .parent() should return to the SelectedNotesFromType (not plain SelectedNotes)
        parent = filtered_empty.parent()
        assert parent is not None
        assert isinstance(parent, SelectedNotesFromType)
        assert parent.note_type == note_type
