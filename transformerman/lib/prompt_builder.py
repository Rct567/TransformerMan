"""
TransformerMan by Rick Zuidhoek. Licensed under the GNU GPL-3.0.
See <https://www.gnu.org/licenses/gpl-3.0.html> for details.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .xml_parser import escape_xml_content
from .selected_notes import SelectedNotes

if TYPE_CHECKING:
    from anki.collection import Collection
    from anki.notes import Note


class PromptBuilder:
    """Builds prompts for the language model to fill empty fields."""

    def __init__(self, field_instructions: dict[str, str] | None = None) -> None:
        self.field_instructions = field_instructions or {}

    def build_prompt(
        self,
        col: Collection,
        target_notes: SelectedNotes,
        selected_fields: set[str],
        note_type_name: str,
    ) -> str:
        """
        Build a complete prompt for the LM including examples and target notes.
        """
        # Get example notes
        example_notes = self._select_example_notes(col, target_notes, selected_fields, note_type_name)

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
            prompt_parts.append("- Fill empty fields intelligently based on field names, deck context, and examples.")

        prompt_parts.extend([
            "",
            "Here are some example notes from the collection:",
            "",
        ])

        # Add example notes
        if example_notes:
            prompt_parts.append(self._format_notes_as_xml(example_notes, note_type_name, selected_fields))
            prompt_parts.append("")
        else:
            prompt_parts.append("(No examples available)")
            prompt_parts.append("")

        # Get target notes and filter to only include those with empty fields
        target_note_objects = target_notes.get_notes(target_notes.note_ids)
        notes_with_empty_fields = [
            note for note in target_note_objects
            if SelectedNotes.has_empty_field(note, selected_fields)
        ]

        # Add target notes
        if not notes_with_empty_fields:
            raise ValueError("No notes with empty fields found")

        prompt_parts.extend([
            "Please fill the empty fields in the following notes and return them in the same XML format:",
            "",
            self._format_notes_as_xml(notes_with_empty_fields, note_type_name, selected_fields),
        ])

        return "\n".join(prompt_parts)

    def _select_example_notes(
        self,
        col: Collection,
        target_notes: SelectedNotes,
        selected_fields: set[str],
        note_type_name: str,
        max_examples: int = 3,
    ) -> list[Note]:
        """
        Select up to max_examples example notes from the collection.

        Selection criteria (in order):
        1. Number of non-empty selected fields (higher first)
        2. Total word count in selected fields (higher first)
        3. Preference for notes from the same deck as target notes

        Args:
            col: Anki collection.
            target_notes: SelectedNotes instance (to avoid selecting them as examples).
            selected_fields: Set of field names to consider.
            note_type_name: Name of the note type.
            max_examples: Maximum number of examples to return.

        Returns:
            List of example notes.
        """
        # Get target note IDs
        target_note_ids = set(target_notes.note_ids)

        # Find the note type
        notetype = None
        for nt in col.models.all():
            if nt['name'] == note_type_name:
                notetype = nt
                break

        if not notetype:
            return []

        # Get all note IDs of this type
        note_ids = col.find_notes(f'"note:{note_type_name}"')

        # Filter out target notes
        candidate_note_ids = [nid for nid in note_ids if nid not in target_note_ids]

        if not candidate_note_ids:
            return []

        # Score each candidate
        scored_candidates: list[tuple[int, int, Note]] = []

        for nid in candidate_note_ids[:100]:  # Limit to first 100 for performance
            try:
                note = col.get_note(nid)

                # Count non-empty selected fields
                non_empty_count = sum(1 for field in selected_fields if note[field].strip())

                # Count total words in selected fields
                word_count = sum(len(note[field].split()) for field in selected_fields if note[field].strip())

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
        notes: list[Note],
        note_type_name: str,
        fields_included: set[str],
    ) -> str:
        """
        Format notes as XML-like structure.

        Args:
            notes: List of notes to format.
            note_type_name: Name of the note type.
            fields_included: Set of field names to include.

        Returns:
            XML-like string representation.
        """

        lines = [f'<notes model="{escape_xml_content(note_type_name)}">']

        for note in notes:
            # Get deck name
            card_ids = note.card_ids()
            deck_name = ""
            if card_ids:
                try:
                    card = note.col.get_card(card_ids[0])
                    deck = note.col.decks.get(card.did)
                    if deck:
                        deck_name = deck['name']
                except Exception:
                    pass

            lines.append(f'  <note nid="{note.id}" deck="{escape_xml_content(deck_name)}">')

            # Add included fields
            for field_name in fields_included:
                if field_name in note:
                    field_value = note[field_name]
                    escaped_value = escape_xml_content(field_value)
                    lines.append(f'    <field name="{escape_xml_content(field_name)}">{escaped_value}</field>')

            lines.append('  </note>')

        lines.append('</notes>')

        return '\n'.join(lines)
