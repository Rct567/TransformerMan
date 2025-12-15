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


class FieldUpdates:
    """
    A container for field updates to be applied to notes.

    This class wraps a dictionary mapping note IDs to field updates,
    providing a more type-safe and extensible interface than using
    dict[NoteId, dict[str, str]] directly.
    """

    def __init__(self, updates: dict[NoteId, dict[str, str]] | None = None) -> None:
        """
        Initialize FieldUpdates with optional initial data.

        Args:
            updates: Initial field updates dictionary. If None, creates empty updates.
        """
        self._updates: dict[NoteId, dict[str, str]] = updates.copy() if updates else {}

    def clear(self) -> None:
        """Clear all field updates."""
        self._updates.clear()

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
        if isinstance(other, FieldUpdates):
            self._updates.update(other._updates)
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
        if note_id not in self._updates:
            self._updates[note_id] = {}
        self._updates[note_id][field_name] = content

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
            return self._updates == other._updates
        if isinstance(other, dict):
            return self._updates == other
        return False

    @override
    def __hash__(self) -> int:
        """Return a hash of the FieldUpdates."""
        return hash(tuple(sorted(self._updates.items())))

    @override
    def __repr__(self) -> str:
        """Return a string representation of the FieldUpdates."""
        return f"FieldUpdates({self._updates})"
