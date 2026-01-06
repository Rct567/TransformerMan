"""
TransformerMan by Rick Zuidhoek. Licensed under the GNU GPL-3.0.
See <https://www.gnu.org/licenses/gpl-3.0.html> for details.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from .xml_parser import new_notes_from_xml
from .generation_prompt_builder import GenerationPromptBuilder

if TYPE_CHECKING:
    from .lm_clients import LMClient, LmResponse
    from .http_utils import LmProgressData
    from .selected_notes import NoteModel, SelectedNotesFromType
    from .transform_middleware import TransformMiddleware
    from anki.collection import Collection


class NoteGenerator:
    """Handles the generation of new Anki notes using a language model."""

    prompt: str | None
    response: LmResponse | None

    def __init__(self, col: Collection, lm_client: LMClient, transform_middleware: TransformMiddleware) -> None:
        self.col = col
        self.lm_client = lm_client
        self.transform_middleware = transform_middleware
        self.prompt_builder = GenerationPromptBuilder(col)
        self.prompt = None
        self.response = None

    def generate_notes(
        self,
        source_text: str,
        note_type: NoteModel,
        deck_name: str,
        target_count: int,
        selected_fields: list[str] | None = None,
        example_notes: SelectedNotesFromType | None = None,
        progress_callback: Callable[[LmProgressData], None] | None = None,
        should_cancel: Callable[[], bool] | None = None,
    ) -> list[dict[str, str]]:
        """
        Generate new notes and return them as a list of dictionaries.

        Args:
            source_text: The raw text to generate notes from.
            note_type: The target note type.
            deck_name: The target deck name.
            target_count: Number of notes to generate.
            selected_fields: Optional list of fields to include in generation.
            example_notes: Optional selection of notes to use as style examples.
            progress_callback: Optional callback for progress reporting.
            should_cancel: Optional callback to check if operation should be canceled.

        Returns:
            List of dictionaries, each representing a new note.
        """
        self.prompt = self.prompt_builder.build_prompt(
            source_text=source_text,
            note_type=note_type,
            deck_name=deck_name,
            target_count=target_count,
            selected_fields=selected_fields,
            example_notes=example_notes,
        )

        # Initial response
        self.response = None

        # Pre-transform middleware (e.g., log request)
        self.transform_middleware.before_transform(self)  # type: ignore[arg-type]

        # Get LM response
        if not self.response:
            self.response = self.lm_client.transform(
                prompt=self.prompt,
                progress_callback=progress_callback,
                should_cancel=should_cancel,
            )

        # Post-transform middleware (e.g., log response)
        self.transform_middleware.after_transform(self)  # type: ignore[arg-type]

        if self.response.error:
            raise Exception(self.response.error)

        if self.response.is_canceled:
            return []

        return new_notes_from_xml(self.response.content)
