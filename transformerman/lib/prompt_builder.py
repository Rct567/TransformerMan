"""
TransformerMan by Rick Zuidhoek. Licensed under the GNU GPL-3.0.
See <https://www.gnu.org/licenses/gpl-3.0.html> for details.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .xml_parser import escape_xml_content
from .selected_notes import SelectedNotes

if TYPE_CHECKING:
    from collections.abc import Sequence
    from anki.collection import Collection
    from anki.notes import Note, NoteId
    from anki.cards import Card, CardId
    from anki.decks import DeckId


class PromptBuilder:
    """Builds prompts for the language model to fill empty fields."""

    field_instructions: dict[str, str]
    deck_cache: dict[int, str]
    note_cache: dict[NoteId, Note]
    card_cache: dict[CardId, Card]
    find_notes_cache: dict[str, Sequence[NoteId]]
    note_xml_cache: dict[tuple[NoteId, tuple[str, ...]], str]

    def __init__(self, col: Collection) -> None:
        self.col = col
        self.field_instructions = {}
        self.deck_cache = {}
        self.note_cache = {}
        self.card_cache = {}
        self.find_notes_cache = {}
        self.note_xml_cache = {}

    def clear_cache(self) -> None:
        """Clear the internal caches."""
        self.deck_cache.clear()
        self.note_cache.clear()
        self.card_cache.clear()
        self.find_notes_cache.clear()
        self.note_xml_cache.clear()

    def _get_note(self, note_id: NoteId) -> Note:
        """Get a note from cache or collection."""
        if note_id in self.note_cache:
            return self.note_cache[note_id]

        note = self.col.get_note(note_id)
        self.note_cache[note_id] = note
        return note

    def _get_deck_name(self, deck_id: DeckId) -> str:
        """Get deck name from cache or collection."""
        if deck_id in self.deck_cache:
            return self.deck_cache[deck_id]

        deck = self.col.decks.get(deck_id)
        name = deck["name"] if deck else ""
        self.deck_cache[deck_id] = name
        return name

    def _get_deck_name_for_note(self, note: Note) -> str:
        """Get deck name for a note."""
        card_ids = note.card_ids()
        if not card_ids:
            return ""

        card = self._get_card(card_ids[0])
        return self._get_deck_name(card.did)


    def _format_note_as_xml(self, note: Note, fields_included: Sequence[str]) -> str:
        """Format a single note as XML with caching."""
        # Create cache key
        cache_key = (note.id, tuple(fields_included))

        # Check cache
        if cache_key in self.note_xml_cache:
            return self.note_xml_cache[cache_key]

        # Get deck name
        deck_name = self._get_deck_name_for_note(note)

        # Build XML lines for this note
        lines = [
            f'  <note nid="{note.id}" deck="{escape_xml_content(deck_name)}">'
        ]

        # Add included fields
        for field_name in fields_included:
            if field_name in note:
                field_value = note[field_name]
                escaped_value = escape_xml_content(field_value)
                lines.append(f'    <field name="{escape_xml_content(field_name)}">{escaped_value}</field>')

        lines.append('  </note>')

        # Join lines and cache
        result = '\n'.join(lines)
        self.note_xml_cache[cache_key] = result
        return result

    def _get_card(self, card_id: CardId) -> Card:
        """Get a card from cache or collection."""
        if card_id in self.card_cache:
            return self.card_cache[card_id]

        card = self.col.get_card(card_id)
        self.card_cache[card_id] = card
        return card

    def _find_notes(self, query: str) -> Sequence[NoteId]:
        """Find note IDs using cache or collection."""
        if query in self.find_notes_cache:
            return self.find_notes_cache[query]

        note_ids = self.col.find_notes(query)
        self.find_notes_cache[query] = note_ids
        return note_ids

    def update_field_instructions(self, field_instructions: dict[str, str]) -> None:
        """Update the field instructions for this prompt builder."""
        self.field_instructions = field_instructions

    def build_prompt(
        self,
        target_notes: SelectedNotes,
        selected_fields: Sequence[str],
        writable_fields: Sequence[str] | None,
        note_type_name: str = "",
    ) -> str:
        """
        Build a complete prompt for the LM including examples and target notes.
        Precondition: `target_notes` must contain at least one note with an empty field;
        """

        if writable_fields is None:
            target_fields = selected_fields
        else:
            target_fields = writable_fields

        assert target_notes.has_note_with_empty_field(target_fields)

        # Get example notes
        example_notes = self._select_example_notes(target_notes, selected_fields, note_type_name)

        # Build prompt parts
        prompt_parts = [
            "You are an Anki note assistant. Your task is to fill empty fields in notes based on context.",
            "",
            "Instructions:",
        ]

        # Add field-specific instructions
        if self.field_instructions:
            for field_name, instruction in self.field_instructions.items():
                if field_name in selected_fields:
                    prompt_parts.append(f"- For field '{field_name}': {instruction}")
        else:
            # Adjust instruction based on whether examples are available
            if example_notes:
                prompt_parts.append("- Fill empty fields intelligently based on field names, deck context, and examples.")
            else:
                prompt_parts.append("- Fill empty fields intelligently based on field names and deck context.")

            if writable_fields:
                if len(writable_fields) == 1:
                    prompt_parts.append(f"- Fill in only the following empty field: \"{writable_fields[0]}\".")
                else:
                    fields_str = ", ".join(f"'{f}'" for f in writable_fields)
                    prompt_parts.append(f"- Fill in only the following empty fields: {fields_str}.")

        # Only include examples section if there are examples
        if example_notes:
            prompt_parts.extend(
                [
                    "",
                    "Here are some example notes from the collection:",
                    "",
                    self._format_notes_as_xml(example_notes, note_type_name, selected_fields),
                    "",
                ]
            )

        # Get target notes and filter to only include those with empty fields
        notes_with_empty_fields = [note for note in target_notes.get_notes() if SelectedNotes.has_empty_field(note, target_fields)]

        # Add target notes
        if not notes_with_empty_fields:
            raise ValueError("No notes with empty fields found")

        if writable_fields:
            if len(writable_fields) == 1:
                prompt_parts.append("Please fill the specified empty field (\"{}\") in the following notes and return them in the same XML format:".format(writable_fields[0]))
            else:
                prompt_parts.append("Please fill the specified empty fields in the following notes and return them in the same XML format:")
        else:
            prompt_parts.append("Please fill the empty fields in the following notes and return them in the same XML format:")

        prompt_parts.extend(
            [
                "",
                self._format_notes_as_xml(notes_with_empty_fields, note_type_name, selected_fields),
            ]
        )

        return "\n".join(prompt_parts)

    def _select_example_notes(
        self,
        target_notes: SelectedNotes,
        selected_fields: Sequence[str],
        note_type_name: str,
        max_examples: int = 3,
    ) -> Sequence[Note]:
        """
        Select up to max_examples example notes from the collection.

        Selection criteria (in order):
        1. Number of non-empty selected fields (higher first)
        2. Total word count in selected fields (higher first)
        3. Preference for notes from the same deck as target notes

        Args:
            target_notes: SelectedNotes instance (to avoid selecting them as examples).
            selected_fields: Sequence of field names to consider.
            note_type_name: Name of the note type.
            max_examples: Maximum number of examples to return.

        Returns:
            List of example notes.
        """
        # Get target note IDs
        target_note_ids = set(target_notes.get_ids())

        # Find the note type
        notetype = self.col.models.by_name(note_type_name)
        if not notetype:
            return []

        def find_candidate_notes(query: str) -> list[NoteId]:
            note_ids = self._find_notes(query)
            # Filter out target notes
            return [nid for nid in note_ids if nid not in target_note_ids]

        refined_query_parts = [f'"note:{note_type_name}"']
        for field in selected_fields:
            refined_query_parts.append(f"-{field}:") # filter out notes with empty selected fields
        refined_query = " ".join(refined_query_parts)

        candidate_note_ids = []

        # Attempt 1/3 Use deck and refined query

        deck_name = target_notes.get_most_common_deck()

        if deck_name:
            candidate_note_ids = find_candidate_notes(refined_query + f' "deck:{deck_name}"')

        # Attempt 2/3 Try just the refined query

        if len(candidate_note_ids) < max_examples:
            existing_ids = set(candidate_note_ids)
            for note_id in find_candidate_notes(refined_query):
                if note_id not in existing_ids:
                    candidate_note_ids.append(note_id)

        # Attempt 3/3 If refined query doesn't produce enough candidate notes, fall back to 'note type' based query

        if len(candidate_note_ids) < max_examples:
            existing_ids = set(candidate_note_ids)
            # Get all note IDs of this type
            for note_id in find_candidate_notes(f'"note:{note_type_name}"'):
                if note_id not in existing_ids:
                    candidate_note_ids.append(note_id)

        if not candidate_note_ids:
            return []

        # Score each candidate
        scored_candidates: list[tuple[int, int, Note]] = []

        for nid in candidate_note_ids[:300]:  # Limit to first 300 for performance
            try:
                note = self._get_note(nid)

                # Count non-empty selected fields and words
                non_empty_count = 0
                word_count = 0

                for field in selected_fields:
                    val = note[field]
                    if val and val.strip():
                        non_empty_count += 1
                        word_count += len(val.split())

                if non_empty_count > 0:  # Only consider notes with at least one filled field
                    scored_candidates.append((non_empty_count, word_count, note))

            except Exception:
                continue

        # Sort by non-empty count (desc), then word count (desc)
        scored_candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)

        # Return top examples
        return [note for _, _, note in scored_candidates[:max_examples]]

    def _format_notes_as_xml(
        self,
        notes: Sequence[Note],
        note_type_name: str,
        fields_included: Sequence[str],
    ) -> str:
        """
        Format notes as XML-like structure.

        Args:
            notes: List of notes to format.
            note_type_name: Name of the note type.
            fields_included: Sequence of field names to include.

        Returns:
            XML-like string representation.
        """

        lines = [f'<notes model="{escape_xml_content(note_type_name)}">']

        for note in notes:
            lines.append(self._format_note_as_xml(note, fields_included))

        lines.append("</notes>")

        return "\n".join(lines)
