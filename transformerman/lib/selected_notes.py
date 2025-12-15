"""
TransformerMan by Rick Zuidhoek. Licensed under the GNU GPL-3.0.
See <https://www.gnu.org/licenses/gpl-3.0.html> for details.
"""

from __future__ import annotations

import logging
import random
from typing import TYPE_CHECKING, NamedTuple

from anki.utils import ids2str

if TYPE_CHECKING:
    from collections.abc import Sequence
    from anki.collection import Collection
    from anki.notes import Note, NoteId
    from anki.cards import CardId
    from .prompt_builder import PromptBuilder


class BatchingStats(NamedTuple):
    num_prompts_tried: int
    avg_batch_size: int | None
    num_batches: int
    num_notes_selected: int  # noqa: vulture
    max_prompt_size: int

class SelectedNotes:
    """Manages selected notes for transformation."""

    _note_ids: Sequence[NoteId]
    _card_ids: Sequence[CardId] | None
    _note_cache: dict[NoteId, Note]
    _deck_cache: dict[CardId, str]
    batching_stats: BatchingStats | None

    # Constants for batch sizing algorithm
    EXPONENTIAL_MULTIPLIER: int = 2
    MAX_BINARY_SEARCH_ITERATIONS: int = 3  # Limit binary search to prevent too many prompt builds

    # Constants for dynamic start size calculation
    # Formula incorporates both max_chars and total notes:
    # start_size = (max_chars - FIXED_OVERHEAD_ESTIMATE) * BASE_COEFFICIENT * scale_factor
    # where scale_factor = min(MAX_SCALE, max(MIN_SCALE, (total_notes / REFERENCE_NOTES) ** SCALE_EXPONENT))
    # Adjusted based on empirical data showing batches up to ~1800 for 500k max_chars

    # Estimated fixed overhead in characters for prompt template, instructions, etc.
    # This is subtracted from max_chars to get available space for note content
    FIXED_OVERHEAD_ESTIMATE: int = 2000

    # Maximum allowed starting batch size to prevent excessive memory usage
    # Increased from 1000 to 2000 based on empirical data showing batches up to ~1800
    MAX_START_SIZE: int = 2000

    def __init__(
        self,
        col: Collection,
        note_ids: Sequence[NoteId],
        card_ids: Sequence[CardId] | None = None,
        note_cache: dict[NoteId, Note] | None = None,
        deck_cache: dict[CardId, str] | None = None,
    ) -> None:
        """Initialize with collection and selected note IDs and optional card IDs."""
        self.col = col
        self._note_ids = note_ids
        self._card_ids = card_ids if card_ids else None
        self._note_cache = note_cache if note_cache else {}
        self._deck_cache = deck_cache if deck_cache else {}
        self.logger = logging.getLogger(__name__)
        self.batching_stats = None

        assert self._card_ids is None or len(self._card_ids) >= len(self._note_ids)

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


    @classmethod
    def _compute_start_size(cls, max_chars: int, total_notes: int | None = None) -> int:
        """
        Compute a reasonable starting batch size based on max_chars and total notes.

        Uses a linear model with coefficient that scales with total notes:
        start_size = (max_chars - fixed_overhead) * base_coefficient * scale_factor

        where scale_factor = min(MAX_SCALE, (total_notes / REFERENCE_NOTES) ** SCALE_EXPONENT)
        This accounts for the observation that with more notes, average batch size tends to be larger.

        Args:
            max_chars: Maximum prompt size in characters.
            total_notes: Total number of notes available (optional). If None, uses default scaling.

        Returns:
            Suggested starting batch size.
        """
        if max_chars <= cls.FIXED_OVERHEAD_ESTIMATE:
            return 1

        # Base coefficient for notes per character at reference note count (1000 notes)
        # Represents how many notes fit per character of available space after overhead
        # Adjusted upward from 0.0025 to 0.0032 based on empirical data showing larger batches
        BASE_COEFFICIENT: float = 0.0032

        # Reference note count for scaling. With this many notes, scale_factor = 1.0
        # Chosen as a typical moderate note count for common usage scenarios
        REFERENCE_NOTES: int = 1000

        # Exponent for scaling function. Lower values (0.3 vs 0.4) make scaling less aggressive
        # This controls how quickly the coefficient increases with more notes
        SCALE_EXPONENT: float = 0.3

        # Minimum scale factor to avoid underprediction when very few notes are selected
        # Prevents the coefficient from becoming too small for small note counts
        MIN_SCALE: float = 0.9

        # Maximum scale factor to prevent overprediction when many notes are selected
        # Limits how much the coefficient can increase with large note counts
        MAX_SCALE: float = 1.5

        if total_notes is None or total_notes <= 0:
            # Default to moderate scaling
            scale_factor = 1.1
        else:
            # Scale coefficient based on total notes
            # With more notes, we can use a larger coefficient (batch sizes tend to be larger)
            scale_factor = (total_notes / REFERENCE_NOTES) ** SCALE_EXPONENT
            scale_factor = max(min(scale_factor, MAX_SCALE), MIN_SCALE)

        effective_coefficient = BASE_COEFFICIENT * scale_factor

        # Linear estimate based on available space after fixed overhead
        estimate = int((max_chars - cls.FIXED_OVERHEAD_ESTIMATE) * effective_coefficient)

        # Apply bounds
        return max(1, min(estimate, cls.MAX_START_SIZE))

    def filter_by_writable_or_overwritable(
        self,
        writable_fields: Sequence[str],
        overwritable_fields: Sequence[str],
    ) -> SelectedNotes:
        """
        Return a new SelectedNotes instance containing only notes that have:
        1. At least one empty field among writable_fields, OR
        2. At least one field among overwritable_fields (regardless of content).

        Args:
            writable_fields: Sequence of field names to check for emptiness.
            overwritable_fields: Sequence of field names to include regardless of content.

        Returns:
            New SelectedNotes instance with filtered note IDs.
        """
        filtered_note_ids: list[NoteId] = []
        writable_set = set(writable_fields)
        overwritable_set = set(overwritable_fields)

        for nid in self._note_ids:
            note = self.get_note(nid)
            # Check if note has empty field in writable_fields
            has_empty_writable = any(
                field in note and not note[field].strip()
                for field in writable_set
            )
            # Check if note has field in overwritable_fields
            has_overwritable = any(
                field in note
                for field in overwritable_set
            )

            if has_empty_writable or has_overwritable:
                filtered_note_ids.append(nid)

        return self.new_selected_notes(filtered_note_ids)

    def batched_by_prompt_size(
        self,
        prompt_builder: PromptBuilder,
        selected_fields: Sequence[str],
        writable_fields: Sequence[str] | None,
        overwritable_fields: Sequence[str] | None,
        note_type_name: str,
        max_chars: int,
    ) -> list[SelectedNotes]:
        """
        Split notes into batches where each batch's prompt size <= max_chars.

        Uses exponential search starting from a dynamically computed start size
        based on max_chars: increases when it fits, decreases via binary search when it doesn't fit.

        Args:
            prompt_builder: PromptBuilder instance for building prompts.
            selected_fields: Sequence of field names to include in the prompt.
            writable_fields: Sequence of field names that can be filled if empty.
                If None, defaults to selected_fields.
            overwritable_fields: Sequence of field names that can be filled even if already have content.
                If None, defaults to empty list.
            note_type_name: Name of the note type.
            max_chars: Maximum prompt size in characters.

        Returns:
            List of SelectedNotes instances, each representing a batch.
        """
        if not self._note_ids:
            return []

        if writable_fields is None:
            writable_fields = selected_fields

        if overwritable_fields is None:
            overwritable_fields = []

        # Filter to notes with empty fields in writable_fields OR notes with fields in overwritable_fields
        notes_with_fields = self.filter_by_writable_or_overwritable(writable_fields, overwritable_fields)
        if not notes_with_fields:
            return []

        # Get note objects
        notes = notes_with_fields.get_notes()

        batches: list[SelectedNotes] = []
        i = 0  # Current position in notes list
        # Use dynamically computed start size for first batch, then previous batch size
        # Pass total notes to adjust coefficient based on available notes
        last_batch_size = self._compute_start_size(max_chars, len(notes))
        num_prompts_tried = 0

        def build_prompt(test_selected_notes: SelectedNotes) -> str:
            nonlocal num_prompts_tried
            num_prompts_tried += 1
            return prompt_builder.build_prompt(
                target_notes=test_selected_notes,
                selected_fields=selected_fields,
                writable_fields=writable_fields,
                overwritable_fields=overwritable_fields,
                note_type_name=note_type_name,
            )

        while i < len(notes):
            remaining = len(notes) - i

            # Use the size of the last batch as starting point
            # This is efficient because batch sizes tend to be similar
            start_size = min(last_batch_size, remaining)

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

                # If we still haven't found a fitting size, test the smallest size (1)
                # This handles the case where binary search didn't test mid=1 due to iteration limit
                if best_size == 0 and start_size > 1:
                    # Test a single note
                    test_batch_note_ids = [note.id for note in notes[i:i+1]]
                    test_selected_notes = self.new_selected_notes(test_batch_note_ids)
                    try:
                        test_prompt = build_prompt(test_selected_notes)
                        test_size = len(test_prompt)
                        if test_size <= max_chars:
                            best_size = 1
                    except Exception as e:
                        # If building fails, treat as too large
                        self.logger.warning(f"Failed to build prompt for single note test: {e}")

            if best_size == 0:
                # Even a single note doesn't fit
                # Check if single note fits alone (for accurate warning)
                single_note_selected_notes = self.new_selected_notes([notes[i].id])
                try:
                    single_prompt = build_prompt(single_note_selected_notes)
                    single_size = len(single_prompt)
                    if single_size > max_chars:
                        self.logger.warning(
                            f"Note {notes[i].id} exceeds maximum prompt size ({single_size} > {max_chars}). Skipping."
                        )
                    else:
                        # This shouldn't happen if our algorithm is correct, but log for debugging
                        self.logger.warning(
                            f"Note {notes[i].id} unexpectedly skipped despite fitting ({single_size} <= {max_chars})."
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
        num_batches = len(batches)
        if batches:
            avg_batch_size = sum(len(batch) for batch in batches) // num_batches
        else:
            avg_batch_size = None
            self.logger.info("No batches created")

        self.batching_stats = BatchingStats(
            num_prompts_tried=num_prompts_tried,
            avg_batch_size=avg_batch_size,
            num_batches=num_batches,
            num_notes_selected=len(notes),
            max_prompt_size=max_chars
        )

        self.logger.info(self.batching_stats)

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

        card_ids = []
        if self._card_ids:
            for note in self.get_notes(note_ids):
                for card_id in note.card_ids():
                    if card_id in self._card_ids:
                        card_ids.append(card_id)

        return SelectedNotes(self.col, note_ids, card_ids, note_cache=self._note_cache, deck_cache=self._deck_cache)

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


    def _get_deck_name_for_card_id(self, card_id: CardId) -> str:
        """
        Get deck name for a card ID, with caching.

        Args:
            card_id: Card ID.

        Returns:
            Deck name (full path) or empty string if card not found.
        """
        if card_id in self._deck_cache:
            return self._deck_cache[card_id]

        card = self.col.get_card(card_id)
        if not card:
            self._deck_cache[card_id] = ""
            return ""

        deck = self.col.decks.get(card.did)
        name = deck["name"] if deck else ""
        self._deck_cache[card_id] = name
        return name


    def _get_all_card_ids(self) -> Sequence[CardId]:
        """Get all card IDs for the selected notes."""

        assert self.col.db

        if self._card_ids:
            return self._card_ids

        return self.col.db.list(
            f"SELECT id FROM cards WHERE nid IN {ids2str(self._note_ids)}"
        )

    def get_most_common_deck(self) -> str:
        """
        Return the full name of most common deck among the selected cards.

        Returns:
            Full deck name (e.g., "Parent::Child") or empty string if no decks found.
        """
        # Count deck frequencies
        deck_counts: dict[str, int] = {}

        sample_size = 500

        card_ids = self._get_all_card_ids()

        # Use card IDs
        if not card_ids:
            return ""

        # Random sampling for >500 cards
        if len(card_ids) > sample_size:
            card_ids = random.sample(card_ids, sample_size)

        for card_id in card_ids:
            deck_name = self._get_deck_name_for_card_id(card_id)
            if deck_name:  # Skip empty deck names
                deck_counts[deck_name] = deck_counts.get(deck_name, 0) + 1

        # Return most common deck or empty string
        if not deck_counts:
            return ""

        return max(deck_counts.items(), key=lambda x: x[1])[0]

    def clear_cache(self) -> None:
        """Clear the note cache."""
        self._note_cache.clear()
        self._deck_cache.clear()

    def __len__(self) -> int:
        """Return the number of notes in the selection."""
        return len(self._note_ids)
