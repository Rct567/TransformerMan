"""
TransformerMan by Rick Zuidhoek. Licensed under the GNU GPL-3.0.
See <https://www.gnu.org/licenses/gpl-3.0.html> for details.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from .utilities import batched

if TYPE_CHECKING:
    from collections.abc import Sequence
    from anki.collection import Collection
    from anki.notes import Note, NoteId
    from .prompt_builder import PromptBuilder


class SelectedNotes:
    """Manages selected notes for transformation."""

    _note_ids: Sequence[NoteId]
    _note_cache: dict[NoteId, Note]

    def __init__(self, col: Collection, note_ids: Sequence[NoteId], note_cache: dict[NoteId, Note] | None = None) -> None:
        """
        Initialize with collection and selected note IDs.

        Args:
            col: Anki collection.
            note_ids: Sequence of selected note IDs.
        """
        self.col = col
        self._note_ids = note_ids
        self._note_cache = note_cache if note_cache else {}
        self.logger = logging.getLogger(__name__)

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


    def get_ids(self) -> Sequence[NoteId]:
        """Return the note IDs in the selection."""
        return self._note_ids


    def filter_by_note_type(self, note_type_name: str) -> Sequence[NoteId]:
        """
        Filter notes by note type name.

        Args:
            note_type_name: Name of the note type to filter by.

        Returns:
            List of note IDs matching the note type.
        """
        filtered_note_ids: list[NoteId] = []

        for nid in self._note_ids:
            note = self.get_note(nid)
            notetype = self.col.models.get(note.mid)
            if notetype and notetype['name'] == note_type_name:
                filtered_note_ids.append(nid)

        return filtered_note_ids

    def get_note_type_counts(self) -> dict[str, int]:
        """
        Get count of notes for each note type in the selection.

        Returns:
            Dictionary mapping note type names to counts, sorted by count (descending).
        """
        counts: dict[str, int] = {}

        for nid in self._note_ids:
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

        for batch_note_ids in batched(self._note_ids, batch_size):
            batches.append(self.new_selected_notes(batch_note_ids))

        return batches

    def batched_by_prompt_size(
        self,
        prompt_builder: PromptBuilder,
        selected_fields: Sequence[str],
        note_type_name: str,
        max_chars: int,
    ) -> list[SelectedNotes]:
        """
        Split notes into batches where each batch's prompt size <= max_chars.

        Uses a simple greedy algorithm that builds prompts to check sizes.

        Args:
            prompt_builder: PromptBuilder instance for building prompts.
            selected_fields: Sequence of field names to fill.
            note_type_name: Name of the note type.
            max_chars: Maximum prompt size in characters.

        Returns:
            List of SelectedNotes instances, each representing a batch.
        """
        if not self._note_ids:
            return []

        # Filter to only notes with empty fields (these are the ones that will be in the prompt)
        notes_with_empty_fields = self.filter_by_empty_field(selected_fields)
        if not notes_with_empty_fields:
            return []

        # Get note objects
        notes = notes_with_empty_fields.get_notes()

        batches: list[SelectedNotes] = []
        current_batch_note_ids: list[NoteId] = []

        for note in notes:
            # Try adding this note to the current batch
            test_batch_note_ids = current_batch_note_ids + [note.id]
            test_selected_notes = self.new_selected_notes(test_batch_note_ids)

            try:
                # Build the actual prompt to check its size
                test_prompt = prompt_builder.build_prompt(
                    col=self.col,
                    target_notes=test_selected_notes,
                    selected_fields=selected_fields,
                    note_type_name=note_type_name,
                )
                test_size = len(test_prompt)

                if test_size <= max_chars:
                    # Note fits in current batch
                    current_batch_note_ids = test_batch_note_ids
                else:
                    # Note doesn't fit - finalize current batch if it has notes
                    if current_batch_note_ids:
                        batches.append(self.new_selected_notes(current_batch_note_ids))

                    # Start new batch with just this note
                    # Check if note fits alone
                    single_note_selected_notes = self.new_selected_notes([note.id])
                    single_prompt = prompt_builder.build_prompt(
                        col=self.col,
                        target_notes=single_note_selected_notes,
                        selected_fields=selected_fields,
                        note_type_name=note_type_name,
                    )
                    single_size = len(single_prompt)

                    if single_size <= max_chars:
                        current_batch_note_ids = [note.id]
                    else:
                        # Note is too large even on its own - skip with warning
                        self.logger.warning(
                            f"Note {note.id} exceeds maximum prompt size ({single_size} > {max_chars}). Skipping."
                        )
                        current_batch_note_ids = []

            except Exception as e:
                # If building fails, fall back to single-note batches
                self.logger.warning(f"Failed to build prompt for batch sizing: {e}")
                # Finalize current batch if it has notes
                if current_batch_note_ids:
                    batches.append(self.new_selected_notes(current_batch_note_ids))
                # Start new batch with just this note
                current_batch_note_ids = [note.id]

        # Don't forget last batch
        if current_batch_note_ids:
            batches.append(self.new_selected_notes(current_batch_note_ids))

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
            note_ids = self._note_ids

        notes: list[Note] = []

        for nid in note_ids:
            note = self.get_note(nid)
            notes.append(note)

        return notes

    def new_selected_notes(self, note_ids: Sequence[NoteId]) -> SelectedNotes:
        """
        Get a new SelectedNotes instance containing only the specified note IDs.

        Args:
            note_ids: Sequence of note IDs.

        Returns:
            New SelectedNotes instance.
        """
        return SelectedNotes(self.col, note_ids, self._note_cache)

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
    def has_empty_field(note: Note, selected_fields: Sequence[str]) -> bool:
        """
        Check if a note has any empty fields among the selected fields.

        Args:
            note: The note to check.
            selected_fields: Sequence of field names to consider.

        Returns:
            True if the note has at least one empty field in selected_fields, False otherwise.
        """
        selected_fields_set = set(selected_fields)
        return any(not note[field].strip() for field in selected_fields_set if field in note)

    def has_note_with_empty_field(self, selected_fields: Sequence[str]) -> bool:
        """
        Check if any note in this SelectedNotes instance has empty fields.

        Args:
            selected_fields: Sequence of field names to consider.

        Returns:
            True if at least one note has empty fields in selected_fields, False otherwise.
        """
        for nid in self._note_ids:
            note = self.get_note(nid)
            if SelectedNotes.has_empty_field(note, selected_fields):
                return True
        return False

    def filter_by_empty_field(self, selected_fields: Sequence[str]) -> SelectedNotes:
        """
        Return a new SelectedNotes instance containing only notes that have at least one empty field among selected_fields.

        Args:
            selected_fields: Sequence of field names to consider.

        Returns:
            New SelectedNotes instance with filtered note IDs.
        """
        filtered_note_ids: list[NoteId] = []
        for nid in self._note_ids:
            note = self.get_note(nid)
            if SelectedNotes.has_empty_field(note, selected_fields):
                filtered_note_ids.append(nid)
        return self.new_selected_notes(filtered_note_ids)

    def clear_cache(self) -> None:
        """Clear the note cache."""
        self._note_cache.clear()

    def __len__(self) -> int:
        """Return the number of notes in the selection."""
        return len(self._note_ids)
