"""
TransformerMan by Rick Zuidhoek. Licensed under the GNU GPL-3.0.
See <https://www.gnu.org/licenses/gpl-3.0.html> for details.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .utilities import batched

if TYPE_CHECKING:
    from collections.abc import Sequence
    from anki.collection import Collection
    from anki.notes import Note, NoteId


class SelectedNotes:
    """Manages selected notes for transformation."""

    note_ids: Sequence[NoteId]

    def __init__(self, col: Collection, note_ids: Sequence[NoteId]) -> None:
        """
        Initialize with collection and selected note IDs.

        Args:
            col: Anki collection.
            note_ids: Sequence of selected note IDs.
        """
        self.col = col
        self.note_ids = note_ids
        self._note_cache: dict[NoteId, Note] = {}

    def get_note(self, nid: NoteId) -> Note:
        """
        Get a Note object by ID, with caching.

        Args:
            nid: Note ID.

        Returns:
            Note object if found and no error, otherwise None.
        """
        if nid in self._note_cache:
            return self._note_cache[nid]

        note = self.col.get_note(nid)
        self._note_cache[nid] = note
        return note


    def filter_by_note_type(self, note_type_name: str) -> Sequence[NoteId]:
        """
        Filter notes by note type name.

        Args:
            note_type_name: Name of the note type to filter by.

        Returns:
            List of note IDs matching the note type.
        """
        filtered_ids: list[NoteId] = []

        for nid in self.note_ids:
            note = self.get_note(nid)
            notetype = self.col.models.get(note.mid)
            if notetype and notetype['name'] == note_type_name:
                filtered_ids.append(nid)

        return filtered_ids

    def get_note_type_counts(self) -> dict[str, int]:
        """
        Get count of notes for each note type in the selection.

        Returns:
            Dictionary mapping note type names to counts, sorted by count (descending).
        """
        counts: dict[str, int] = {}

        for nid in self.note_ids:
            note = self.get_note(nid)
            notetype = self.col.models.get(note.mid)
            if notetype:
                name = notetype['name']
                counts[name] = counts.get(name, 0) + 1

        # Sort by count descending
        return dict(sorted(counts.items(), key=lambda x: x[1], reverse=True))

    def batched(self, batch_size: int) -> list[SelectedNotes]:
        """
        Split the current SelectedNotes instance into batches.

        Args:
            batch_size: Maximum size of each batch.

        Returns:
            List of SelectedNotes instances, each representing a batch.
        """
        batches: list[SelectedNotes] = []

        for batch_note_ids in batched(self.note_ids, batch_size):
            batches.append(self.get_selected_notes(batch_note_ids))

        return batches

    def get_notes(self, note_ids: Sequence[NoteId] | None = None) -> Sequence[Note]:
        """
        Get Note objects from note IDs.

        Args:
            note_ids: Sequence of note IDs. If None, uses the note_ids of this instance.

        Returns:
            List of Note objects.
        """
        if note_ids is None:
            note_ids = self.note_ids

        notes: list[Note] = []

        for nid in note_ids:
            note = self.get_note(nid)
            notes.append(note)

        return notes

    def get_selected_notes(self, note_ids: Sequence[NoteId]) -> SelectedNotes:
        """
        Get a new SelectedNotes instance containing only the specified note IDs.

        Args:
            note_ids: Sequence of note IDs.

        Returns:
            New SelectedNotes instance.
        """
        return SelectedNotes(self.col, note_ids)

    def get_field_names(self, note_type_name: str) -> list[str]:
        """
        Get field names for a note type.

        Args:
            note_type_name: Name of the note type.

        Returns:
            List of field names.
        """
        for notetype in self.col.models.all():
            if notetype['name'] == note_type_name:
                return [field['name'] for field in notetype['flds']]

        return []

    @staticmethod
    def has_empty_field(note: Note, selected_fields: set[str]) -> bool:
        """
        Check if a note has any empty fields among the selected fields.

        Args:
            note: The note to check.
            selected_fields: Set of field names to consider.

        Returns:
            True if the note has at least one empty field in selected_fields, False otherwise.
        """
        return any(not note[field].strip() for field in selected_fields if field in note)

    def has_note_with_empty_field(self, selected_fields: set[str]) -> bool:
        """
        Check if any note in this SelectedNotes instance has empty fields.

        Args:
            selected_fields: Set of field names to consider.

        Returns:
            True if at least one note has empty fields in selected_fields, False otherwise.
        """
        for nid in self.note_ids:
            note = self.get_note(nid)
            if SelectedNotes.has_empty_field(note, selected_fields):
                return True
        return False

    def filter_by_empty_field(self, selected_fields: set[str]) -> SelectedNotes:
        """
        Return a new SelectedNotes instance containing only notes that have at least one empty field among selected_fields.

        Args:
            selected_fields: Set of field names to consider.

        Returns:
            New SelectedNotes instance with filtered note IDs.
        """
        filtered_ids: list[NoteId] = []
        for nid in self.note_ids:
            note = self.get_note(nid)
            if SelectedNotes.has_empty_field(note, selected_fields):
                filtered_ids.append(nid)
        return self.get_selected_notes(filtered_ids)
