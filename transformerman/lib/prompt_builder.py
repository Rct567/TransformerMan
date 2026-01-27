"""
TransformerMan by Rick Zuidhoek. Licensed under the GNU GPL-3.0.
See <https://www.gnu.org/licenses/gpl-3.0.html> for details.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .xml_parser import escape_xml_content
from .collection_data import CollectionData, NoteModel

if TYPE_CHECKING:
    from .selected_notes import SelectedNotes
    from collections.abc import Sequence
    from anki.collection import Collection
    from anki.notes import Note, NoteId


class PromptBuilder:
    """Base class for building prompts for the language model."""

    note_xml_cache: dict[tuple[NoteId, tuple[str, ...], tuple[str, ...], bool, bool], str]

    def __init__(self, col: Collection) -> None:
        self.col = CollectionData(col)
        self.note_xml_cache = {}

    def select_example_notes(
        self,
        note_type: NoteModel,
        exclude_notes: SelectedNotes | None,
        selected_fields: Sequence[str],
        max_examples: int,
        target_deck_name: str | None,
    ) -> Sequence[Note]:
        """
        Select up to max_examples example notes from the collection.

        Selection criteria (in order):
        1. Number of non-empty selected fields (higher first)
        2. Total word count in selected fields (higher first)
        3. Preference for notes from the same deck as target notes

        Args:
            note_type: Note type to select examples from.
            exclude_notes: Notes to exclude from the example selection.
            selected_fields: Sequence of field names to consider.
            max_examples: Maximum number of example notes to produce.
            target_deck_name: Deck name to prioritize examples from.
        Returns:
            List of example notes.
        """
        # Get target note IDs
        if exclude_notes is None:
            exclude_note_ids: set[NoteId] = set()
        else:
            exclude_note_ids = set(exclude_notes.get_ids())

        # Find the note type
        model = self.col.get_note_model_by_name(note_type.name)
        if not model:
            return []

        def find_candidate_notes(query: str) -> list[NoteId]:
            note_ids = self.col.find_notes(query)
            # Filter out target notes
            return [nid for nid in note_ids if nid not in exclude_note_ids]

        refined_query_parts = [f'"note:{note_type.name}"']
        for field in selected_fields:
            refined_query_parts.append(f'-"{field}:"')  # filter out notes with empty selected fields
        refined_query = " ".join(refined_query_parts)

        candidate_note_ids = []

        # Attempt 1/3 Use deck and refined query

        if target_deck_name:
            candidate_note_ids = find_candidate_notes(refined_query + f' "deck:{target_deck_name}"')

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
            for note_id in find_candidate_notes(f'"note:{note_type.name}"'):
                if note_id not in existing_ids:
                    candidate_note_ids.append(note_id)

        if not candidate_note_ids:
            return []

        # Score each candidate
        scored_candidates: list[tuple[int, int, Note]] = []

        for nid in candidate_note_ids[:300]:  # Limit to first 300 for performance
            try:
                note = self.col.get_note(nid)

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

    def format_note_as_xml(
        self,
        note: Note,
        fields_included: Sequence[str],
        leave_empty: Sequence[str] | None,
        include_deck: bool = True,
        include_nid: bool = True,
    ) -> str:
        """Format a single note as XML with caching."""
        # Create cache key
        cache_key = (note.id, tuple(fields_included), tuple(leave_empty or []), include_deck, include_nid)
        # Check cache
        if cache_key in self.note_xml_cache:
            return self.note_xml_cache[cache_key]

        # Get deck name
        deck_name = self.col.get_deck_name_for_note(note)

        if include_nid:
            id_attr = f' nid="{note.id}"'
        else:
            id_attr = ""

        # Build XML lines for this note
        if include_deck:
            lines = [f'  <note{id_attr} deck="{escape_xml_content(deck_name)}">']
        else:
            lines = [f"  <note{id_attr}>"]

        # Add included fields
        for field_name in fields_included:
            if field_name in note:
                field_value = note[field_name]
                if leave_empty and field_name in leave_empty:
                    escaped_value = ""
                else:
                    escaped_value = escape_xml_content(field_value)
                lines.append(f'    <field name="{escape_xml_content(field_name)}">{escaped_value}</field>')

        lines.append("  </note>")

        # Join lines and cache
        result = "\n".join(lines)
        self.note_xml_cache[cache_key] = result
        return result

    def format_notes_as_xml(
        self,
        notes: Sequence[Note],
        note_type: NoteModel,
        fields_included: Sequence[str],
        leave_empty: Sequence[str] | None = None,
        include_nid: bool = True,
    ) -> str:
        """
        Format notes as XML-like structure.

        Args:
            notes: List of notes to format.
            note_type: Note type of the notes.
            fields_included: Sequence of field names to include.
            leave_empty: Included field names to leave empty (optional).
            include_nid: Whether to include note IDs in the output.

        Returns:
            XML-like string representation.
        """

        assert not leave_empty or all(field in fields_included for field in leave_empty)

        # Check if all notes have the same deck
        common_deck: str | None = None
        if notes:
            first_deck = self.col.get_deck_name_for_note(notes[0])
            all_same_deck = all(self.col.get_deck_name_for_note(note) == first_deck for note in notes)
            if all_same_deck:
                common_deck = first_deck

        # Build root element
        if common_deck:
            lines = [f'<notes model="{escape_xml_content(note_type.name)}" deck="{escape_xml_content(common_deck)}">']
        else:
            lines = [f'<notes model="{escape_xml_content(note_type.name)}">']

        # Add notes
        for note in notes:
            lines.append(
                self.format_note_as_xml(note, fields_included, leave_empty, include_deck=(common_deck is None), include_nid=include_nid)
            )

        lines.append("</notes>")

        return "\n".join(lines)
