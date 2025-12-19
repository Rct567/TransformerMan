"""
TransformerMan by Rick Zuidhoek. Licensed under the GNU GPL-3.0.

See <https://www.gnu.org/licenses/gpl-3.0.html> for details.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, overload

from .utilities import override

if TYPE_CHECKING:
    from collections.abc import Iterator
    from anki.notes import NoteId
    from ..lib.selected_notes import SelectedNotes


class FieldUpdates:
    """
    A container for field updates to be applied to notes.

    This class wraps a dictionary mapping note IDs to field updates,
    providing a more type-safe and extensible interface than using
    dict[NoteId, dict[str, str]] directly.
    """

    def __init__(self, updates: dict[NoteId, dict[str, str]] | None = None, selected_notes: SelectedNotes | None = None) -> None:
        """
        Initialize FieldUpdates with optional initial data.

        Args:
            updates: Initial field updates dictionary. If None, creates empty updates.
            selected_notes: SelectedNotes instance for accessing note data.
        """
        self._updates: dict[NoteId, dict[str, str]] = updates.copy() if updates else {}
        self._overwritable_fields: set[str] = set()
        self._selected_notes = selected_notes
        self.is_applied = False

    def __len__(self) -> int:
        """Return the number of notes with field updates."""
        return len(self._updates)

    def __bool__(self) -> bool:
        """Return True if there are any field updates."""
        return bool(self._updates)

    def items(self) -> Iterator[tuple[NoteId, dict[str, str]]]:
        """Return an iterator over (note_id, field_updates) pairs."""
        return iter(self._updates.items())

    def keys(self) -> Iterator[NoteId]:
        """Return an iterator over note IDs."""
        return iter(self._updates.keys())

    def values(self) -> Iterator[dict[str, str]]:
        """Return an iterator over field updates dictionaries."""
        return iter(self._updates.values())

    @overload
    def get(self, note_id: NoteId) -> dict[str, str] | None:
        ...

    @overload
    def get(self, note_id: NoteId, default: dict[str, str]) -> dict[str, str]:
        ...

    def get(self, note_id: NoteId, default: dict[str, str] | None = None) -> dict[str, str] | None:
        """
        Get field updates for a specific note ID.

        Args:
            note_id: The note ID to look up.
            default: Default value to return if note_id is not found.

        Returns:
            Field updates dictionary for the note, or default if not found.
        """
        return self._updates.get(note_id, default)

    def update(self, other: dict[NoteId, dict[str, str]] | FieldUpdates) -> None:
        """
        Update with field updates from another dictionary or FieldUpdates instance.

        Args:
            other: Dictionary or FieldUpdates instance to merge into this one.
        """
        assert not self.is_applied, "Cannot update FieldUpdates after they have been applied."
        if isinstance(other, FieldUpdates):
            # Merge field updates
            for note_id, updates in other._updates.items():
                if note_id not in self._updates:
                    self._updates[note_id] = {}
                self._updates[note_id].update(updates)

            # Merge overwritable fields
            self._overwritable_fields.update(other._overwritable_fields)

            # Use the other's selected_notes if we don't have one and they do
            if not self._selected_notes and other._selected_notes:
                self._selected_notes = other._selected_notes
        else:
            self._updates.update(other)

    def add_field_update(self, note_id: NoteId, field_name: str, content: str) -> None:
        """
        Add a single field update for a note.

        Args:
            note_id: The note ID to update.
            field_name: The name of the field to update.
            content: The new content for the field.
        """
        assert not self.is_applied, "Cannot add field updates after they have been applied."
        if note_id not in self._updates:
            self._updates[note_id] = {}
        self._updates[note_id][field_name] = content

    def add_field_updates(self, note_id: NoteId, field_updates: dict[str, str]) -> None:
        """
        Add multiple field updates for a note.

        Args:
            note_id: The note ID to update.
            field_updates: Dictionary of field names to new content.
        """
        assert not self.is_applied, "Cannot add field updates after they have been applied."
        if note_id not in self._updates:
            self._updates[note_id] = {}
        self._updates[note_id].update(field_updates)

    def add_overwritable_field(self, field_name: str) -> None:
        """
        Mark a field as overwritable for this transformation.

        Args:
            field_name: The name of the field that is overwritable.
        """
        assert not self.is_applied, "Cannot add overwritable fields after updates have been applied."
        self._overwritable_fields.add(field_name)

    def get_overwritable_fields(self) -> set[str]:
        """
        Get the set of overwritable fields for this transformation.

        Returns:
            Set of field names that are overwritable.
        """
        return self._overwritable_fields.copy()

    def has_overwritable_fields(self) -> bool:
        """
        Check if any fields are marked as overwritable.

        Returns:
            True if any fields are overwritable, False otherwise.
        """
        return bool(self._overwritable_fields)

    def get_notes_with_overwritten_content(self) -> dict[NoteId, set[str]]:
        """
        Get notes that will have content overwritten based on overwritable fields.

        Returns:
            Dictionary mapping note_id to set of field names that will be overwritten.
        """
        if not self._selected_notes:
            return {}

        notes_with_overwritten: dict[NoteId, set[str]] = {}

        for note_id, field_updates in self._updates.items():
            try:
                note = self._selected_notes.get_note(note_id)
                overwritten_fields: set[str] = set()

                for field_name in field_updates.keys():
                    if (field_name in self._overwritable_fields and
                        field_name in note and
                        note[field_name].strip()):
                        overwritten_fields.add(field_name)

                if overwritten_fields:
                    notes_with_overwritten[note_id] = overwritten_fields

            except Exception:
                # Skip notes that can't be loaded
                continue

        return notes_with_overwritten

    def __contains__(self, note_id: NoteId) -> bool:
        """Check if a note ID has field updates."""
        return note_id in self._updates

    def __iter__(self) -> Iterator[NoteId]:
        """Iterate over note IDs."""
        return iter(self._updates)

    def __getitem__(self, note_id: NoteId) -> dict[str, str]:
        """Get field updates for a specific note ID."""
        return self._updates[note_id]

    @override
    def __eq__(self, other: object) -> bool:
        """Check equality with another FieldUpdates instance or dictionary."""
        if isinstance(other, FieldUpdates):
            return (self._updates == other._updates and
                   self._overwritable_fields == other._overwritable_fields and
                   self._selected_notes is other._selected_notes)
        if isinstance(other, dict):
            return self._updates == other
        return False

    @override
    def __hash__(self) -> int:
        """Return a hash of the FieldUpdates."""
        updates_tuple = tuple(sorted(
            (note_id, tuple(sorted(field_items.items())))
            for note_id, field_items in self._updates.items()
        ))
        overwritable_tuple = tuple(sorted(self._overwritable_fields))
        selected_notes_tuple = (id(self._selected_notes) if self._selected_notes else None,)
        return hash((updates_tuple, overwritable_tuple, selected_notes_tuple))

    @override
    def __repr__(self) -> str:
        """Return a string representation of the FieldUpdates."""
        return (f"FieldUpdates(updates={self._updates}, "
                f"overwritable_fields={self._overwritable_fields}, "
                f"selected_notes={self._selected_notes})")
