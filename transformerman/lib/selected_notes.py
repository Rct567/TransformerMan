"""
TransformerMan by Rick Zuidhoek. Licensed under the GNU GPL-3.0.
See <https://www.gnu.org/licenses/gpl-3.0.html> for details.
"""

from __future__ import annotations

import logging
import math
import random
from typing import TYPE_CHECKING, Callable, NamedTuple

from anki.utils import ids2str

if TYPE_CHECKING:
    from collections.abc import Sequence
    from anki.collection import Collection
    from anki.models import NotetypeId, NotetypeDict
    from anki.notes import Note, NoteId
    from anki.cards import CardId
    from ..ui.field_widgets import FieldSelection
    from .prompt_builder import PromptBuilder


class BatchingStats(NamedTuple):
    initial_batch_size: int  # noqa: F841
    num_prompts_tried: int
    median_batch_size: int | None
    avg_batch_size: int | None
    num_batches: int
    num_notes_selected: int  # noqa: F841
    avg_note_size: int
    max_prompt_size: int


class NoteModel:
    """Wrapper for Anki's note type (model)."""

    def __init__(self, col: Collection, data: NotetypeDict):
        self.col = col
        self.data = data

    @classmethod
    def by_name(cls, col: Collection, name: str) -> NoteModel | None:
        data = col.models.by_name(name)
        if data:
            return cls(col, data)
        return None

    @classmethod
    def by_id(cls, col: Collection, mid: NotetypeId) -> NoteModel | None:
        data = col.models.get(mid)
        if data:
            return cls(col, data)
        return None

    def get_fields(self) -> list[str]:
        """Return the names of the fields in this note model."""
        return [field["name"] for field in self.data["flds"]]

    @property
    def id(self) -> NotetypeId:
        return self.data["id"]

    @property
    def name(self) -> str:
        return self.data["name"]


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
        model = NoteModel.by_name(self.col, note_type_name)
        if not model:
            return []

        filtered_note_ids: list[NoteId] = []

        for nid in self._note_ids:
            note = self.get_note(nid)
            if note.mid == model.id:
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
            model = NoteModel.by_id(self.col, note.mid)
            if model:
                name = model.name
                counts[name] = counts.get(name, 0) + 1

        # Sort by count descending
        return dict(sorted(counts.items(), key=lambda x: x[1], reverse=True))

    def predict_batch_size(self, max_prompt_size: int, num_notes_selected: int, avg_note_size: float) -> int:
        """
        Batch size prediction using continuous mathematical formula.

        Returns:
            Predicted batch size (notes per batch) to use as starting point
        """
        # Per-note overhead for metadata, separators, formatting
        overhead = 15
        # Base efficiency: increases with note size using smooth exponential curve
        # Approaches ~49% for very large notes, starts at ~31% for very small notes
        # The larger the note, the less the fixed overhead matters
        base_efficiency = 0.49 - 0.18 * math.exp(-avg_note_size / 530)
        # Prompt size scaling: larger prompts are more efficient
        # Use square root scaling for smooth, modest gains
        prompt_scale = math.sqrt(max_prompt_size / 100000)
        # Clamp to reasonable bounds (0.8x to 1.25x)
        prompt_scale = max(0.80, min(1.25, prompt_scale))
        # Combined efficiency with conservative multiplier
        # 0.80 multiplier makes predictions ~20% more pessimistic
        # This targets the lower of median/avg batch size
        efficiency = base_efficiency * prompt_scale * 0.80
        # Calculate total effective size with overhead
        effective_size_per_note = avg_note_size + overhead
        total_effective_size = num_notes_selected * effective_size_per_note
        # Calculate usable prompt space
        usable_prompt_size = max_prompt_size * efficiency
        # Calculate batches needed (minimum 1)
        batches = max(1, math.ceil(total_effective_size / usable_prompt_size))
        # Return the batch SIZE (notes per batch), not number of batches
        batch_size = max(1, num_notes_selected // batches)
        return batch_size

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

    def _test_batch_size(
        self,
        notes: Sequence[Note],
        start_idx: int,
        batch_size: int,
        build_prompt: Callable[[SelectedNotes], str],
        max_chars: int,
    ) -> tuple[bool, int]:
        """
        Test if a batch of given size fits within max_chars.

        Args:
            notes: Sequence of notes to test.
            start_idx: Starting index in notes sequence.
            batch_size: Size of batch to test.
            build_prompt: Function to build prompt for testing.
            max_chars: Maximum allowed prompt size.

        Returns:
            Tuple of (fits: bool, actual_size: int).
            actual_size is -1 if prompt building failed.
        """
        test_batch_note_ids = [note.id for note in notes[start_idx:start_idx+batch_size]]
        test_selected_notes = self.new_selected_notes(test_batch_note_ids)

        try:
            test_prompt = build_prompt(test_selected_notes)
            test_size = len(test_prompt)
            return test_size <= max_chars, test_size
        except Exception as e:
            self.logger.warning(f"Failed to build prompt for batch sizing: {e}")
            return False, -1

    def _perform_binary_search_for_batch_size(
        self,
        notes: Sequence[Note],
        start_idx: int,
        low: int,
        high: int,
        build_prompt: Callable[[SelectedNotes], str],
        max_chars: int,
    ) -> int:
        """
        Perform binary search to find maximum batch size that fits within max_chars.

        Args:
            notes: Sequence of notes to search in.
            start_idx: Starting index in notes sequence.
            low: Minimum batch size to consider.
            high: Maximum batch size to consider.
            build_prompt: Function to build prompt for testing.
            max_chars: Maximum allowed prompt size.

        Returns:
            Maximum batch size that fits, or 0 if none found.
        """
        best_size = 0
        iteration = 0

        while low <= high and iteration < self.MAX_BINARY_SEARCH_ITERATIONS:
            iteration += 1
            mid = (low + high) // 2
            fits, _ = self._test_batch_size(notes, start_idx, mid, build_prompt, max_chars)

            if fits:
                # Fits, try larger
                best_size = mid
                low = mid + 1
            else:
                # Too large, try smaller
                high = mid - 1

        return best_size

    def batched_by_prompt_size(
        self,
        prompt_builder: PromptBuilder,
        field_selection: FieldSelection,
        note_type_name: str,
        max_chars: int,
        max_examples: int
    ) -> list[SelectedNotes]:
        """
        Split notes into batches where each batch's prompt size <= max_chars.

        Uses exponential search starting from a dynamically computed start size
        based on max_chars: increases when it fits, decreases via binary search when it doesn't fit.

        Args:
            prompt_builder: PromptBuilder instance for building prompts.
            field_selection: FieldSelection containing selected, writable, and overwritable fields.
            note_type_name: Name of note type.
            max_chars: Maximum prompt size in characters.

        Returns:
            List of SelectedNotes instances, each representing a batch.
        """

        if not self._note_ids:
            return []

        # Filter to notes with empty fields in writable_fields OR notes with fields in overwritable_fields
        notes_with_fields = self.filter_by_writable_or_overwritable(field_selection.writable, field_selection.overwritable)
        if not notes_with_fields:
            return []

        # Get note objects
        notes = notes_with_fields.get_notes()

        sample = random.sample(notes, min(500, len(notes)))
        avg_note_size = sum(sum(len(note[fields_name]) for fields_name in field_selection.selected) for note in sample) // len(sample)

        predicted_batch_size = self.predict_batch_size(max_chars, len(notes), avg_note_size)

        batches: list[SelectedNotes] = []
        i = 0  # Current position in notes list
        # Use dynamically computed start size for first batch, then previous batch size
        last_batch_size = predicted_batch_size
        num_prompts_tried = 0

        def build_prompt(test_selected_notes: SelectedNotes) -> str:
            nonlocal num_prompts_tried
            num_prompts_tried += 1
            return prompt_builder.build_prompt(
                target_notes=test_selected_notes,
                field_selection=field_selection,
                max_examples=max_examples,
                note_type_name=note_type_name,
            )

        while i < len(notes):
            remaining = len(notes) - i

            # Use the size of the last batch as starting point
            # This is efficient because batch sizes tend to be similar
            start_size = min(last_batch_size, remaining)

            # First check if start_size fits
            start_fits, _ = self._test_batch_size(notes, i, start_size, build_prompt, max_chars)

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

                    fits, _ = self._test_batch_size(notes, i, next_size, build_prompt, max_chars)

                    if fits:
                        # Still fits, continue exponential search
                        low = next_size  # Update lower bound (last known fitting size)
                        high = next_size
                    else:
                        # Doesn't fit, found upper bound
                        high = next_size
                        break

                # Now binary search between low and high to find max fitting size
                # low is last known fitting size, high is first known non-fitting size
                best_size = low

                # If we reached end of notes without finding non-fitting size, use remaining
                if high == low and high < remaining:
                    best_size = remaining
                else:
                    # Binary search between low and high to find max fitting size
                    best_size = self._perform_binary_search_for_batch_size(
                        notes, i, low, high, build_prompt, max_chars
                    )
                    if best_size == 0:
                        best_size = low  # Fall back to last known good size
            else:
                # start_size doesn't fit, binary search between 1 and start_size-1
                best_size = self._perform_binary_search_for_batch_size(
                    notes, i, 1, start_size - 1, build_prompt, max_chars
                )

                # If we still haven't found a fitting size, test the smallest size (1)
                # This handles the case where binary search didn't test mid=1 due to iteration limit
                if best_size == 0 and start_size > 1:
                    fits, _ = self._test_batch_size(notes, i, 1, build_prompt, max_chars)
                    if fits:
                        best_size = 1

            if best_size == 0:
                # Even a single note doesn't fit - check for accurate warning
                fits, actual_size = self._test_batch_size(notes, i, 1, build_prompt, max_chars)
                if actual_size > max_chars:
                    self.logger.warning(
                        f"Note {notes[i].id} exceeds maximum prompt size ({actual_size} > {max_chars}). Skipping."
                    )
                elif fits:
                    # This shouldn't happen if our algorithm is correct, but log for debugging
                    self.logger.warning(
                        f"Note {notes[i].id} unexpectedly skipped despite fitting ({actual_size} <= {max_chars})."
                    )

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
            median_batch_size = sorted(len(batch) for batch in batches)[num_batches // 2]
            avg_batch_size = sum(len(batch) for batch in batches) // num_batches
        else:
            median_batch_size = None
            avg_batch_size = None
            self.logger.info("No batches created")

        self.batching_stats = BatchingStats(
            initial_batch_size=predicted_batch_size,
            num_prompts_tried=num_prompts_tried,
            median_batch_size=median_batch_size,
            avg_batch_size=avg_batch_size,
            num_batches=num_batches,
            num_notes_selected=len(notes),
            avg_note_size=avg_note_size,
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
