"""
Tests for FieldUpdates overwritable fields tracking functionality.
"""

from __future__ import annotations

from anki.notes import NoteId

from transformerman.lib.field_updates import FieldUpdates
from transformerman.lib.selected_notes import SelectedNotes
from tests.tools import with_test_collection, TestCollection, test_collection as test_collection_fixture

col = test_collection_fixture



class TestFieldUpdates:


    def test_add_overwritable_field(self) -> None:
        """Test adding overwritable fields."""
        field_updates = FieldUpdates()

        # Add overwritable fields
        field_updates.add_overwritable_field("field1")
        field_updates.add_overwritable_field("field2")

        # Check overwritable fields
        overwritable = field_updates.get_overwritable_fields()
        assert overwritable == {"field1", "field2"}

        # Check that we have overwritable fields
        assert field_updates.has_overwritable_fields() is True

    def test_no_overwritable_fields(self) -> None:
        """Test behavior when no fields are overwritable."""
        field_updates = FieldUpdates()

        # Check that we have no overwritable fields
        assert field_updates.has_overwritable_fields() is False

        # Get overwritable fields should be empty
        overwritable = field_updates.get_overwritable_fields()
        assert overwritable == set()

    @with_test_collection("empty_collection")
    def test_get_notes_with_overwritten_content(self, col: TestCollection) -> None:
        """Test calculating notes with overwritten content."""

        # Create real notes in the collection first
        model = col.models.by_name("Basic")
        assert model is not None
        deck = col.decks.all()[0]
        deck_id = deck["id"]

        note1 = col.new_note(model)
        note1["Front"] = "old_front1"
        note1["Back"] = "old_back1"
        col.add_note(note1, deck_id)

        note2 = col.new_note(model)
        note2["Back"] = ""  # empty content
        note2["Front"] = "front2"
        col.add_note(note2, deck_id)

        note3 = col.new_note(model)
        note3["Back"] = "old_back3"
        col.add_note(note3, deck_id)

        # Create selected notes with the actual note IDs
        selected_notes = SelectedNotes(col, [note1.id, note2.id, note3.id])
        field_updates = FieldUpdates(selected_notes=selected_notes)

        # Add overwritable fields
        field_updates.add_overwritable_field("Front")
        # Note: Back is NOT overwritable to test the logic properly

        # Add field updates for notes
        field_updates.add_field_update(note1.id, "Front", "new_front1")
        field_updates.add_field_update(note1.id, "Back", "new_back1")
        field_updates.add_field_update(note2.id, "Back", "new_back2")
        field_updates.add_field_update(note3.id, "Back", "new_back3")  # not overwritable

        # Calculate overwritten content
        overwritten = field_updates.get_notes_with_overwritten_content()

        # Note 1 should have Front overwritten (has content and is overwritable)
        # Note 2 should not have anything overwritten (Back is not overwritable)
        # Note 3 should not have anything overwritten (Back is not overwritable)
        expected = {
            note1.id: {"Front"}
        }
        assert overwritten == expected

    def test_update_merges_overwritable_fields(self) -> None:
        """Test that update() method properly merges overwritable fields."""
        field_updates1 = FieldUpdates()
        field_updates2 = FieldUpdates()

        note_id1 = NoteId(123)
        note_id2 = NoteId(456)

        # Setup first FieldUpdates
        field_updates1.add_field_update(note_id1, "field1", "content1")
        field_updates1.add_overwritable_field("field1")

        # Setup second FieldUpdates
        field_updates2.add_field_update(note_id1, "field2", "content2")
        field_updates2.add_overwritable_field("field2")
        field_updates2.add_field_update(note_id2, "field3", "content3")
        field_updates2.add_overwritable_field("field3")

        # Update first with second
        field_updates1.update(field_updates2)

        # Check that both field updates and overwritable fields are merged
        assert field_updates1.get(note_id1) == {"field1": "content1", "field2": "content2"}
        assert field_updates1.get(note_id2) == {"field3": "content3"}

        # Check overwritable fields are merged
        overwritable = field_updates1.get_overwritable_fields()
        assert overwritable == {"field1", "field2", "field3"}

    def test_equality_includes_overwritable_fields(self) -> None:
        """Test that equality check includes overwritable fields."""
        field_updates1 = FieldUpdates()
        field_updates2 = FieldUpdates()
        field_updates3 = FieldUpdates()

        note_id = NoteId(123)

        # Add same field updates to all
        field_updates1.add_field_update(note_id, "field1", "content1")
        field_updates2.add_field_update(note_id, "field1", "content1")
        field_updates3.add_field_update(note_id, "field1", "content1")

        # Mark overwritable fields on 1 and 2
        field_updates1.add_overwritable_field("field1")
        field_updates2.add_overwritable_field("field1")

        # 1 and 2 should be equal (same field updates and same overwritable fields)
        assert field_updates1 == field_updates2

        # 1 and 3 should not be equal (same field updates but different overwritable fields)
        assert field_updates1 != field_updates3

    def test_hash_includes_overwritable_fields(self) -> None:
        """Test that hash includes overwritable fields."""
        field_updates1 = FieldUpdates()
        field_updates2 = FieldUpdates()
        field_updates3 = FieldUpdates()

        note_id = NoteId(123)

        # Add same field updates to all
        field_updates1.add_field_update(note_id, "field1", "content1")
        field_updates2.add_field_update(note_id, "field1", "content1")
        field_updates3.add_field_update(note_id, "field1", "content1")

        # Mark overwritable fields on 1 and 2
        field_updates1.add_overwritable_field("field1")
        field_updates2.add_overwritable_field("field1")

        # 1 and 2 should have same hash
        assert hash(field_updates1) == hash(field_updates2)

        # 1 and 3 should have different hash
        assert hash(field_updates1) != hash(field_updates3)

    def test_get_notes_with_overwritten_content_handles_missing_notes(self) -> None:
        """Test that get_notes_with_overwritten_content handles missing notes gracefully."""
        field_updates = FieldUpdates()  # No selected_notes

        # Add overwritable fields and field updates
        field_updates.add_overwritable_field("field1")
        note_id = NoteId(123)
        field_updates.add_field_update(note_id, "field1", "content1")

        # Should handle missing selected_notes gracefully
        overwritten = field_updates.get_notes_with_overwritten_content()
        assert overwritten == {}
