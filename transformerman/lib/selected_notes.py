"""
TransformerMan by Rick Zuidhoek. Licensed under the GNU GPL-3.0.
See <https://www.gnu.org/licenses/gpl-3.0.html> for details.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from anki.collection import Collection
    from anki.notes import Note, NoteId


class SelectedNotes:
    """Manages selected notes for transformation."""

    def __init__(self, col: Collection, note_ids: list[NoteId]) -> None:
        """
        Initialize with collection and selected note IDs.

        Args:
            col: Anki collection.
            note_ids: List of selected note IDs.
        """
        self.col = col
        self.note_ids = note_ids

    def filter_by_note_type(self, note_type_name: str) -> list[NoteId]:
        """
        Filter notes by note type name.

        Args:
            note_type_name: Name of the note type to filter by.

        Returns:
            List of note IDs matching the note type.
        """
        filtered_ids: list[NoteId] = []

        for nid in self.note_ids:
            try:
                note = self.col.get_note(nid)
                notetype = self.col.models.get(note.mid)
                if notetype and notetype['name'] == note_type_name:
                    filtered_ids.append(nid)
            except Exception:
                continue

        return filtered_ids

    def get_note_type_counts(self) -> dict[str, int]:
        """
        Get count of notes for each note type in the selection.

        Returns:
            Dictionary mapping note type names to counts, sorted by count (descending).
        """
        counts: dict[str, int] = {}

        for nid in self.note_ids:
            try:
                note = self.col.get_note(nid)
                notetype = self.col.models.get(note.mid)
                if notetype:
                    name = notetype['name']
                    counts[name] = counts.get(name, 0) + 1
            except Exception:
                continue

        # Sort by count descending
        return dict(sorted(counts.items(), key=lambda x: x[1], reverse=True))

    def create_batches(self, note_ids: list[NoteId], batch_size: int) -> list[list[NoteId]]:
        """
        Split note IDs into batches.

        Args:
            note_ids: List of note IDs to batch.
            batch_size: Maximum size of each batch.

        Returns:
            List of batches (each batch is a list of note IDs).
        """
        batches: list[list[NoteId]] = []

        for i in range(0, len(note_ids), batch_size):
            batches.append(note_ids[i:i + batch_size])

        return batches

    def get_notes(self, note_ids: list[NoteId]) -> list[Note]:
        """
        Get Note objects from note IDs.

        Args:
            note_ids: List of note IDs.

        Returns:
            List of Note objects.
        """
        notes: list[Note] = []

        for nid in note_ids:
            try:
                notes.append(self.col.get_note(nid))
            except Exception:
                continue

        return notes

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
