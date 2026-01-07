"""
TransformerMan by Rick Zuidhoek. Licensed under the GNU GPL-3.0.
See <https://www.gnu.org/licenses/gpl-3.0.html> for details.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .prompt_builder import PromptBuilder
from .selected_notes import SelectedNotes, SelectedNotesFromType

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from anki.collection import Collection
    from anki.notes import Note
    from ..ui.field_widgets import FieldSelection


class TransformPromptTemplate:
    def __init__(
        self,
        field_instructions: dict[str, str],
        fields_to_fill: Sequence[str],
        formatted_examples_xml: str,
    ) -> None:
        self.field_instructions = field_instructions
        self.fields_to_fill = fields_to_fill
        self.formatted_examples_xml = formatted_examples_xml

    def introduction_section(self, field_instructions: dict[str, str], fields_to_fill: Sequence[str], has_examples: bool) -> list[str]:
        parts = [
            "You are an Anki note assistant. Your task is to fill empty fields in notes based on context.",
            "",
            "Instructions:",
        ]

        # Add field-specific instructions (only for fields to be filled)
        if field_instructions:
            for field_name, instruction in field_instructions.items():
                if field_name in fields_to_fill:
                    parts.append(f"- For field '{field_name}': {instruction}")
        else:
            # Adjust instruction based on whether examples are available
            if has_examples:
                parts.append("- Fill empty fields intelligently based on field names, deck context, and examples.")
            else:
                parts.append("- Fill empty fields intelligently based on field names and deck context.")

            if fields_to_fill:
                if len(fields_to_fill) == 1:
                    parts.append(f'- Fill in only the following empty field: "{fields_to_fill[0]}".')
                else:
                    fields_str = ", ".join(f"'{f}'" for f in fields_to_fill)
                    parts.append(f"- Fill in only the following empty fields: {fields_str}.")
        return parts

    def examples_section(self) -> list[str]:
        if not self.formatted_examples_xml:
            return []

        return [
            "",
            "Here are some example notes from the collection:",
            "",
            self.formatted_examples_xml,
            "",
        ]

    def target_notes_section(self, formatted_target_notes_xml: str) -> list[str]:
        if self.fields_to_fill:
            if len(self.fields_to_fill) == 1:
                instruction = (
                    f'Please fill the specified empty field ("{self.fields_to_fill[0]}") in the following '
                    "notes and return them in the same XML format:"
                )
            else:
                instruction = "Please fill the specified empty fields in the following notes and return them in the same XML format:"
        else:
            instruction = "Please fill the empty fields in the following notes and return them in the same XML format:"

        return [
            instruction,
            "",
            formatted_target_notes_xml,
        ]

    def render(self, formatted_target_notes_xml: str) -> str:
        """Render the complete prompt as a string."""
        parts = []

        # Introduction section
        has_examples = bool(self.formatted_examples_xml)
        parts.extend(self.introduction_section(self.field_instructions, self.fields_to_fill, has_examples))

        # Examples section
        parts.extend(self.examples_section())

        # Target notes section
        parts.extend(self.target_notes_section(formatted_target_notes_xml))

        return "\n".join(parts)


class TransformPromptBuilder(PromptBuilder):
    """Builds prompts for the language model to fill empty fields."""

    field_instructions: dict[str, str]

    def __init__(self, col: Collection) -> None:
        super().__init__(col)
        self.field_instructions = {}

    def update_field_instructions(self, field_instructions: dict[str, str]) -> None:
        """Update the field instructions for this prompt builder."""
        self.field_instructions = field_instructions

    def build_prompt_template(
        self,
        target_notes: SelectedNotesFromType,
        field_selection: FieldSelection,
        max_examples: int,
    ) -> str:
        """
        Build the prompt template string with {target_notes_xml} placeholder.
        """
        if not field_selection.writable:
            target_fields = field_selection.selected
        else:
            target_fields = field_selection.writable

        # Check precondition: notes with empty writable fields OR notes with overwritable fields
        has_empty_writable = target_notes.has_note_with_empty_field(target_fields)
        has_overwritable = field_selection.overwritable and any(
            field in note for note in target_notes.get_notes() for field in field_selection.overwritable
        )
        if not has_empty_writable and not has_overwritable:
            raise ValueError("Target notes does not have any notes with empty writable fields or overwritable fields")

        fields_to_fill = field_selection.overwritable if field_selection.overwritable else field_selection.writable
        if not fields_to_fill:
            raise ValueError("No writable or overwritable fields specified")

        # Get example notes
        example_notes = self.select_example_notes(target_notes.note_type, target_notes, field_selection.selected, max_examples)

        formatted_examples_xml = (
            self.format_notes_as_xml(example_notes, target_notes.note_type, field_selection.selected) if example_notes else ""
        )

        prompt = TransformPromptTemplate(self.field_instructions, fields_to_fill, formatted_examples_xml)
        return prompt.render("{target_notes_xml}")

    def get_renderer_from_template(
        self,
        prompt_template_str: str,
        target_notes: SelectedNotesFromType,
        field_selection: FieldSelection,
    ) -> Callable[[SelectedNotesFromType | None], str]:
        """
        Get a renderer function from a provided template string.
        """
        if not field_selection.writable:
            target_fields = field_selection.selected
        else:
            target_fields = field_selection.writable

        def render_prompt(provided_target_notes: SelectedNotesFromType | None = None) -> str:

            if provided_target_notes is None:
                provided_target_notes = target_notes

            # Get target notes and filter to include:
            # 1. Notes with empty fields in writable_fields
            # 2. Notes with fields in overwritable_fields (regardless of emptiness)
            target_notes_to_include: list[Note] = []
            for note in provided_target_notes.get_notes():
                # Check if note has empty field in writable_fields
                if SelectedNotes.has_empty_field(note, target_fields):
                    target_notes_to_include.append(note)
                # Check if note has field in overwritable_fields
                elif field_selection.overwritable and any(field in note for field in field_selection.overwritable):
                    target_notes_to_include.append(note)

            if not target_notes_to_include:
                raise ValueError("No target notes with empty writable fields or overwritable fields found")

            formatted_target_notes_xml = self.format_notes_as_xml(
                target_notes_to_include, provided_target_notes.note_type, field_selection.selected, field_selection.overwritable
            )

            return prompt_template_str.replace("{target_notes_xml}", formatted_target_notes_xml)

        return render_prompt

    def get_prompt_renderer(
        self,
        target_notes: SelectedNotesFromType,
        field_selection: FieldSelection,
        max_examples: int,
    ) -> Callable[[SelectedNotesFromType | None], str]:
        """
        Get a function that renders the prompt for the given target notes and field selection.
        """
        prompt_template_str = self.build_prompt_template(target_notes, field_selection, max_examples)
        return self.get_renderer_from_template(prompt_template_str, target_notes, field_selection)
