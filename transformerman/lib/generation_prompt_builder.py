"""
TransformerMan by Rick Zuidhoek. Licensed under the GNU GPL-3.0.
See <https://www.gnu.org/licenses/gpl-3.0.html> for details.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .xml_parser import escape_xml_content
from .prompt_builder import PromptBuilder

if TYPE_CHECKING:
    from anki.collection import Collection
    from .selected_notes import NoteModel, SelectedNotesFromType


class GenerationPromptBuilder(PromptBuilder):
    """Builds prompts for generating new Anki notes."""

    def __init__(self, col: Collection) -> None:
        super().__init__(col)

    def build_prompt(
        self,
        source_text: str,
        note_type: NoteModel,
        deck_name: str,
        target_count: int,
        selected_fields: list[str] | None,
        example_notes: SelectedNotesFromType | None,
        max_examples: int,
    ) -> str:
        """
        Build a prompt for generating new notes.

        Args:
            source_text: The raw text to generate notes from.
            note_type: The target note type.
            deck_name: The target deck name.
            target_count: Number of notes to generate.
            selected_fields: Optional list of fields to include in generation.
            example_notes: Optional selection of notes to use as style examples.
            max_examples: Maximum number of examples to include.

        Returns:
            The complete prompt string.
        """
        all_field_names = note_type.get_fields()
        field_names = selected_fields if selected_fields else all_field_names

        parts = [
            (
                "You are an expert Anki note creator. Your goal is to extract or generate "
                "high-quality learning material from the provided text and format it as Anki notes."
            ),
            "",
            f"Target Note Type: {note_type.name}",
            f"Target Deck: {deck_name}",
            f"Available Fields: {', '.join(field_names)}",
            "",
        ]

        notes_from_examples = {note.id: note for note in example_notes.get_notes()[:max_examples]} if example_notes else {}

        if len(notes_from_examples) < max_examples:
            for note in self.select_example_notes(note_type, None, field_names, max_examples, target_deck_name=deck_name):
                if note.id not in notes_from_examples:
                    notes_from_examples[note.id] = note
                if len(notes_from_examples) >= max_examples:
                    break

        if notes_from_examples:
            parts.append("Here are some existing notes of this type from the collection to show the desired style and level of detail:")
            parts.append(self.format_notes_as_xml(list(notes_from_examples.values()), note_type, field_names))
            parts.append("")

        parts.extend([
            "Source Text/Keywords:",
            f'"{source_text}"',
            "",
            f"Target Number of Notes: {target_count}",
            "",
            f"Please generate exactly {target_count} new Anki notes based on the source text above.",
            "",
            "Return the notes in the following XML format. Ensure all fields are filled appropriately.",
            "",
        ])

        fields_xml = [f'    <field name="{escape_xml_content(field)}">...</field>' for field in field_names]

        parts.extend([
            f'<notes model="{escape_xml_content(note_type.name)}" deck="{escape_xml_content(deck_name)}">',
            "  <note>",
            *fields_xml,
            "  </note>",
            "</notes>",
            "",
        ])

        return "\n".join(parts)
