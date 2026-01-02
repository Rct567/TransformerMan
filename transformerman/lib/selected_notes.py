"""
TransformerMan by Rick Zuidhoek. Licensed under the GNU GPL-3.0.
See <https://www.gnu.org/licenses/gpl-3.0.html> for details.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from typing_extensions import Self

from anki.utils import ids2str

from .utilities import evenly_spaced_sample, override

from .notes_batching import BatchingStats, batched_by_prompt_size

if TYPE_CHECKING:
    from collections.abc import Sequence
    from anki.collection import Collection
    from anki.models import NotetypeId, NotetypeDict
    from anki.notes import Note, NoteId
    from anki.cards import CardId
    from ..ui.field_widgets import FieldSelection
    from .prompt_builder import PromptBuilder


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

    def __init__(
        self,
        col: Collection,
        note_ids: Sequence[NoteId],
        card_ids: Sequence[CardId] | None = None,
        note_cache: dict[NoteId, Note] | None = None,
        deck_cache: dict[CardId, str] | None = None,
        _parent: SelectedNotes | None = None,
    ) -> None:
        """Initialize with collection and selected note IDs and optional card IDs."""
        self.col = col
        self._note_ids = note_ids
        self._card_ids = card_ids if card_ids else None  # these might represent cards selected by the user
        self._note_cache = note_cache if note_cache else {}
        self._deck_cache = deck_cache if deck_cache else {}
        self.logger = logging.getLogger(__name__)
        self.batching_stats = None
        self._parent = _parent

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

    def get_selected_card_ids(self) -> Sequence[CardId] | None:
        """Return the card IDs in the selection, or None if not available."""
        return self._card_ids

    def filter_by_note_type(self, note_type: NoteModel) -> SelectedNotesFromType:
        """
        Filter notes by note type.

        Args:
            note_type: Note type to filter by.

        Returns:
            SelectedNotesFromType containing only notes of the specified note type.
        """
        filtered_note_ids: list[NoteId] = []

        for nid in self._note_ids:
            note = self.get_note(nid)
            if note.mid == note_type.id:
                filtered_note_ids.append(nid)

        return SelectedNotesFromType(
            self.col,
            filtered_note_ids,
            note_type,
            self._card_ids,
            self._note_cache,
            self._deck_cache,
            _parent=self,
        )

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

    def filter_by_writable_or_overwritable(
        self,
        writable_fields: Sequence[str],
        overwritable_fields: Sequence[str],
    ) -> Self:
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
            has_empty_writable = any(field in note and not note[field].strip() for field in writable_set)
            # Check if note has field in overwritable_fields
            has_overwritable = any(field in note for field in overwritable_set)

            if has_empty_writable or has_overwritable:
                filtered_note_ids.append(nid)

        return self.new_selected_notes(filtered_note_ids)

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

    def new_selected_notes(self, note_ids: Sequence[NoteId]) -> Self:
        """
        Get a new SelectedNotes instance containing only the specified note IDs.

        Args:
            note_ids: Sequence of note IDs.

        Returns:
            New SelectedNotes instance.
        """
        return self._new_sub_selection(self, note_ids)

    @classmethod
    def _new_sub_selection(cls, selected_notes: SelectedNotes, note_ids: Sequence[NoteId]) -> Self:
        """
        Create a new instance of the class from an existing SelectedNotes instance and a list of note IDs.

        Args:
            selected_notes: The existing SelectedNotes instance.
            note_ids: The list of note IDs to include in the new sub selection instance.
            _parent: Optional parent selection. If None, uses selected_notes.

        Returns:
            A new instance of the class.
        """
        assert len(note_ids) <= len(selected_notes._note_ids)
        if selected_notes._card_ids:
            original_card_ids_set = set(selected_notes._card_ids)
            new_card_ids = [card_id for card_id in selected_notes._get_card_ids_from_notes(note_ids) if card_id in original_card_ids_set]
        else:
            new_card_ids = None
        return cls(
            selected_notes.col,
            note_ids,
            new_card_ids,
            note_cache=selected_notes._note_cache,
            deck_cache=selected_notes._deck_cache,
            _parent=selected_notes,
        )

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

    def filter_by_empty_field(self, selected_fields: Sequence[str]) -> Self:
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

    def _get_card_ids_from_notes(self, note_ids: Sequence[NoteId]) -> Sequence[CardId]:
        """Get card IDs associated with the given note IDs."""

        assert self.col.db

        return self.col.db.list(f"SELECT id FROM cards WHERE nid IN {ids2str(note_ids)}")

    def _get_all_card_ids(self) -> Sequence[CardId]:
        """Get all card IDs for the selected notes (independent of selected cards)."""

        if self.get_selected_card_ids():
            raise ValueError("Are you sure you don't need to use get_selected_card_ids()?")

        return self._get_card_ids_from_notes(self._note_ids)

    def get_most_common_deck(self) -> str:
        """
        Return the full name of most common deck among the selected cards.

        Returns:
            Full deck name (e.g., "Parent::Child") or empty string if no decks found.
        """
        # Count deck frequencies
        deck_counts: dict[str, int] = {}

        sample_size = 500

        card_ids = self.get_selected_card_ids()

        if not card_ids:
            card_ids = self._get_all_card_ids()

        # Use card IDs
        if not card_ids:
            return ""

        # Random sampling for >500 cards
        if len(card_ids) > sample_size:
            card_ids = evenly_spaced_sample(card_ids, sample_size)

        for card_id in card_ids:
            deck_name = self._get_deck_name_for_card_id(card_id)
            if deck_name:  # Skip empty deck names
                deck_counts[deck_name] = deck_counts.get(deck_name, 0) + 1

        # Return most common deck or empty string
        if not deck_counts:
            return ""

        return max(deck_counts.items(), key=lambda x: x[1])[0]

    def clear_cache(self, clear_notes_cache: bool = True, clear_deck_cache: bool = True) -> None:
        """Clear the cache for notes and/or decks."""
        if clear_notes_cache:
            self._note_cache.clear()
        if clear_deck_cache:
            self._deck_cache.clear()

    def parent(self) -> SelectedNotes | None:  # noqa
        """Return to the previous selection in the chain (jQuery-style)."""
        return self._parent

    def __len__(self) -> int:
        """Return the number of notes in the selection."""
        return len(self._note_ids)


class SelectedNotesBatch(SelectedNotes):
    pass


class SelectedNotesFromType(SelectedNotes):
    """SelectedNotes that also contains the NoteModel.

    This class is useful when you need to pass both note_type and selected_notes
    together, eliminating the need for two separate parameters.
    """

    def __init__(
        self,
        col: Collection,
        note_ids: Sequence[NoteId],
        note_type: NoteModel,
        card_ids: Sequence[CardId] | None = None,
        note_cache: dict[NoteId, Note] | None = None,
        deck_cache: dict[CardId, str] | None = None,
        _parent: SelectedNotes | None = None,
    ) -> None:
        super().__init__(col, note_ids, card_ids, note_cache, deck_cache, _parent)
        self.note_type = note_type

    @override
    def new_selected_notes(self, note_ids: Sequence[NoteId]) -> SelectedNotesFromType:
        """Override to preserve note_type when creating sub-selections."""
        base = SelectedNotesFromType._new_sub_selection(self, note_ids)
        base.note_type = self.note_type
        return base

    def new_selected_notes_batch(self, note_ids: Sequence[NoteId]) -> SelectedNotesBatch:
        """Get a new batch containing only the specified note IDs. (note_type is not needed for batches)"""
        return SelectedNotesBatch._new_sub_selection(self, note_ids)

    def batched_by_prompt_size(
        self,
        prompt_builder: PromptBuilder,
        field_selection: FieldSelection,
        max_chars: int,
        max_examples: int,
    ) -> list[SelectedNotesBatch]:
        """Batch notes by maximum prompt size."""

        if not self.get_ids():
            return []

        # Filter to notes with empty fields in writable_fields OR notes with fields in overwritable_fields
        notes_with_fields = self.filter_by_writable_or_overwritable(field_selection.writable, field_selection.overwritable)
        if not notes_with_fields:
            return []

        # Set parent so batches return to self (not the intermediate filtered result)
        # this might not be needed (?)
        notes_with_fields._parent = self

        batches, self.batching_stats = batched_by_prompt_size(
            notes_with_fields, prompt_builder, field_selection, max_chars, max_examples, self.logger
        )

        self.logger.info(self.batching_stats)

        return batches
