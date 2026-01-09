"""
TransformerMan by Rick Zuidhoek. Licensed under the GNU GPL-3.0.
See <https://www.gnu.org/licenses/gpl-3.0.html> for details.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence
    from anki.collection import Collection
    from anki.models import NotetypeId, NotetypeDict
    from anki.notes import Note, NoteId
    from anki.cards import Card, CardId
    from anki.decks import DeckId


class NoteModel:
    """Wrapper for Anki's note type (model)."""

    def __init__(self, col: Collection, data: NotetypeDict) -> None:
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


class CollectionData:
    """Handles caching for common collection data operations."""

    def __init__(self, col: Collection) -> None:
        self.col = col
        self.note_cache: dict[NoteId, Note] = {}
        self.card_cache: dict[CardId, Card] = {}
        self.deck_cache: dict[DeckId, str] = {}  # deck_id to deck_name
        self.find_notes_cache: dict[str, Sequence[NoteId]] = {}

    def get_note(self, note_id: NoteId) -> Note:
        """Get a note from cache or collection."""
        if note_id in self.note_cache:
            return self.note_cache[note_id]

        note = self.col.get_note(note_id)
        self.note_cache[note_id] = note
        return note

    def get_card(self, card_id: CardId) -> Card:
        """Get a card from cache or collection."""
        if card_id in self.card_cache:
            return self.card_cache[card_id]

        card = self.col.get_card(card_id)
        self.card_cache[card_id] = card
        return card

    def get_deck_name(self, deck_id: DeckId) -> str:
        """Get deck name from cache or collection."""
        if deck_id in self.deck_cache:
            return self.deck_cache[deck_id]

        deck = self.col.decks.get(deck_id)
        name = deck["name"] if deck else ""
        self.deck_cache[deck_id] = name
        return name

    def find_notes(self, query: str) -> Sequence[NoteId]:
        """Find note IDs using cache or collection."""
        if query in self.find_notes_cache:
            return self.find_notes_cache[query]

        note_ids = self.col.find_notes(query)
        self.find_notes_cache[query] = note_ids
        return note_ids

    def get_deck_name_for_note(self, note: Note) -> str:
        """Get deck name for a note."""
        card_ids = note.card_ids()
        if not card_ids:
            return ""

        card = self.get_card(card_ids[0])
        return self.get_deck_name(card.did)

    def get_note_model_by_name(self, name: str) -> NoteModel | None:
        """Get note model by name."""
        data = self.col.models.by_name(name)
        if data:
            return NoteModel(self.col, data)
        return None
