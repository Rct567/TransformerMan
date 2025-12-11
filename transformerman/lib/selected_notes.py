"""
TransformerMan by Rick Zuidhoek. Licensed under the GNU GPL-3.0.
See <https://www.gnu.org/licenses/gpl-3.0.html> for details.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:
    from collections.abc import Sequence
    from anki.collection import Collection
    from anki.notes import Note, NoteId
    from .prompt_builder import PromptBuilder


class BatchingStats(NamedTuple):
    num_prompts_tried: int
    avg_batch_size: int | None
    num_batches: int

class SelectedNotes:
    """Manages selected notes for transformation."""

    _note_ids: Sequence[NoteId]
    _note_cache: dict[NoteId, Note]
    batching_stats: BatchingStats | None

    # Constants for batch sizing algorithm
    DEFAULT_START_SIZE: int = 250
    EXPONENTIAL_MULTIPLIER: int = 2
    MAX_BINARY_SEARCH_ITERATIONS: int = 3  # Limit binary search to prevent too many prompt builds

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
        self.batching_stats = None

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


    def batched_by_prompt_size(
        self,
        prompt_builder: PromptBuilder,
        selected_fields: Sequence[str],
        note_type_name: str,
        max_chars: int,
    ) -> list[SelectedNotes]:
        """
        Split notes into batches where each batch's prompt size <= max_chars.

        Uses exponential search starting from DEFAULT_START_SIZE notes: increases when it fits,
        decreases via binary search when it doesn't fit.

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
        i = 0  # Current position in notes list
        last_batch_size = self.DEFAULT_START_SIZE  # Start with default, then use previous batch size
        num_prompts_tried = 0

        def build_prompt(test_selected_notes: SelectedNotes) -> str:
            nonlocal num_prompts_tried
            num_prompts_tried += 1
            return prompt_builder.build_prompt(
                target_notes=test_selected_notes,
                selected_fields=selected_fields,
                note_type_name=note_type_name,
            )

        while i < len(notes):
            remaining = len(notes) - i

            # Use the size of the last batch as starting point (but at least DEFAULT_START_SIZE)
            # This is efficient because batch sizes tend to be similar
            start_size = min(max(self.DEFAULT_START_SIZE, last_batch_size), remaining)

            # First check if start_size fits
            test_batch_note_ids = [note.id for note in notes[i:i+start_size]]
            test_selected_notes = self.new_selected_notes(test_batch_note_ids)

            try:
                test_prompt = build_prompt(test_selected_notes)
                test_size = len(test_prompt)
                start_fits = test_size <= max_chars
            except Exception as e:
                # If building fails, treat as too large
                self.logger.warning(f"Failed to build prompt for batch sizing: {e}")
                start_fits = False

            if start_fits:
                # start_size fits, try to find larger size that fits
                # Exponential search with doubling
                low = start_size
                high = start_size

                # Find upper bound (first size that doesn't fit)
                while high < remaining:
                    next_size = min(high * self.EXPONENTIAL_MULTIPLIER, remaining)
                    if next_size <= high:  # Prevent infinite loop
                        break

                    test_batch_note_ids = [note.id for note in notes[i:i+next_size]]
                    test_selected_notes = self.new_selected_notes(test_batch_note_ids)

                    try:
                        test_prompt = build_prompt(test_selected_notes)
                        test_size = len(test_prompt)

                        if test_size <= max_chars:
                            # Still fits, continue exponential search
                            low = next_size  # Update lower bound (last known fitting size)
                            high = next_size
                        else:
                            # Doesn't fit, found upper bound
                            high = next_size
                            break
                    except Exception as e:
                        # If building fails, treat as too large
                        self.logger.warning(f"Failed to build prompt for batch sizing: {e}")
                        high = next_size
                        break

                # Now binary search between low and high to find max fitting size
                # low is last known fitting size, high is first known non-fitting size
                best_size = low

                # If we reached end of notes without finding non-fitting size, use remaining
                if high == low and high < remaining:
                    best_size = remaining
                else:
                    # Binary search between low and high with iteration limit
                    iteration = 0
                    while low + 1 < high and iteration < self.MAX_BINARY_SEARCH_ITERATIONS:
                        iteration += 1
                        mid = (low + high) // 2
                        test_batch_note_ids = [note.id for note in notes[i:i+mid]]
                        test_selected_notes = self.new_selected_notes(test_batch_note_ids)

                        try:
                            test_prompt = build_prompt(test_selected_notes)
                            test_size = len(test_prompt)

                            if test_size <= max_chars:
                                # Fits, try larger
                                best_size = mid
                                low = mid
                            else:
                                # Too large, try smaller
                                high = mid
                        except Exception as e:
                            # If building fails, treat as too large
                            self.logger.warning(f"Failed to build prompt for batch sizing: {e}")
                            high = mid
            else:
                # start_size doesn't fit, binary search between 1 and start_size-1
                low = 1
                high = start_size - 1
                best_size = 0
                iteration = 0

                while low <= high and iteration < self.MAX_BINARY_SEARCH_ITERATIONS:
                    iteration += 1
                    mid = (low + high) // 2
                    test_batch_note_ids = [note.id for note in notes[i:i+mid]]
                    test_selected_notes = self.new_selected_notes(test_batch_note_ids)

                    try:
                        test_prompt = build_prompt(test_selected_notes)
                        test_size = len(test_prompt)

                        if test_size <= max_chars:
                            # Fits, try larger
                            best_size = mid
                            low = mid + 1
                        else:
                            # Too large, try smaller
                            high = mid - 1
                    except Exception as e:
                        # If building fails, treat as too large
                        self.logger.warning(f"Failed to build prompt for batch sizing: {e}")
                        high = mid - 1

            if best_size == 0:
                # Even a single note doesn't fit
                # Check if single note fits alone (for accurate warning)
                single_note_selected_notes = self.new_selected_notes([notes[i].id])
                try:
                    single_prompt = build_prompt(single_note_selected_notes)
                    single_size = len(single_prompt)
                    self.logger.warning(
                        f"Note {notes[i].id} exceeds maximum prompt size ({single_size} > {max_chars}). Skipping."
                    )
                except Exception as e:
                    self.logger.warning(f"Failed to build prompt for note {notes[i].id}: {e}")

                i += 1
                continue

            # Create batch with best_size notes
            batch_note_ids = [note.id for note in notes[i:i+best_size]]

            batches.append(self.new_selected_notes(batch_note_ids))
            last_batch_size = best_size  # Remember for next batch
            i += best_size

        # Calculate and log average batch size
        if batches:
            num_batches = len(batches)
            avg_batch_size = sum(len(batch) for batch in batches) // num_batches
            self.batching_stats = BatchingStats(num_prompts_tried=num_prompts_tried, avg_batch_size=avg_batch_size, num_batches=num_batches)
            self.logger.info(self.batching_stats)
        else:
            self.batching_stats = BatchingStats(num_prompts_tried=num_prompts_tried, avg_batch_size=None, num_batches=0)
            self.logger.info("No batches created")

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
